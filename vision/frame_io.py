"""Read the existing bridge packet without ROS or model dependencies."""
import struct
import time

def read_packet(path, previous=0, max_age=3):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) < 16:
        return None
    stamp, width, height = struct.unpack('<dII', data[:16])
    if (width, height) != (320, 240) or len(data) != 16 + width * height * 3:
        return None
    if stamp <= previous or not -0.5 <= time.time() - stamp <= max_age:
        return None
    return stamp, width, height, data[16:]
