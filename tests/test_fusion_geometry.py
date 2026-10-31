from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
try:
    import numpy as np
    from fusion_geometry import fit_similarity,fit_inverse_depth,native_sample,orientation_alignment
    from fused_floorplan import frame_geometry
except ImportError:
    np=None

@unittest.skipIf(np is None,'Run with the vision Python environment for numerical fusion checks')
class FusionGeometryTests(unittest.TestCase):
    def test_similarity_recovers_scale_and_axes_with_outliers(self):
        rng=np.random.default_rng(2);x=rng.normal(size=(40,3))
        r=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
        y=2*x@r.T+[10,20,30];y[-5:]+=100
        fit=fit_similarity(x,y)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit['scale'],2.,places=6)
        np.testing.assert_allclose(fit['rotation'],r,atol=1e-6)
        self.assertEqual(fit['inliers'].sum(),35)

    def test_degenerate_motion_does_not_invent_alignment(self):
        x=np.array([[i,0,0] for i in range(12)],float)
        self.assertIsNone(fit_similarity(x,x))
        self.assertIsNone(fit_similarity(np.zeros((12,3)),np.zeros((12,3))))

    def test_relative_inverse_depth_needs_support_and_positive_relation(self):
        signal=np.linspace(1,5,50);z=1/(.2*signal+.1)
        fit=fit_inverse_depth(signal,z)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit['a'],.2,places=6)
        self.assertAlmostEqual(fit['b'],.1,places=6)
        self.assertIsNone(fit_inverse_depth(signal[:5],z[:5]))
        self.assertIsNone(fit_inverse_depth(signal,z[::-1]))

    def test_stale_motion_and_different_frames_are_rejected(self):
        meta={'log':{'valid':False}}
        self.assertIsNone(native_sample(meta))
        result=frame_geometry({'source_stamp':1.},{'source_stamp':2.},None,meta,{},None,None)
        self.assertEqual(result[2]['rejected'],'different image frames')

    def test_stationary_orientation_does_not_invent_extrinsics(self):
        self.assertIsNone(orientation_alignment([np.eye(3)]*10,[np.eye(3)]*10,np.eye(3)))

    def test_all_sources_contribute_and_telemetry_moves_object_position(self):
        import cv2
        from fused_floorplan import K,D
        rng=np.random.default_rng(8)
        uv=np.column_stack([rng.integers(60,260,60),rng.integers(60,180,60)]).astype(float)
        yy,xx=np.mgrid[:240,:320]
        depth=(2+np.sin(xx/55)+np.cos(yy/40)).astype(np.float32)
        values=depth[uv[:,1].astype(int),uv[:,0].astype(int)]
        z=1/(.2*values+.1)
        rays=cv2.undistortPoints(uv.reshape(-1,1,2),K,D).reshape(-1,2)
        points=np.column_stack([rays,np.ones(len(rays))])*z[:,None]
        coordinates=dict(enumerate(points))
        obs={'source_stamp':1.,'camera_to_world':np.eye(4).tolist(),
             'features':[[i,*p] for i,p in enumerate(uv)]}
        detection={'source_stamp':1.,'objects':[{'label':'table','polygon':[[50,50],[270,50],[270,190],[50,190]]}]}
        meta={'image_stamp_ns':1_000_000_000,'log':{'valid':True,'age_ms':5,
              'sample':{'data':{'mvo':{'count':1,'pos_x':10.,'pos_y':20.,'pos_z':30.},
                                'imu':{'count':1,'q0':1.,'q1':0.,'q2':0.,'q3':0.}}}}}
        rotation=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
        fit={'scale':2.,'rotation':rotation,'translation':np.array([10.,20.,30.]),'error':.01,'spread':10.}
        orientation={'offset':rotation,'transpose':False}
        cs,surface,quality=frame_geometry(obs,detection,depth,meta,coordinates,fit,orientation)
        self.assertTrue(cs and cs[0]['depth'] and cs[0]['imu'])
        self.assertGreater(len(surface),100)
        self.assertGreaterEqual(quality['depth_fit']['support'],16)
        meta['log']['sample']['data']['mvo']['pos_x']+=.2
        moved,_,_=frame_geometry(obs,detection,depth,meta,coordinates,fit,orientation)
        self.assertAlmostEqual(float(np.mean(moved[0]['points'][:,0]-cs[0]['points'][:,0])),.2,places=5)

if __name__=='__main__':unittest.main()
