import unittest

import maya.cmds as MC

import core
reload(core)
import control
reload(control)


class TestDefaultControl(unittest.TestCase):
    def setUp(self):
        MC.file(newFile=1, f=1)
        
        
    def test_returnType(self):
        ctl = control.makeControl('myControl')
        self.assertIsInstance(ctl, basestring)

    def test_useExistingNode(self):
        name = 'myControl'
        self.assertEqual(MC.createNode('transform', name='myControl'), name)

        start = len(MC.ls())
        ctl = control.makeControl(name)
        self.assertEqual(ctl, name)
        self.assertEqual(start, len(MC.ls()))
        
    def test_createJointType(self):
        clt = control.makeControl('test', xformType='joint')
        self.assertTrue(MC.objectType(ctl, isAType='joint'))

    def test_existingNodeMaintainsType(self):
        name = 'myControl'
        node = MC.createNode('joint', name=name)
        ctl = control.makeControl(name)
        self.assertTrue(MC.objectType(ctl, isType='joint'))
        MC.delete(ctl)

        node = MC.createNode('transform', name=name)
        ctl = control.makeControl(name)
        self.assertTrue(MC.objectType(ctl, isType='transform'))
        
    def test_typeConversionRaisesError(self):        
        node = control.makeControl('test')
        
class TestControlDiffs(unittest.TestCase):
    def setUp(self):
        MC.file(newFile=1, f=1)

class TestNodeTagging(unittest.TestCase):
    def setUp(self):
        MC.file(newFile=1, f=1)

class TestNaming(unittest.TestCase):
    pass

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

    
