import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
try:
    import cv2,numpy as np
    from dense_reconstruction import pose_and_depth,transformed_frame,reconstruct
    from room_models import doorway_candidates
except ImportError:np=None

@unittest.skipIf(np is None,'Requires vision dependencies')
class DenseChecks(unittest.TestCase):
    def fixture(self):
        k=np.array([[220.,0,160],[0,220,120],[0,0,1]])
        yy,xx=np.mgrid[0:240,0:320];depth=(2+xx*.002+yy*.001+np.sin(xx/60)*.1).astype(np.float32)
        features=[];coordinates={}
        for i,(x,y) in enumerate([(x,y) for x in range(25,300,25) for y in range(25,220,25)]):
            z=depth[y,x];coordinates[i]=[(x-160)/220*z,(y-120)/220*z,float(z)];features.append([i,x,y])
        return k,depth,coordinates,{'features':features,'camera_to_world':np.eye(4).tolist(),'source_stamp':1.,'map_origin':1.}
    def test_current_landmarks_recover_pose_and_depth(self):
        k,depth,coordinates,obs=self.fixture()
        fit,reason=pose_and_depth(obs,coordinates,1/depth,depth,k,np.zeros(5))
        self.assertIsNone(reason);self.assertLess(fit['fit_error'],.01)
        np.testing.assert_allclose(fit['pose'],np.eye(4),atol=1e-4)
        self.assertGreater(np.count_nonzero(fit['depth']),10000)
        bad,_=pose_and_depth(obs,coordinates,np.random.default_rng(4).random(depth.shape).astype(np.float32),None,k,np.zeros(5));self.assertIsNone(bad)
    def test_similarity_scales_camera_translation_and_ranges(self):
        pose=np.eye(4);pose[:3,3]=[1,2,3]
        output,depth=transformed_frame(pose,np.ones((2,2)),{'scale':2,'rotation':np.eye(3),'translation':[3,0,0]})
        np.testing.assert_allclose(output[:3,3],[5,4,6]);np.testing.assert_allclose(depth,2)
    def test_door_state_is_tentative_and_invalid_depth_unknown(self):
        frame=np.zeros((240,320,3),np.uint8);labels=np.zeros((240,320),np.uint8);labels[30:210,100:200]=14
        confidence=np.ones((240,320),np.float32)
        doors=doorway_candidates(frame,labels,confidence,np.full((240,320),np.nan))
        self.assertTrue(doors);self.assertEqual(doors[0]['state'],'unknown');self.assertFalse(doors[0]['traversable'])
        doors=doorway_candidates(frame,labels,confidence,np.full((240,320),2.))
        self.assertEqual(doors[0]['state'],'possibly closed');self.assertFalse(doors[0]['verified'])
    @unittest.skipUnless(importlib.util.find_spec('open3d'),'Requires Open3D')
    def test_tsdf_exports_mesh_and_keeps_planning_blocked(self):
        k,depth,coordinates,obs=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);capture=root/'maps/a';capture.mkdir(parents=True);live=root/'sessions/a/runtime/live';live.mkdir(parents=True)
            assets=live.parent/'assets';assets.mkdir();(assets/'tello_320_dense.yaml').write_text('fx: 220\nfy: 220\ncx: 160\ncy: 120\ncols: 320\nrows: 240\n')
            (capture/'source.json').write_text(json.dumps({'live':str(live)}));(live/'observations').mkdir();(live/'depth-frames').mkdir()
            (live/'observations/1000000.json').write_text(json.dumps(obs))
            np.savez_compressed(live/'depth-frames/1000000.npz',depth=1/depth,metric_depth=depth,source_stamp=1.,rgb=np.full((240,320,3),150,np.uint8))
            data={'landmark_ids':list(coordinates),'points':list(coordinates.values()),'map_origin':1.}
            result,_=reconstruct(root,[(capture,data,{'scale':1.,'rotation':np.eye(3),'translation':np.zeros(3)})],.04)
            self.assertEqual(result['integrated_frames'],1,result['rejected']);self.assertGreater(result['triangles'],0);self.assertFalse(result['planning_ready'])
            self.assertTrue((root/'room-mesh.ply').exists())
            cells=json.loads((root/'occupancy.json').read_text());self.assertFalse(cells['planning_ready'])
            # Losing all usable poses replaces the displayed mesh with empty geometry.
            result,_=reconstruct(root,[],.04);self.assertEqual(result['integrated_frames'],0)
            self.assertEqual(json.loads((root/'room-mesh.json').read_text())['vertices'],[])

if __name__=='__main__':unittest.main()
