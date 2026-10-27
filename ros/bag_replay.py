"""Replay recorded sensing/status only. Never import a drone library or publish control requests."""
import argparse
import json
import math
import os
import struct
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.serialization import deserialize_message
import rosbag2_py
from sensor_msgs.msg import Image
from std_msgs.msg import String

ALLOWED = {
    '/tello/image_raw': ('sensor_msgs/msg/Image', Image),
    '/tello/telemetry': ('std_msgs/msg/String', String),
    '/tello/control_status': ('std_msgs/msg/String', String),
}

class BagReplay(Node):
    def __init__(self, bag, rate):
        super().__init__('tello_bag_replay')
        self.bag = bag
        self.rate = rate
        self.folder = Path(os.environ['TELLO_RUNTIME_DIR'])
        self.folder.mkdir(parents=True, exist_ok=True)
        self.publishers_by_topic = {
            topic: self.create_publisher(kind, topic, qos_profile_sensor_data if kind is Image else 10)
            for topic, (_, kind) in ALLOWED.items()
        }
        self.replay_publisher = self.create_publisher(String, '/tello/replay_status', 10)
        self.last_status = 0
        self.image_count = 0
        self.position = 0
        self.recorded_image_stamp = None
        self.delivery_image_stamp = None
        self.ordered = None
        if os.environ.get('TELLO_SLAM_ORDERED') == '1':
            from cv_bridge import CvBridge
            self.converter = CvBridge()
            self.ordered = (self.folder/'slam-input.bin').open('wb')
        self.reader = rosbag2_py.SequentialReader()
        self.reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id='mcap'),
                         rosbag2_py.ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr'))
        topics = {item.name: item.type for item in self.reader.get_all_topics_and_types()}
        if topics.get('/tello/image_raw') != 'sensor_msgs/msg/Image':
            raise RuntimeError('Bag does not contain the expected /tello/image_raw camera topic.')
        for topic, (expected, _) in ALLOWED.items():
            if topic in topics and topics[topic] != expected:
                raise RuntimeError(f'Unexpected message type for {topic}: {topics[topic]}')
        self.reader.set_filter(rosbag2_py.StorageFilter(topics=list(ALLOWED)))

    def status(self, state, force=False):
        now = time.monotonic()
        if not force and now - self.last_status < 0.5:
            return
        self.last_status = now
        data = {'mode': 'bag', 'state': state, 'bag': self.bag.name,
                'stamp_ns': time.time_ns(), 'position_seconds': self.position,
                'rate': self.rate, 'image_count': self.image_count,
                'recorded_image_stamp_ns': self.recorded_image_stamp,
                'delivery_image_stamp_ns': self.delivery_image_stamp,
                'flight_enabled': False, 'recorded_controls_replayed': False}
        temporary = self.folder / 'playback.tmp'
        temporary.write_text(json.dumps(data))
        temporary.replace(self.folder / 'playback.json')
        message = String(); message.data = json.dumps(data)
        self.replay_publisher.publish(message)

    def publish_record(self, topic, payload, recording_stamp):
        message = deserialize_message(payload, ALLOWED[topic][1])
        now = time.time_ns()
        if topic == '/tello/image_raw':
            self.recorded_image_stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
            if self.ordered is not None:
                frame = self.converter.imgmsg_to_cv2(message, desired_encoding='bgr8')
                if frame.shape != (240,320,3):
                    raise RuntimeError('Ordered SLAM expects the calibrated 320x240 camera stream.')
                packet = struct.pack('<dII', self.recorded_image_stamp/1e9, 320,240)+frame.tobytes()
                if self.ordered.tell()+len(packet) > 2*1024**3:
                    raise RuntimeError('Ordered SLAM spool exceeded 2 GiB. Use a shorter recording; original bag is unchanged.')
                self.ordered.write(packet)
                self.ordered.flush()
            self.delivery_image_stamp = now
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(now, 1_000_000_000)
            self.image_count += 1
        else:
            data = json.loads(message.data)
            data['recording_time_ns'] = recording_stamp
            data['replay'] = True
            if topic == '/tello/telemetry':
                data['recorded_received_stamp_ns'] = data.get('received_stamp_ns')
                data['received_stamp_ns'] = now
            else:
                data['recorded_stamp_ns'] = data.get('stamp_ns')
                data['stamp_ns'] = now
                data['recorded_flight_enabled'] = data.get('flight_enabled')
                data['flight_enabled'] = False
                data['input_active'] = False
                data['phase'] = 'PLAYBACK: ' + str(data.get('phase', 'unknown'))
            message.data = json.dumps(data)
        self.publishers_by_topic[topic].publish(message)

    def play(self):
        self.status('waiting for consumers', True)
        deadline = time.monotonic() + 15
        while rclpy.ok() and time.monotonic() < deadline:
            if self.count_subscribers('/tello/image_raw') and self.count_subscribers('/tello/telemetry') and self.count_subscribers('/tello/control_status'):
                break
            rclpy.spin_once(self, timeout_sec=0.1)
        if not self.count_subscribers('/tello/image_raw'):
            raise RuntimeError('Image bridge not discovered within 15 seconds. Check bridge log.')
        if os.environ.get('TELLO_WAIT_FOR_VISION') == '1':
            deadline = time.monotonic() + 180
            while rclpy.ok() and time.monotonic() < deadline:
                self.status('waiting for V4 models')
                try:
                    vision = json.loads((self.folder / 'vision-status.json').read_text())
                except FileNotFoundError:
                    vision = {}
                if os.environ.get('TELLO_VISION_SPLIT') == '1':
                    try:
                        depth = json.loads((self.folder/'depth-status.json').read_text())
                    except FileNotFoundError:
                        depth = {}
                else:
                    depth = vision
                ready_states = {'waiting','ready','running','processing','error'}
                if vision.get('state') in ready_states and depth.get('state') in ready_states:
                    break
                if vision.get('state') == 'error':
                    print('V4 failed to load; playing recording without processed vision. Check vision log.', flush=True)
                    break
                rclpy.spin_once(self, timeout_sec=0.1)
            else:
                print('V4 preparation timed out; starting recording. Check vision log.', flush=True)
        first = None
        start = time.monotonic()
        last_report = start
        while rclpy.ok() and self.reader.has_next():
            topic, payload, stamp = self.reader.read_next()
            if topic not in ALLOWED:
                continue
            if first is None:
                first = stamp
                start = time.monotonic()
            target = start + (stamp - first) / 1e9 / self.rate
            while rclpy.ok() and time.monotonic() < target:
                rclpy.spin_once(self, timeout_sec=min(0.05, max(0, target - time.monotonic())))
            if not rclpy.ok():
                return
            self.position = (stamp - first) / 1e9
            self.publish_record(topic, payload, stamp)
            self.status('playing')
            rclpy.spin_once(self, timeout_sec=0)
            if time.monotonic() - last_report >= 5:
                print(f'Bag replay: {self.position:.1f}s | images={self.image_count} | rate={self.rate}x', flush=True)
                last_report = time.monotonic()
        if self.ordered is not None:
            self.ordered.close()
            self.ordered = None
            (self.folder/'slam-input.done').write_text(str(self.image_count))
        self.status('finished', True)
        print('Recording finished. Dashboard remains open; Ctrl+C stops all components. Restart to replay.', flush=True)
        while rclpy.ok():
            self.status('finished')
            rclpy.spin_once(self, timeout_sec=0.2)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag', type=Path)
    parser.add_argument('--rate', type=float, default=1.0)
    args = parser.parse_args()
    if not math.isfinite(args.rate) or args.rate <= 0:
        parser.error('--rate must be positive')
    rclpy.init()
    node = None
    try:
        node = BagReplay(args.bag.resolve(), args.rate)
        node.play()
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            if node.ordered is not None:
                node.ordered.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
