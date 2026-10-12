import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

class RateCheck(Node):
    def __init__(self):
        super().__init__("check_video_rate")
        self.count = 0
        self.started = None
        self.last = None
        self.longest_gap = 0.0
        self.subscription = self.create_subscription(
            Image, "/tello/image_raw",
            self.receive, qos_profile_sensor_data
        )
        self.create_timer(5.0, self.report)

    def receive(self, message):
        now = time.monotonic()
        if self.started is None:
            self.started = now
            print(f"First image: {message.width}x{message.height}",
                  flush=True)
        if self.last is not None:
            self.longest_gap = max(self.longest_gap, now - self.last)
        self.last = now
        self.count += 1

    def report(self):
        if self.started is None:
            print("Waiting for images...", flush=True)
            return
        elapsed = time.monotonic() - self.started
        rate = (self.count - 1) / elapsed if elapsed else 0
        print(f"Received: {self.count}; average: {rate:.2f} Hz; "
              f"longest gap: {self.longest_gap:.2f}s", flush=True)

rclpy.init()
node = RateCheck()
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
