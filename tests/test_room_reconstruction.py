import importlib.util,json,tempfile,unittest
import os
from pathlib import Path
try:
    import numpy as np
    import cv2
except ImportError:
    np=None
if np is not None:
    spec=importlib.util.spec_from_file_location('room_reconstruction',Path(__file__).resolve().parents[1]/'scripts/rebuild_room_map.py')
    roommap=importlib.util.module_from_spec(spec);spec.loader.exec_module(roommap)

@unittest.skipIf(np is None,'Requires the vision environment (numpy and OpenCV)')
class ReconstructionTests(unittest.TestCase):
    def test_later_bridge_capture_links_previously_unmatched_flight(self):
        rng=np.random.default_rng(12);points=rng.normal(size=(60,3));descs=rng.integers(0,256,(60,32),dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            entries=[('a',points[:30],descs[:30]),('b',points[30:]*3+[4,2,1],descs[30:]),('c',points*2+[1,3,2],descs)]
            for i,(name,p,d) in enumerate(entries):
                folder=root/'maps'/name;folder.mkdir(parents=True);file=folder/'map.json'
                file.write_text(json.dumps({'points':p.tolist(),'landmark_descriptors':d.tolist(),'cameras':[]}));os.utime(file,(100+i,100+i))
            roommap.rebuild(root);result=json.loads((root/'room-map.json').read_text())
            self.assertEqual(result['aligned_maps'],3);self.assertEqual(result['separate_maps'],0)
    def test_registration_and_persistent_rebuild(self):
        rng=np.random.default_rng(42);points=rng.normal(size=(80,3));descs=rng.integers(0,256,(80,32),dtype=np.uint8)
        angle=.4;rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        target=2*points@rotation.T+[3,1,-2]
        transform,reason=roommap.registration(points,target,descs,descs)
        self.assertIsNone(reason);self.assertAlmostEqual(transform['scale'],2,places=6)
        np.testing.assert_allclose(transform['rotation'],rotation,atol=1e-6)
        rejected,_=roommap.registration(points,rng.normal(size=(80,3)),descs,descs);self.assertIsNone(rejected)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,cloud in [('a',target),('b',points)]:
                folder=root/'maps'/name;folder.mkdir(parents=True)
                (folder/'map.json').write_text(json.dumps({'points':cloud.tolist(),'landmark_descriptors':descs.tolist(),'cameras':[],'map_origin':name}))
            roommap.rebuild(root);first=json.loads((root/'room-map.json').read_text());roommap.rebuild(root);second=json.loads((root/'room-map.json').read_text())
            self.assertEqual(first['aligned_maps'],2);self.assertEqual(first['points'],second['points']);self.assertEqual(first['anchor_id'],second['anchor_id'])
            self.assertTrue(any(p[3]==2 for p in first['points']))
    def test_missing_descriptors_keeps_captures_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);points=np.random.default_rng(2).normal(size=(30,3)).tolist()
            for name in ['a','b']:
                folder=root/'maps'/name;folder.mkdir(parents=True);(folder/'map.json').write_text(json.dumps({'points':points,'cameras':[]}))
            roommap.rebuild(root);result=json.loads((root/'room-map.json').read_text())
            self.assertEqual(result['aligned_maps'],1);self.assertEqual(result['separate_maps'],1)

if __name__=='__main__':unittest.main()
