import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
try:
 import numpy as np
 from pose_fusion import blend_position
except ImportError:np=None

@unittest.skipIf(np is None,'Requires numpy')
class PoseFusionChecks(unittest.TestCase):
 def blend(self,**kwargs):
  d=dict(telemetry=[0,0,0],visual=[.1,0,0],age_ms=20,speed_m_s=.4,support=40,reprojection_px=.5,alignment_error_m=.03,gate_m=.3);d.update(kwargs);return blend_position(**d)
 def test_stale_outlier_or_weak_vision_is_not_averaged_in(self):
  for kwargs in [dict(age_ms=500),dict(visual=[4,0,0]),dict(support=5),dict(reprojection_px=8),dict(visual=[float('nan'),0,0])]:self.assertIsNone(self.blend(**kwargs)[0])
 def test_weights_adapt_and_position_stays_between_inputs(self):
  a,_=self.blend();b,_=self.blend(age_ms=300)
  self.assertLess(b['telemetry_weight'],a['telemetry_weight'])
  self.assertGreater(a['position'][0],0);self.assertLess(a['position'][0],.1)
  self.assertAlmostEqual(a['telemetry_weight']+a['visual_weight'],1.)
 def test_quality_is_not_confidence_probability(self):
  a,_=self.blend();self.assertIn('heuristic',a['quality_basis'])
