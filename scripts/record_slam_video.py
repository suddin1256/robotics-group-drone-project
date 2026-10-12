from pathlib import Path
import time
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

output = Path.home() / "Documents/tello-slam/assets/tello_test.avi"
rclpy.init()
node = Node("record_slam_video")
bridge = CvBridge()
writer = None
count = 0
first = None

def receive(msg):
    global writer, count, first
    frame = bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
    if frame.shape[:2] != (240, 320):
        raise RuntimeError("Expected 320x240 images")
    if writer is None:
        writer = cv2.VideoWriter(
            str(output), cv2.VideoWriter_fourcc(*"MJPG"), 15.0, (320, 240)
        )
        if not writer.isOpened():
            raise RuntimeError("Could not open video writer")
        first = time.monotonic()
        print("Recording. Slowly move the camera through the scene.", flush=True)
    writer.write(frame)
    count += 1
    if count % 75 == 0:
        print(f"Recorded {count} frames", flush=True)

subscription = node.create_subscription(
    Image, "/tello/image_raw", receive, qos_profile_sensor_data
)

deadline = time.monotonic() + 45
try:
    while count < 450 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
finally:
    if writer is not None:
        writer.release()
    node.destroy_node()
    rclpy.shutdown()

print(f"Saved {count} frames: {output}")
if first is not None:
    print(f"Received rate: {count / (time.monotonic() - first):.1f} Hz")
