import json
from pathlib import Path
import os
from urllib.parse import urlparse
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

lock = threading.Lock()
keys = set()
actions = deque()
last_input = 0.0
input_enabled = False
selected_mode = "slow"
control_status = "{}"
live_folder = Path(os.environ["TELLO_RUNTIME_DIR"])
allowed = {"w", "s", "a", "d", "ArrowUp", "ArrowDown",
           "ArrowLeft", "ArrowRight"}

PAGE = Path(__file__).with_name("dashboard.html").read_text()
PLAYBACK_ONLY = os.environ.get('TELLO_PLAYBACK_ONLY') == '1'
if PLAYBACK_ONLY:
    PAGE = PAGE.replace('<h2>', '<script>window.TELLO_PLAYBACK_ONLY=true;</script><h2>', 1)
    PAGE = PAGE.replace('Live camera</h3>', 'Recorded camera</h3>')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/slam_blocks.js':
            body = Path(__file__).with_name('slam_blocks.js').read_bytes()
            content_type = 'application/javascript; charset=utf-8'
        elif path == "/control.json":
            with lock:
                body = control_status.encode()
            content_type = "application/json"
        elif path in {
            "/video.jpg", "/preview.jpg", "/map.json", "/telemetry.json",
            "/vision.jpg", "/vision-status.json", "/playback.json",
            "/depth.jpg", "/depth-status.json", "/slam-status.json"
        }:
            try:
                body = (live_folder / path[1:]).read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
            content_type = (
                "image/jpeg" if path.endswith(".jpg")
                else "application/json"
            )
        elif path == "/":
            body = PAGE.encode()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return
        if self.path != "/":
            self.send_error(404)
            return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global keys, last_input, input_enabled, selected_mode
        if PLAYBACK_ONLY:
            self.send_error(403, 'Flight controls disabled during bag playback')
            return
        if self.path != "/input":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            requested = data.get("keys", [])
            if not isinstance(requested, list):
                raise ValueError("Invalid keys")
            with lock:
                keys = {k for k in requested if k in allowed}
                input_enabled = data.get("enabled") is True
                mode = data.get("mode", "slow")
                if mode in {"slow", "normal", "fast", "descent"}:
                    selected_mode = mode

                last_input = time.monotonic()
                action = data.get("action")
                if action in {"stop", "land", "toggle_flight"}:
                    keys.clear()
                    actions.append(action)
        except (ValueError, TypeError):
            self.send_error(400)
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass

class ManualControl(Node):
    def __init__(self):
        super().__init__("manual_control_live")
        self.publisher = None if PLAYBACK_ONLY else self.create_publisher(
            String, "/tello/manual_control", 10
        )
        self.driver_status_subscription = self.create_subscription(
            String, "/tello/control_status", self.receive_driver_status, 10
        )
        self.previous = None
        self.create_timer(0.05, self.tick)

    def receive_driver_status(self, message):
        global control_status
        with lock:
            control_status = message.data

    def tick(self):
        if PLAYBACK_ONLY:
            return
        with lock:
            fresh = input_enabled and time.monotonic() - last_input < 0.35
            held = set(keys) if fresh else set()
            mode = selected_mode
            pending = list(actions)
            actions.clear()

        speed = 20 if mode == "slow" else 35
        rc = [
            speed * (("ArrowRight" in held) - ("ArrowLeft" in held)),
            speed * (("ArrowUp" in held) - ("ArrowDown" in held)),
            speed * (("w" in held) - ("s" in held)),
            speed * (("d" in held) - ("a" in held)),
        ]
        message = String()
        message.data = json.dumps({
            "dry_run": False,
            "mode": mode,
            "rc": rc,
            "input_fresh": fresh,
            "sent_stamp_ns": time.time_ns(),
            "actions": pending
        })
        self.publisher.publish(message)

        current = (tuple(rc), fresh)
        if current != self.previous:
            print(
                f"LIVE CONTROL: slide={rc[0]}, forward={rc[1]}, "
                f"up={rc[2]}, yaw={rc[3]} | "
                f"{'input active' if fresh else 'input expired: STOP'}",
                flush=True
            )
            self.previous = current
        for action in pending:
            print(f"LIVE CONTROL action: {action}", flush=True)

rclpy.init()
node = ManualControl()
port = int(os.environ.get('TELLO_DASHBOARD_PORT', '8082'))
server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
print(f"Open http://127.0.0.1:{port} — " + ('RECORDING PLAYBACK, controls disabled.' if PLAYBACK_ONLY else 'use only with the flight driver in a clear flight area.'), flush=True)

try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    server.shutdown()
    server.server_close()
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
