"""Cache and warm up mapping models while online. Normal flights never download."""
import json,time
from pathlib import Path
import numpy as np
from room_models import IndoorDepth,RoomStructure,ROOT

if __name__=='__main__':
    import torch
    torch.set_num_threads(2)
    import open3d
    frame=np.zeros((240,320,3),np.uint8)
    for cls in [IndoorDepth,RoomStructure]:
        start=time.monotonic();model=cls(download=True);model.predict(frame)
        print(f'{cls.__name__}: cached and forward pass passed on {model.device} ({time.monotonic()-start:.1f}s including loading)',flush=True)
    marker=ROOT/'vision/models/mapping-ready.json'
    marker.write_text(json.dumps({'prepared':time.time(),'depth':'metric-indoor-small','structure':'segformer-b0','open3d':open3d.__version__}))
    print('Mapping models ready. Metric predictions still need measured-room validation.',flush=True)
