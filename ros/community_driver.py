"""Pinned PedroS235 ROS2 driver adapted to our launch/control and recording contract.

Upstream publishers and serializers are reused; raw native readings are preserved.
Experimental motion topics are not calibrated SI data and are never fed to SLAM.
"""
import json
import os
from pathlib import Path
import sys
import time
from collections import deque

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/tello_ros2_driver/tello_driver'))
from community_paths import configure
configure()
from tello_driver.tello_driver import TelloRosWrapper
from tello_driver.serializers import generate_imu_msg, generate_odom_msg
from tello_manual_launch import ManualLaunch, main
from telemetry_capture import plain, previous_sample
from std_msgs.msg import String


class CommunityFlight(ManualLaunch, TelloRosWrapper):
    def __init__(self, enabled):
        # One ROS node, one drone connection. Do not run upstream's auto-connect lifecycle.
        ManualLaunch.__init__(self, enabled)
        self.tello=self.drone
        self._image_topic_name='/tello/community/image_unused'
        self._flight_data_topic_name='/tello/flight_data'
        self._odom_topic_name='/tello/odometry_unverified'
        self._imu_topic_name='/tello/imu_unverified'
        self._battery_state_topic_name='/tello/battery'
        self._odom_frame_id='tello_native_odom_unverified'
        self._imu_frame_id='tello_native_imu_unverified'
        TelloRosWrapper._init_publisher(self)
        self.raw_logs=self.create_publisher(String,'/tello/raw_log',100)
        self.raw_packets=self.create_publisher(String,'/tello/raw_log_packets',100)
        self.frame_metadata=self.create_publisher(String,'/tello/image_metadata',30)
        self.capabilities=self.create_publisher(String,'/tello/capabilities',10)
        self.samples={'flight':deque(maxlen=1500),'log':deque(maxlen=1500)}
        self.folder=Path(os.environ.get('TELLO_RUNTIME_DIR',str(ROOT/'runtime/live')))
        self.capture_folder=self.folder/'captures'/time.strftime('%Y%m%d_%H%M%S')
        self.capture_folder.mkdir(parents=True,exist_ok=True)
        self.events=(self.capture_folder/'telemetry.jsonl').open('a',buffering=1)
        self.frames=(self.capture_folder/'image-metadata.jsonl').open('a',buffering=1)
        self.drone.subscribe(self.drone.EVENT_LOG_DATA,self._log_data_callback)
        self.drone.subscribe(self.drone.EVENT_LOG_RAWDATA,self.receive_packet)
        self.drone.subscribe(self.drone.EVENT_FLIGHT_DATA,self._flight_data_callback)
        self.raw_status={}
        self.create_timer(1.,self.publish_inventory)
        self.tool_subscription=self.create_subscription(String,'/tello/tools',self.tool_request,10)

    def capture(self, kind, data):
        sample={'received_stamp_ns':time.time_ns(),'kind':kind,'data':plain(data),
                'clock':'host_receive_time','units_and_axes_verified':False}
        with self.lock:
            self.samples[kind].append(sample)
            self.events.write(json.dumps(sample,allow_nan=False)+'\n')
            self.raw_status[kind]=sample
        return sample

    def receive_packet(self,event,sender,data,**kwargs):
        packet={'kind':'log_packet','received_stamp_ns':time.time_ns(),
                'native_recv_time':kwargs.get('recv_time'),'payload_hex':bytes(data).hex()}
        text=json.dumps(packet,allow_nan=False)
        with self.lock:self.events.write(text+'\n')
        message=String();message.data=text;self.raw_packets.publish(message)

    def _flight_data_callback(self,event,sender,data,**kwargs):
        self.capture('flight',data)
        # Reuse upstream flight statistics mapping. Battery voltage is not measured.
        from tello_driver.serializers import generate_flight_data_msg, generate_battery_state_msg
        self._flight_data_publisher.publish(generate_flight_data_msg(data))
        battery=generate_battery_state_msg(self.get_clock().now(),data)
        battery.percentage=float(data.battery_percentage)/100.
        battery.voltage=float('nan')
        battery.cell_voltage=[]
        self._battery_state_publisher.publish(battery)

    def _log_data_callback(self,event,sender,data,**kwargs):
        sample=self.capture('log',data)
        raw=String();raw.data=json.dumps(sample,allow_nan=False);self.raw_logs.publish(raw)
        records=getattr(data,'records',None)
        updated={getattr(r,'record_id',None) for r in records} if records is not None else None
        # Preserve upstream conventions on explicitly unverified topics; do not publish TF.
        now=self.get_clock().now()
        imu=generate_imu_msg(now,self._imu_frame_id,data)
        imu.orientation_covariance[0]=-1.
        imu.angular_velocity_covariance[0]=-1.
        imu.linear_acceleration_covariance[0]=-1.
        odom=generate_odom_msg(now,self._odom_frame_id,data)
        odom.child_frame_id='tello_native_body_unverified'
        # Fix upstream's copy/paste of vel_x into all three components.
        odom.twist.twist.linear.y=-float(data.mvo.vel_y)
        odom.twist.twist.linear.z=float(data.mvo.vel_z)
        for axis in range(6):
            odom.pose.covariance[axis*7]=1e6
            odom.twist.covariance[axis*7]=1e6
        if updated is None or getattr(data.imu,'record_id',None) in updated:
            self._imu_publisher.publish(imu)
        if updated is None or getattr(data.mvo,'record_id',None) in updated:
            self._odometry_publisher.publish(odom)

    def publish_image(self):
        before=self.published_sequence
        ManualLaunch.publish_image(self)
        if before==self.published_sequence:return
        # publish_image records the precise frame actually published, not the next decode.
        stamp,sequence=self.last_published_frame
        with self.lock:
            data={'image_stamp_ns':stamp,'sequence':sequence,'width':320,'height':240,
                  'phase':self.phase,
                  'launch_surface':self.launch_surface,'table_height_cm':self.table_height_cm,
                  'association':'latest preceding host-received sample; NOT hardware synchronization',
                  'flight':previous_sample(self.samples['flight'],stamp),
                  'log':previous_sample(self.samples['log'],stamp)}
            self.frames.write(json.dumps(data,allow_nan=False)+'\n')
        message=String();message.data=json.dumps(data,allow_nan=False)
        self.frame_metadata.publish(message)
        temporary=self.folder/'image-metadata.tmp'
        temporary.write_text(message.data);temporary.replace(self.folder/'image-metadata.json')

    def publish_inventory(self):
        with self.lock:latest=dict(self.raw_status)
        info={'backend':'PedroS235/tello_ros2_driver (adapted)',
              'upstream_commit':'9a2bef366ebe2a2e7b57ef170e4f7cafb483e8e8',
              'tellopy_api_inventory':[name for name in dir(self.drone) if not name.startswith('_') and callable(getattr(self.drone,name,None))],
              'available_tools':['manual arm/lift','land','neutral/manual takeover','slow/normal/native fast',
                                 'camera exposure (0/1/2)','ground/table launch annotation'],
              'upstream_tools_not_enabled':['flips','throw and go','palm land','automatic takeoff','altitude/attitude limits','video-mode changes'],
              'notes':'Motion units/axes and firmware field availability unverified; no TF or SLAM fusion.',
              'capture_directory':str(self.capture_folder),
              'latest':latest}
        message=String();message.data=json.dumps(info,allow_nan=False);self.capabilities.publish(message)
        temporary=self.folder/'driver-data.tmp'
        temporary.write_text(message.data);temporary.replace(self.folder/'driver-data.json')

    def tool_request(self,message):
        try:
            data=json.loads(message.data)
            if time.time_ns()-data['sent_stamp_ns'] not in range(0,500_000_001):return
            if data['tool']=='exposure' and type(data['value']) is int and data['value'] in {0,1,2}:
                self.drone.set_exposure(data['value'])
        except (KeyError,TypeError,ValueError):return

    def close(self):
        try:ManualLaunch.close(self)
        finally:
            self.events.close();self.frames.close()


if __name__=='__main__':main(CommunityFlight)
