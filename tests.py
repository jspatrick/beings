#control
import maya.cmds as MC
import core as core
from utils.Naming import Namer
reload(core)
import unittest


class TestCoreJointMethods(unittest.TestCase):
    
    def setUp(self):
        MC.file(newFile=1, f=1)
        MC.select(cl=1)
        names = ['hip', 'knee', 'ankle']
        
        jnts = {}
        for i in range(3):
            jnt = MC.joint(p=[0,i * 2, 0], name='jnt_%i' % i)
            jnts[names[i]] = jnt
            
        self.names = names
        self.jnts = jnts

        self.namer = Namer(c='testchar', side='lf', part='leg')
        
    def test_duplicateJoints(self):
        
        result = core.duplicateBindJoints(self.jnts, namer)
        
        
        
def runTests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCoreJointMethods)
    unittest.TextTestRunner(verbosity=2).run(suite)

    
