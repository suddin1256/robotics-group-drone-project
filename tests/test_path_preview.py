import itertools,unittest
from mapping.path_preview import plan_preview

class PathPreviewTests(unittest.TestCase):
    def grid(self):return {'units':'arbitrary','cells':[{'cell':p,'state':'free_candidate'} for p in itertools.product(range(8),range(5),range(5))]}
    def test_route_and_unknown_clearance(self):
        result=plan_preview(self.grid(),[1,2,2],[6,2,2],1)
        self.assertEqual(result['cells'][0],(1,2,2));self.assertFalse(result['autonomous_allowed'])
        with self.assertRaises(ValueError):plan_preview(self.grid(),[0,2,2],[6,2,2],1)
    def test_wall_blocks_path(self):
        grid=self.grid()
        for cell in grid['cells']:
            if cell['cell'][0]==4:cell['state']='occupied_candidate'
        with self.assertRaises(ValueError):plan_preview(grid,[1,2,2],[6,2,2],1)
