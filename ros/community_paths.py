"""Load the local ROS overlay without modifying the user's base environment."""
import ctypes
import os
from pathlib import Path
import sys

def configure():
    prefix=Path(__file__).resolve().parents[1]/'local/community'
    os.environ['AMENT_PREFIX_PATH']=str(prefix)+os.pathsep+os.environ.get('AMENT_PREFIX_PATH','')
    for site in (prefix/'lib').glob('python*/site-packages'):
        sys.path.insert(0,str(site))
    # RoboStack/macOS resolves type support by bare library name. Preloading our
    # absolute paths makes these discoverable even when Pixi resets loader paths.
    for pattern in ['libtello_msgs__rosidl_typesupport*.dylib','libtello_msgs__rosidl_typesupport*.so']:
        for library in sorted((prefix/'lib').glob(pattern)):
            ctypes.CDLL(str(library))
