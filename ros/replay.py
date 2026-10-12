"""Recorded camera input plus a mock flight driver; never imports a drone library."""
import argparse, json, time
import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String

class Replay(Node):
    def __init__(self, video):
        super().__init__('tello_replay')
        self.capture=cv2.VideoCapture(video)
        if not self.capture.isOpened(): raise RuntimeError('Cannot decode replay video')
        self.bridge=CvBridge()
        self.images=self.create_publisher(Image,'/tello/image_raw',qos_profile_sensor_data)
        self.status=self.create_publisher(String,'/tello/control_status',10)
        self.telemetry=self.create_publisher(String,'/tello/telemetry',10)
        self.mode='slow'; self.rc=[0]*4; self.phase='grounded'; self.last=0
        self.control=self.create_subscription(String,'/tello/manual_control',self.receive,10)
        self.create_timer(1/15,self.tick)
    def receive(self,message):
        data=json.loads(message.data)
        self.mode=data.get('mode','slow')
        if time.time_ns()-data.get('sent_stamp_ns',0)>350_000_000:return
        self.last=time.monotonic()
        self.rc=data.get('rc',[0]*4) if data.get('input_fresh') else [0]*4
        for action in data.get('actions',[]):
            if action=='toggle_flight': self.phase='armed_simulated'
            elif action=='land': self.phase='grounded'
            elif action=='stop': self.rc=[0]*4
        if self.phase=='armed_simulated' and self.rc[2]>0:self.phase='airborne_simulated'
    def tick(self):
        ok,frame=self.capture.read()
        if not ok:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES,0)
            ok,frame=self.capture.read()
            if not ok:raise RuntimeError('Video contains no decodable frames')
        frame=cv2.resize(frame,(320,240))
        message=self.bridge.cv2_to_imgmsg(frame,encoding='bgr8')
        message.header.stamp=self.get_clock().now().to_msg()
        message.header.frame_id='tello_camera_optical_frame'
        self.images.publish(message)
        fresh=time.monotonic()-self.last<0.35
        status={'stamp_ns':time.time_ns(),'phase':self.phase,'mode':self.mode,
                'descent_assist':False,'input_active':fresh,'commanded_rc':self.rc if fresh else [0]*4,
                'flight_enabled':False,'native_fast_requested':False,'battery':100,'simulation':True}
        out=String();out.data=json.dumps(status);self.status.publish(out)
        out=String();out.data=json.dumps({'received_stamp_ns':time.time_ns(),'state':{'bat':100,'simulation':True,'note':'Synthetic telemetry; video is recorded'}});self.telemetry.publish(out)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('video');args=parser.parse_args()
    rclpy.init();node=Replay(args.video)
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        node.capture.release();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
