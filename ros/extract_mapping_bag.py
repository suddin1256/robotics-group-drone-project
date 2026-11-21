"""Read a bag directly into ordered SLAM input. No ROS node, publishing, Wi-Fi, or flight."""
import argparse,json,struct,shutil
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge

def extract(bag,folder):
    folder.mkdir(parents=True,exist_ok=True);telemetry=folder/'frame-telemetry';telemetry.mkdir(exist_ok=True)
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('cdr','cdr'))
    topics={t.name:t.type for t in reader.get_all_topics_and_types()}
    if topics.get('/tello/image_raw')!='sensor_msgs/msg/Image':raise ValueError('Recording has no supported camera images')
    if '/tello/image_metadata' in topics and topics['/tello/image_metadata']!='std_msgs/msg/String':raise ValueError('Unexpected telemetry metadata type')
    reader.set_filter(rosbag2_py.StorageFilter(topics=['/tello/image_raw','/tello/image_metadata']))
    converter=CvBridge();index=[];previous=-1
    with (folder/'slam-input.bin').open('wb') as stream:
        while reader.has_next():
            topic,payload,_=reader.read_next()
            if topic=='/tello/image_metadata':
                data=json.loads(deserialize_message(payload,String).data)
                (telemetry/f'{round(data["image_stamp_ns"]/1000)}.json').write_text(json.dumps(data));continue
            message=deserialize_message(payload,Image);stamp=message.header.stamp.sec+message.header.stamp.nanosec/1e9
            if stamp<=previous:raise ValueError('Camera timestamps are not strictly increasing')
            frame=converter.imgmsg_to_cv2(message,desired_encoding='bgr8')
            if frame.shape!=(240,320,3):raise ValueError('Camera frames must match the 320×240 SLAM calibration')
            if len(index)%100==0 and shutil.disk_usage(folder).free<512*1024**2:raise ValueError('Less than 512 MiB of disk space remains; extraction stopped')
            index.append({'stamp':stamp,'offset':stream.tell()});stream.write(struct.pack('<dII',stamp,320,240)+frame.tobytes());previous=stamp
            if len(index)%100==0:(folder/'extraction-progress.json').write_text(json.dumps({'images':len(index)}))
    if not index:raise ValueError('Recording contains no images')
    (folder/'frames-index.json').write_text(json.dumps(index));(folder/'slam-input.done').write_text(str(len(index)))
    print(f'Extracted {len(index)} original images and recorded image/telemetry metadata; no topics published.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bag',type=Path);p.add_argument('folder',type=Path);a=p.parse_args();extract(a.bag,a.folder)
