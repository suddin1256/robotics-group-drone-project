import argparse
import json
import threading
import time
from collections import deque

import av
import cv2
import rclpy
import tellopy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String


class ManualLaunch(Node):
    def __init__(self, enabled):
        super().__init__("tello_manual_launch")
        self.enabled = enabled
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.drone = tellopy.Tello()
        self.drone.set_loglevel(tellopy.Tello.LOG_WARN)
        self.converter = CvBridge()
        self.state = {}
        self.state_time = 0.0
        self.state_stamp = 0
        self.frame = None
        self.frame_sequence = 0
        self.published_sequence = -1
        self.last_input = 0.0
        self.rc = [0, 0, 0, 0]
        self.output_rc = [0, 0, 0, 0]
        self.actions = deque()
        self.phase = "grounded"
        self.mode = "slow"
        self.descent = False
        self.deadline = 0.0
        self.landing_started = 0.0
        self.last_land_send = 0.0
        self.worker = None
        self.video_worker = None
        self.closing = False

        self.images = self.create_publisher(
            Image, "/tello/image_raw", qos_profile_sensor_data
        )
        self.telemetry = self.create_publisher(String, "/tello/telemetry", 10)
        self.status = self.create_publisher(String, "/tello/control_status", 10)
        self.controls = self.create_subscription(
            String, "/tello/manual_control", self.receive_control, 1
        )
        self.drone.subscribe(self.drone.EVENT_FLIGHT_DATA, self.receive_state)
        self.create_timer(1 / 15, self.publish_image)
        self.create_timer(0.2, self.publish_status)

    def receive_state(self, event, sender, data, **kwargs):
        values = {
            name: value for name, value in vars(data).items()
            if isinstance(value, (int, float, bool, str))
        }
        with self.lock:
            self.state = values
            self.state_time = time.monotonic()
            self.state_stamp = time.time_ns()

    def receive_control(self, message):
        try:
            request = json.loads(message.data)
            age = (time.time_ns() - request["sent_stamp_ns"]) / 1e9
            rc = request["rc"]
            if request.get("dry_run") is not False:
                return
            if not -0.1 <= age <= 0.35:
                return
            if not isinstance(rc, list) or len(rc) != 4:
                return
            if any(type(v) is not int or abs(v) > 35 for v in rc):
                return
            actions = request.get("actions", [])
            if not isinstance(actions, list):
                return
        except (ValueError, TypeError, KeyError):
            return

        with self.lock:
            # Landing remains available with keyboard controls disabled.
            if "land" in actions:
                self.actions.append("land")

            if request.get("input_fresh") is not True:
                self.rc = [0, 0, 0, 0]
                return

            self.last_input = time.monotonic()
            mode = request.get("mode", "slow")
            self.mode = mode if mode in {"slow", "normal", "fast", "descent"} else "slow"
            limit = 20 if self.mode == "slow" else 35
            self.rc = [max(-limit, min(limit, v)) for v in rc]

            if "stop" in actions:
                self.rc = [0, 0, 0, 0]
                self.actions.append("stop")

            if "toggle_flight" in actions and not any(rc):
                self.actions.append("arm")

    def sticks(self, rc):
        # TelloPy uses normalized stick positions, not SDK RC commands.
        self.drone.set_throttle(rc[2] / 100.0)
        self.drone.set_roll(rc[0] / 100.0)
        self.drone.set_pitch(rc[1] / 100.0)
        self.drone.set_yaw(rc[3] / 100.0)
        with self.lock:
            self.output_rc = list(rc)

    def neutral(self):
        self.sticks([0, 0, 0, 0])

    def request_landing(self, reason):
        self.drone.fast_mode = False
        self.neutral()
        if self.phase != "landing":
            print(f"LAND REQUEST: {reason}", flush=True)
            self.phase = "landing"
            self.landing_started = time.monotonic()
            self.last_land_send = 0.0

    def command_loop(self):
        try:
            while not self.done.is_set():
                now = time.monotonic()
                with self.lock:
                    state = dict(self.state)
                    telemetry_age = now - self.state_time
                    input_age = now - self.last_input
                    rc = list(self.rc)
                    actions = list(self.actions)
                    self.actions.clear()
                    closing = self.closing
                    mode = self.mode

                fresh = input_age < 0.35
                flying = bool(state.get("em_sky", 0))
                motors = bool(state.get("em_open", 0))
                battery = state.get("battery_percentage", 0)
                self.drone.fast_mode = bool(
                    self.phase == "airborne"
                    and mode == "fast"
                    and fresh
                    and telemetry_age < 1
                    and battery > 20
                    and not self.descent
                    and not closing
                )


                if closing:
                    if self.phase == "grounded":
                        return
                    self.request_landing("driver stopping")

                if "land" in actions and self.phase != "grounded":
                    self.request_landing("operator")

                if "stop" in actions:
                    self.neutral()
                    if self.phase in {"arming", "armed_unconfirmed"}:
                        self.request_landing("arming cancelled")

                if "arm" in actions and self.phase == "grounded":
                    if not self.enabled:
                        print("Arming blocked: ground-check mode.", flush=True)
                    elif not fresh or telemetry_age > 1:
                        print("Arming blocked: input or telemetry stale.", flush=True)
                    elif battery < 30:
                        print(f"Arming blocked: battery {battery}% < 30%.", flush=True)
                    elif flying or motors:
                        print("Arming blocked: reported motor/flight state is not idle.",
                              flush=True)
                    else:
                        print("ARMING for 2 seconds. Keep controls active; release keys.",
                              flush=True)
                        self.drone.manual_takeoff()
                        self.phase = "arming"
                        self.deadline = now + 2.0

                if self.phase != "grounded" and self.phase != "landing":
                    if telemetry_age > 1.0 or input_age > 2.0:
                        self.request_landing("input or telemetry lost")

                if self.phase == "arming":
                    if not fresh:
                        self.request_landing("input interrupted during arming")
                    elif now >= self.deadline:
                        self.neutral()
                        self.phase = "armed_unconfirmed"
                        self.deadline = now + 8.0
                        print(
                            "Arming sticks returned to NEUTRAL. "
                            "Visually confirm motors are idling. "
                            "Then hold W briefly; L requests landing.",
                            flush=True
                        )

                elif self.phase == "armed_unconfirmed":
                    self.neutral()
                    if flying:
                        self.phase = "airborne"
                    elif fresh and rc[2] > 0:
                        self.phase = "lifting"
                        self.deadline = now + 5.0
                        self.sticks([0, 0, min(rc[2], 20), 0])
                    elif now > self.deadline:
                        self.request_landing("no manual lift requested")

                elif self.phase == "lifting":
                    if flying:
                        self.phase = "airborne"
                        print("Telemetry reports airborne.", flush=True)
                    elif now > self.deadline:
                        self.request_landing("airborne state not reported")
                    else:
                        self.sticks(
                            [0, 0, max(0, min(rc[2], 20)), 0]
                            if fresh else [0, 0, 0, 0]
                        )

                elif self.phase == "airborne":
                    if battery <= 20:
                        self.descent = True
                    command = list(rc) if fresh else [0, 0, 0, 0]
                    if fresh and (self.descent or mode == "descent"):
                        command[2] = 0 if command[2] > 0 else min(command[2], -10)
                    self.sticks(command)

                    if telemetry_age < 1 and not flying and not motors:
                        self.neutral()
                        self.phase = "grounded"
                        self.descent = False
                        print("Telemetry reports motors off / not airborne.", flush=True)

                elif self.phase == "landing":
                    self.neutral()
                    if now - self.last_land_send > 2.0:
                        self.drone.land()
                        self.last_land_send = now
                    if (
                        now - self.landing_started > 1
                        and telemetry_age < 1
                        and not flying and not motors
                    ):
                        self.phase = "grounded"
                        self.descent = False
                        print(
                            "Telemetry reports motors off / not airborne. "
                            "Confirm visually.", flush=True
                        )
                    elif closing and now - self.landing_started > 12:
                        print("Motor stop NOT confirmed before disconnect.", flush=True)
                        return

                time.sleep(0.02)
        except Exception as error:
            print(f"CONTROL ERROR: {error}", flush=True)
            self.neutral()
            self.drone.land()

    def decode_video(self, stream):
        container = None
        try:
            container = av.open(stream, format="h264", buffer_size=32768)
            for frame in container.decode(video=0):
                if self.done.is_set():
                    break
                rgb = cv2.resize(
                    frame.to_ndarray(format="rgb24"), (320, 240),
                    interpolation=cv2.INTER_AREA
                )
                with self.lock:
                    self.frame = rgb
                    self.frame_sequence += 1
        except Exception as error:
            if not self.done.is_set():
                print(f"VIDEO ERROR: {error}", flush=True)
        finally:
            if container is not None:
                container.close()

    def publish_image(self):
        with self.lock:
            image = self.frame
            sequence = self.frame_sequence
        if image is None or sequence == self.published_sequence:
            return
        message = self.converter.cv2_to_imgmsg(image, encoding="rgb8")
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "tello_camera_optical_frame"
        self.images.publish(message)
        self.published_sequence = sequence

    def publish_status(self):
        with self.lock:
            native = dict(self.state)
            stamp = self.state_stamp
            output = list(self.output_rc)
            mode = self.mode
            active = time.monotonic() - self.last_input < 0.35
        state = dict(native)
        state["bat"] = native.get("battery_percentage")
        state["protocol"] = "TelloPy native; unverified units remain raw"
        telemetry = String()
        telemetry.data = json.dumps({
            "received_stamp_ns": stamp, "state": state
        })
        self.telemetry.publish(telemetry)

        status = String()
        status.data = json.dumps({
            "stamp_ns": time.time_ns(),
            "phase": self.phase,
            "mode": mode,
            "descent_assist": self.descent,
            "commanded_rc": output,
            "input_active": active,
            "battery": native.get("battery_percentage"),
            "flight_enabled": self.enabled,
            "native_fast_requested": bool(self.drone.fast_mode),
            "reported_motor_flag": native.get("em_open"),
            "reported_airborne_flag": native.get("em_sky"),
            "automatic_height_limit": False
        })
        self.status.publish(status)

    def start(self):
        self.drone.connect()
        self.drone.wait_for_connection(10)
        self.neutral()
        stream = self.drone.get_video_stream()
        self.video_worker = threading.Thread(
            target=self.decode_video, args=(stream,), daemon=True
        )
        self.video_worker.start()
        self.worker = threading.Thread(target=self.command_loop, daemon=True)
        self.worker.start()
        print(
            "CONNECTED: T arms only; W requests lift; L requests landing."
            if self.enabled else
            "CONNECTED: GROUND CHECK — motor arming disabled.",
            flush=True
        )

    def close(self):
        self.closing = True
        if self.worker is not None:
            self.worker.join()
        self.done.set()
        self.neutral()
        self.drone.quit()


parser = argparse.ArgumentParser()
parser.add_argument("--enable-flight", action="store_true")
args = parser.parse_args()

rclpy.init()
node = ManualLaunch(args.enable_flight)
try:
    node.start()
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    node.close()
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
