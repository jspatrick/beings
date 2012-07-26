"""
import beings.tests
reload(beings.tests)
beings.tests.runTests('TestNodeTag')
"""

import unittest, sys

import maya.cmds as MC

import core
reload(core)
import control
reload(control)
import nodeTag
reload(nodeTag)

class TestDefaultControl(unittest.TestCase):
    def setUp(self):
        MC.file(newFile=1, f=1)
        
        
    def test_returnType(self):
        ctl = control.makeControl('myControl')
        self.assertTrue(isinstance(ctl, basestring))

    def test_useExistingNode(self):
        name = 'myControl'
        self.assertEqual(MC.createNode('transform', name='myControl'), name)

        start = len(MC.ls(type='transform'))
        ctl = control.makeControl(name)
        self.assertEqual(ctl, name)
        self.assertEqual(start, len(MC.ls(type='transform')))
        
    def test_createJointType(self):
        ctl = control.makeControl('test', xformType='joint')
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

class TestNodeTag(unittest.TestCase):
    def setUp(self):
        MC.file(newFile=1, f=1)        
        self.xform = MC.createNode('transform', name='test')

    def testTagPrefix(self):
        tagName = 'someGreatTag'
        self.assertEqual(nodeTag.getTagAttr(tagName), 'beingsTag_someGreatTag')
        tagName = 'beingsTag_someGreatTag'
        self.assertEqual(nodeTag.getTagAttr(tagName), 'beingsTag_someGreatTag')
        
    def testSetTag(self):
        tagName = 'someGreatTag'
        tagAttr = nodeTag.getTagAttr(tagName)        
        
        nodeTag.setTag(self.xform, tagName, {})        
        self.assertTrue(MC.attributeQuery(tagAttr, n=self.xform, ex=1))
        
    def testHasTag(self):
        tagName = 'someGreatTag'
        tagAttr = nodeTag.getTagAttr(tagName)

        self.assertFalse(nodeTag.hasTag(self.xform,tagName))
        self.assertFalse(nodeTag.hasTag(self.xform,tagAttr))

        nodeTag.setTag(self.xform, tagName, {})
        
        self.assertTrue(nodeTag.hasTag(self.xform,tagName))
        self.assertTrue(nodeTag.hasTag(self.xform,tagAttr))

    def testGetTag(self):
        tagName = 'someGreatTag'
        tagAttr = nodeTag.getTagAttr(tagName)

        self.assertRaises(RuntimeError, nodeTag.getTag, self.xform, tagName)
        self.assertEqual(nodeTag.getTag(self.xform, tagName, noError=True), {})

        val = {'test': 'x'}
        
        nodeTag.setTag(self.xform, tagName, val)
        self.assertEqual(nodeTag.getTag(self.xform, tagName), val)
        
    def testValidTags(self):
        tagName = 'someGreatTag'
        tagAttr = nodeTag.getTagAttr(tagName)        
        
        validValues = {'string': 'aStr',
                       'int': 5,
                       'float': 5.5,
                       'list': ['x', 5, 5.5],
                       'dict': {'s': 'x', 'i': 5, 'f': 5.5},
                       'tuple': ('x', 5, 5.5),
                       'set': set(['x', 5, 5.5])}

        nodeTag.setTag(self.xform, tagName, validValues)
        

        gottenTag = nodeTag.getTag(self.xform, tagName)
        
        for k, v in validValues.items():
            self.assertEqual(v, gottenTag[k])
        
          
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

        
        
        
def runTests(*args):
    module = sys.modules[__name__]

    suite = unittest.TestLoader().loadTestsFromNames(args,
                                                     module=sys.modules[__name__])
    
    unittest.TextTestRunner(verbosity=2).run(suite)

    
