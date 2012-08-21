"""
import maya.cmds as MC
import beings.widgets.fkChain as FKC

MC.file(new=1, f=1)
reload(FKC)
fkc = FKC.Neck()
fkc.buildLayout()
"""
from string import ascii_lowercase
import maya.cmds as MC
import maya.mel as MM
import maya.OpenMaya as OM

import beings.core as core
import logging
from beings.widgets.spine import *

from beings import control
from beings import utils

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)


class HeadNeck(core.Widget):
    def __init__(self):
        super(HeadNeck, self).__init__('neck')
        self.options.addOpt('numNeckBones', 2, min=1, optType=int)
        self.options.addOpt('numIkCtls', 2, min=1, optType=int)
        self.options.subscribe('optChanged', self.__optionChanged)
        self.__setPlugs()

    def __setPlugs(self):
        newPlugs = set(self.__getToks()[:-1])
        currentPlugs = set([x for x in self.plugs()])
        toRemove = currentPlugs.difference(newPlugs)
        toAdd = newPlugs.difference(currentPlugs)
        _logger.debug("Adding plugs: %s; Removing plugs: %s" % (toAdd, toRemove))

        for plug in toRemove:
            self.rmPlug(plug)
        for plug in toAdd:
            self.addPlug(plug)


    def __optionChanged(self, event):
        if event.optName != 'numNeckBones':
            return
        self.__setPlugs()


    def __getToks(self):
        toks = []
        for i in range(self.options.getValue('numNeckBones')):
            toks.append('neck_%s' % ascii_lowercase[i])
        toks.extend(['head', 'head_tip'])
        return toks


    def _makeLayout(self, namer):
        neckJntCnt =  self.options.getValue('numNeckBones')

        MC.select(cl=1)
        jnts = []
        layoutCtls= []
        rigCtls = []

        #the number of ik controls will really be 1 greater than this, because
        #we will parent the first ik control the the first fk control and hide
        #it
        numIkCtls = self.options.getValue('numIkCtls') + 1
        numJnts = self.options.getValue('numNeckBones') + 1

        ctlKwargs = {'shape': 'sphere',
                     'color': 'purple',
                     's': [1.5, .5, 1.5]}
        doubleEndPoints=False
        if numIkCtls == 2:
            doubleEndPoints=True
        nurbsObjs = createBeingsSplineObjs(numIkCtls, numJnts, namer=namer,
                                           ctlKwargs = ctlKwargs,
                                           doubleEndPoints=doubleEndPoints)
        del ctlKwargs

        #rename & regiser joints and add a 'tip' joint
        toks = self.__getToks()
        jnts = []
        for i, jnt in enumerate(nurbsObjs['jnts']):
            jnt = MC.rename(jnt, namer(toks[i], r='bnd'))
            jnts.append(jnt)
            self.registerBindJoint(jnt)

        tipXform = MC.xform(jnts[-1], q=1, t=1, ws=1)
        tipXform[1] = tipXform[1] + 2
        MC.select(jnts[-1])
        tip = MC.joint(p=tipXform,
                 n=namer(toks[-1], r='bnd'))
        jnts.append(tip)
        self.registerBindJoint(tip)

        bindNodesToSurface(jnts[:-1], nurbsObjs['surface'], skipTipOrient=True)
        #MC.orientConstraint(nurbsObjs['ikCtls'][-1], jnts[-2])


        ikRigCtls = []
        for i, ctl in enumerate(nurbsObjs['ikCtls']):
            self.registerControl(ctl, 'layout')
            if i > 0:
                kwargs = {'color': 'red',
                          'shape': 'sphere'}
                if i < (numIkCtls-1):
                    n = namer('ctl', r='ik', alphaSuf=i-1)
                else:
                    n = namer('head_ctl', r='ik')
                rigCtl = control.makeControl(n, **kwargs)
                MC.parent(rigCtl, ctl)
                MC.makeIdentity(rigCtl, t=1, r=1, s=1)
                control.setEditable(rigCtl, True)
                self.registerControl(rigCtl, 'rig')
                ikRigCtls.append(rigCtl)

        control.centeredCtl(jnts[-2], jnts[-1], ikRigCtls[-1])

        rigCtls = []
        for i, tok in enumerate(toks):

            if tok != 'head_tip':
                kwargs = {'color':'green',
                          'shape':'cube',
                          's': [2,2,2]}

                rigCtl = control.makeControl(namer(tok, r='fk'), **kwargs)
                self.registerControl(rigCtl, 'rig')
                rigCtls.append(rigCtl)
                utils.snap(jnts[i], rigCtl)
                MC.parent(rigCtl, jnts[i])

                control.centeredCtl(jnts[i], jnts[i+1], rigCtl)
                control.setEditable(rigCtl, True)

        #make a tip joint control
        tipCtl = control.makeControl(namer('tip_layout'),
                                     shape='cube',
                                     s=[.35, .35, .35],
                                     color='blue')
        utils.snap(jnts[-1], tipCtl)
        MC.parent(tipCtl, nurbsObjs['ikCtls'][-1])
        self.registerControl(tipCtl, 'layout')
        MC.pointConstraint(tipCtl, jnts[-1])
        MC.aimConstraint(tipCtl, jnts[-2],
                         aimVector = [0,1,0],
                         upVector = [1,0,0],
                         worldUpVector=[1,0,0])


        return

        for i, tok in enumerate(self.__getToks()):
            ctlKwargs = {'color': 'yellow',
                         'shape': 'sphere',
                         's': [.5, .5, .5]}

            if tok == 'head_tip':
                ctlKwargs['shape'] = 'cube'
                ctlKwargs['s'] = [.35, .35, .35]
                ctlKwargs['color'] = 'blue'

                jnt = MC.joint(p=[0,i*2+2, 0], n=namer(tok, r='bnd'))
            else:
                jnt = MC.joint(p=[0,i*2, 0], n=namer(tok, r='bnd'))

            if tok == 'head':
                ctlKwargs['shape'] = 'cube'
                ctlKwargs['s'] = [.75, .75, .75]

            self.registerBindJoint(jnt)
            jnts.append(jnt)

            layoutCtl = control.makeControl(namer('layout_%s' % tok, r='fk'),
                                            **ctlKwargs)

            self.registerControl(layoutCtl, 'layout')
            layoutCtls.append(layoutCtl)
            utils.snap(jnt, layoutCtl)


            if tok != 'head_tip':
                kwargs = {'color':'green',
                          'shape':'circle'}

                if tok == 'head':
                    kwargs['shape'] = 'sphere'

                rigCtl = control.makeControl(namer(tok, r='fk'), **kwargs)
                self.registerControl(rigCtl, 'rig')
                rigCtls.append(rigCtl)
                utils.snap(jnt, rigCtl)
                MC.parent(rigCtl, jnt)


            if tok != 'head_tip':
                MC.setAttr("%s.tx" % layoutCtl, l=1)

            MC.select(jnt)



        MC.parent(layoutCtls[-1], layoutCtls[-2])
        return

    def _makeRig(self, namer):

        neckJntCnt =  self.options.getValue('numNeckBones') + 1
        ikCtlCnt =  self.options.getValue('numIkCtls')
        toks = self.__getToks()
        bndJnts = [namer(t, r='bnd') for t in toks]

        MC.makeIdentity(bndJnts, apply=True, r=1, t=1, s=1)

        namer.setTokens(r='fk')
        #fkJnts = utils.dupJntList(bndJnts, toks, namer)

        fkCtls = [namer(t, r='fk') for t in toks[:-1]]
        fkCtls = control.setupFkCtls(bndJnts[:-1], fkCtls, toks[:-1], namer)

        for i, tok in enumerate(toks[:-1]):
            self.setPlugNode(tok, fkCtls[i])

        namer.setTokens(r='ik')
        ikJnts = utils.dupJntList(bndJnts, toks, namer)
        MC.setAttr('%s.v' % ikJnts[0], 0)

        ikCtls = []
        for i in range(ikCtlCnt):
            if i < (ikCtlCnt-1):
                n = namer('ctl', r='ik', alphaSuf=i)
                utils.insertNodeAbove(n)
            else:
                n = namer('head_ctl', r='ik')
            ikCtls.append(n)


        baseIkCtl = MC.createNode('transform', n=namer('base', r='ik'))
        utils.snap(bndJnts[0], baseIkCtl, orient=False)
        ikCtls.insert(0, baseIkCtl)

        tmp = MC.createNode('transform', n="TMP")
        utils.parentShape(tmp, ikCtls[-1], deleteChildXform=False)
        utils.snap(bndJnts[-2], ikCtls[-1])
        utils.parentShape(ikCtls[-1], tmp)
        utils.insertNodeAbove(ikCtls[-1])

        #doubling the cvs on the end allows us to build a curve with only 2 controls,
        #but causes popping otherwise.  Only use if needed
        doubleEndPoints = False
        if ikCtlCnt == 1:
            doubleEndPoints = True

        crv = curveFromNodes(ikCtls, name=namer('ikspline_crv'), doubleEndPoints=doubleEndPoints )
        srf = surfaceFromNodes(ikCtls, name=namer('ikspline_srf'), doubleEndPoints=doubleEndPoints)

        bindControlsToShape(ikCtls, crv,  doubleEndPoints=doubleEndPoints)
        bindControlsToShape(ikCtls, srf,  doubleEndPoints=doubleEndPoints)

        ikNode = setupSpineIkNode(ikCtls, ikJnts[:-1], nodeName='splinik', namer=namer,
                         crv=crv, surf=srf)
        self.setNodeCateogry(ikNode, 'dnt')
        MC.setAttr("%s.v" % ikNode, 0)
        #tag this node so the master connect the uniform scale
        core.Root.tagInputScaleAttr(ikNode, 'inputScaleAmt')

        MC.addAttr(ikCtls[-1], ln='fkIk', dv=0, k=1, min=0, max=1)
        MC.addAttr(ikCtls[-1], ln='stretchAmt', dv=0, k=1, min=0, max=1)
        MC.addAttr(ikCtls[-1], ln='evenStretchAmt', dv=0, k=1, min=0, max=1)

        MC.connectAttr('%s.stretchAmt' % ikCtls[-1], '%s.stretchAmt' % ikNode)
        MC.connectAttr('%s.evenStretchAmt' % ikCtls[-1], '%s.evenStretchAmt' % ikNode)


        ikReverse = utils.blendJointChains(fkCtls, ikJnts[:-1], bndJnts[:-1], '%s.fkIk' % ikCtls[-1], namer)
        for ctl in fkCtls:
            MC.connectAttr('%s.outputX' % (ikReverse), '%s.v' % ctl)
        for ctl in ikCtls[1:-1]:
            MC.connectAttr('%s.fkIk' % (ikCtls[-1]), '%s.v' % ctl)

core.WidgetRegistry().register(HeadNeck, "Neck and Head", "An Fk Neck and head")
