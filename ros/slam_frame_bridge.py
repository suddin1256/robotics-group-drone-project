from pathlib import Path
import os
import struct
import json
import cv2
from std_msgs.msg import String
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

folder = Path(os.environ["TELLO_RUNTIME_DIR"])
folder.mkdir(parents=True, exist_ok=True)

class FrameBridge(Node):
    def __init__(self):
        super().__init__("slam_frame_bridge")
        self.converter = CvBridge()
        self.telemetry_subscription = self.create_subscription(
            String, "/tello/telemetry", self.receive_telemetry, 10
        )
        self.count = 0
        self.last_report = time.monotonic()
        self.subscription = self.create_subscription(
            Image, "/tello/image_raw", self.receive,
            qos_profile_sensor_data
        )

    def receive_telemetry(self, message):
        data = json.loads(message.data)
        temporary = folder / "telemetry.tmp"
        temporary.write_text(json.dumps(data))
        temporary.replace(folder / "telemetry.json")

    def receive(self, message):
        frame = self.converter.imgmsg_to_cv2(
            message, desired_encoding="bgr8"
        )
        if frame.shape != (240, 320, 3):
            self.get_logger().error("Expected 320x240 colour images")
            return

        timestamp = (
            message.header.stamp.sec
            + message.header.stamp.nanosec * 1e-9
        )
        packet = struct.pack("<dII", timestamp, 320, 240)
        packet += frame.tobytes()

        temporary = folder / "frame.tmp"
        temporary.write_bytes(packet)
        temporary.replace(folder / "frame.bin")
        ok, jpeg = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
        if ok:
            preview = folder / "video.tmp"
            preview.write_bytes(jpeg.tobytes())
            preview.replace(folder / "video.jpg")


        self.count += 1
        now = time.monotonic()
        if now - self.last_report >= 5:
            self.get_logger().info(
                f"Passing images to SLAM: "
                f"{self.count / (now - self.last_report):.1f} Hz"
            )
            self.count = 0
            self.last_report = now

rclpy.init()
node = FrameBridge()
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
