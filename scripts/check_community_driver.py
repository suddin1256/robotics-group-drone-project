"""ROS serialization smoke test with a mocked radio: NEVER connects or flies."""
from pathlib import Path
import os
import sys
import time
from unittest.mock import MagicMock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ros'))
os.environ['TELLO_RUNTIME_DIR']=str(ROOT/'.tmp/community-check')
import rclpy
import numpy as np
from std_msgs.msg import String
from tellopy._internal.protocol import FlightData, LogData
from community_driver import CommunityFlight

rclpy.init()
radio=MagicMock()
radio.fast_mode=False
node=None
try:
    with patch('tello_manual_launch.tellopy.Tello',return_value=radio):
        node=CommunityFlight(False)
    import inspect
    flight=FlightData(time.monotonic(),bytes(24)) if len(inspect.signature(FlightData).parameters)>1 else FlightData(bytes(24))
    flight.battery_percentage=61
    node.receive_state(None,None,flight)
    node._flight_data_callback(None,None,flight)
    log=LogData(None)
    log.imu.q0=1.
    log.mvo.vel_x,log.mvo.vel_y,log.mvo.vel_z=1.,2.,3.
    log.records=[log.imu,log.mvo]
    node._log_data_callback(None,None,log)
    node.receive_packet(None,None,b'\x01\x02',recv_time=time.monotonic())
    request=String();request.data='{"dry_run":false,"sent_stamp_ns":'+str(time.time_ns())+',"rc":[0,0,0,0],"actions":[],"input_fresh":false,"launch_surface":"table","table_height_cm":91}'
    node.receive_control(request)
    assert node.launch_surface=='table' and node.table_height_cm==91
    node.phase='airborne'
    changed=String();changed.data=request.data.replace('"table"','"ground"')
    node.receive_control(changed)
    assert node.launch_surface=='table', 'Launch reference must remain frozen in flight'
    node.phase='grounded'
    node.frame=np.zeros((480,640,3),dtype=np.uint8)
    node.frame_stamp_ns=time.time_ns();node.frame_sequence=1
    node.publish_image();node.publish_status();node.publish_inventory()
    import json
    data=json.loads((node.folder/'image-metadata.json').read_text())
    assert data['log']['valid'] and data['image_stamp_ns']==node.frame_stamp_ns
    assert data['launch_surface']=='table'
    assert not radio.connect.called and not radio.manual_takeoff.called and not radio.takeoff.called
    print('PASS: real ROS messages, raw logs, frame association and table setting; radio mocked throughout.')
finally:
    if node is not None:node.close();node.destroy_node()
    rclpy.shutdown()
