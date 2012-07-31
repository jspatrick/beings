"""
import beings.tests
reload(beings.tests)
beings.tests.runTests('TestNodeTag')
beings.tests.runTests('TestStorableXform')
"""

import unittest, sys

import maya.cmds as MC

import core
reload(core)
import control
reload(control)
import nodeTag
reload(nodeTag)

class TestControl(unittest.TestCase):
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

    def test_connectedEditNodeSucceeds(self):
        """Test that connections can be made to an editable node"""
        ctl = control.makeControl("test")
        pp = MC.pointPosition('%s.cv[0]' % ctl)

        control.setEditable(ctl, True)
        editor = control.getEditor(ctl)

        s = MC.spaceLocator()[0]
        MC.connectAttr('%s.tx' % s, '%s.tx' % editor)
        MC.connectAttr('%s.rx' % s, '%s.rx' % editor)
        MC.connectAttr('%s.sx' % s, '%s.sx' % editor)
        MC.setAttr('%s.tx' % s, 5)
        MC.setAttr('%s.rx' % s, 5)
        MC.setAttr('%s.sx' % s, 5)

        control.setEditable(ctl, False)
        ppPost = MC.pointPosition('%s.cv[0]' % ctl)

        self.assertNotEqual(pp[0], ppPost[0])
        self.assertNotEqual(pp[1], ppPost[1])
        self.assertNotEqual(pp[2], ppPost[2])

class TestStorableXform(unittest.TestCase):
    def setUp(self):
        MC.file(newFile=1, f=1)

    def test_makeStorableXform(self):
        xform = control.makeStorableXform('myXform_a')
        xform2 = control.makeStorableXform('myXform_b', nodeType='joint')
        xform3 = control.makeStorableXform('myXform_c', nodeType='joint', parent=xform2)
        
    def test_makeStorableXformCtl(self):
        xform1 = control.makeStorableXform('myXform_a')
        xform2 = control.makeStorableXform('myXform_b', nodeType='joint')
        xform3 = control.makeStorableXform('myXform_c', nodeType='joint', parent=xform2)
        control.makeControl(xform1)
        control.makeControl(xform2)
        control.makeControl(xform3)

        info1 = control.getStorableXformInfo(xform1)
        info2 = control.getStorableXformInfo(xform2)
        info3 = control.getStorableXformInfo(xform3)

        MC.delete(xform1)
        MC.delete(xform2)

        control.makeStorableXform(xform1, **info1)
        control.makeStorableXform(xform2, **info2)
        control.makeStorableXform(xform3, **info3)

    def test_getXformArgs(self):
        xform = control.makeStorableXform('myXform')
        t = [1,2,3]
        r = [10,20,30]
        s = [1.1, 2.2, 3.3]

        MC.setAttr('%s.t' % xform, *t, type='double3')
        MC.setAttr('%s.r' % xform, *r, type='double3')
        MC.setAttr('%s.s' % xform, *s, type='double3')

        result = control.getStorableXformInfo(xform)

        xform2 = control.makeStorableXform('myXform2', **result)
        for i in range(3):
            self.assertTrue(MC.getAttr('%s.t' % xform2)[0][i] - tuple(t)[i] < .0001)
            self.assertTrue(MC.getAttr('%s.r' % xform2)[0][i] - tuple(r)[i] < .0001)
            self.assertTrue(MC.getAttr('%s.s' % xform2)[0][i] - tuple(s)[i] < .0001)

    def test_worldSpaceArgs(self):
        xform = control.makeStorableXform('myXform')
        t = [1,2,3]
        r = [10,20,30]
        s = [1.1, 2.2, 3.3]

        MC.setAttr('%s.t' % xform, *t, type='double3')
        MC.setAttr('%s.r' % xform, *r, type='double3')
        MC.setAttr('%s.s' % xform, *s, type='double3')

        xform2 = control.makeStorableXform('myXform_b', parent=xform, worldSpace=True)
        MC.setAttr('%s.t' % xform2, *t, type='double3')
        MC.setAttr('%s.r' % xform2, *r, type='double3')
        MC.setAttr('%s.s' % xform2, *s, type='double3')

        result = control.getStorableXformInfo(xform2)

        xform3 = control.makeStorableXform('myXform2', **result)
        for i in range(3):
            self.assertTrue(MC.getAttr('%s.t' % xform3)[0][i] - tuple(t)[i] < .0001)
            self.assertTrue(MC.getAttr('%s.r' % xform3)[0][i] - tuple(r)[i] < .0001)
            self.assertTrue(MC.getAttr('%s.s' % xform3)[0][i] - tuple(s)[i] < .0001)

    def test_worldSpaceArgsExisting(self):
        xform = control.makeStorableXform('myXform')
        t = [1,2,3]
        r = [10,20,30]
        s = [1.1, 2.2, 3.3]

        MC.setAttr('%s.t' % xform, *t, type='double3')
        MC.setAttr('%s.r' % xform, *r, type='double3')
        MC.setAttr('%s.s' % xform, *s, type='double3')

        xform2 = control.makeStorableXform('myXform_b', parent=xform, worldSpace=True)
        MC.setAttr('%s.t' % xform2, *t, type='double3')
        MC.setAttr('%s.r' % xform2, *r, type='double3')
        MC.setAttr('%s.s' % xform2, *s, type='double3')

        result = control.getStorableXformInfo(xform2)
        MC.createNode('transform', name='myXform_c')
        xform3 = control.makeStorableXform('myXform_c', **result)
        for i in range(3):
            self.assertTrue(MC.getAttr('%s.t' % xform3)[0][i] - tuple(t)[i] < .0001)
            self.assertTrue(MC.getAttr('%s.r' % xform3)[0][i] - tuple(r)[i] < .0001)
            self.assertTrue(MC.getAttr('%s.s' % xform3)[0][i] - tuple(s)[i] < .0001)

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
