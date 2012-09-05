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
                     's': [6.5, 1.5, 6.5]}
        doubleEndPoints=False
        if numIkCtls == 2:
            doubleEndPoints=True
        nurbsObjs = createBeingsSplineObjs(numIkCtls, numJnts, namer=namer,
                                           ctlKwargs = ctlKwargs,
                                           doubleEndPoints=doubleEndPoints, ctlSep=4)
        del ctlKwargs

        #rename & regiser joints and add a 'tip' joint
        toks = self.__getToks()
        jnts = []
        for i, jnt in enumerate(nurbsObjs['jnts']):
            jnt = MC.rename(jnt, namer(toks[i], r='bnd'))
            jnts.append(jnt)
            self.registerBindJoint(jnt)

        tipXform = MC.xform(jnts[-1], q=1, t=1, ws=1)
        tipXform[1] = tipXform[1] + 10
        MC.select(jnts[-1])
        tip = MC.joint(p=tipXform,
                 n=namer(toks[-1], r='bnd'))
        jnts.append(tip)
        self.registerBindJoint(tip)

        bindNodesToSurface(jnts[:-1], nurbsObjs['surface'], skipTipOrient=True)
        #MC.orientConstraint(nurbsObjs['ikCtls'][-1], jnts[-2])


        ikRigCtls = []
        for i, ctl in enumerate(nurbsObjs['ikCtls']):
            self.registerControl(ctl, 'layout', uk=['ty', 'tz'])
            if i > 0:
                kwargs = {'color': 'yellow',
                          'shape': 'sphere',
                          's': [2,2,2]}
                if i < (numIkCtls-1):
                    n = namer('ctl', r='ik', alphaSuf=i-1)
                else:
                    n = namer('head_ctl', r='ik')
                    kwargs['s'] = [4,1,4]

                rigCtl = control.makeControl(n, **kwargs)

                if i == (numIkCtls-1):
                    control.centeredCtl(jnts[-2], jnts[-1], rigCtl)

                MC.parent(rigCtl, ctl)
                MC.makeIdentity(rigCtl, t=1, r=1, s=1)
                control.setEditable(rigCtl, True)

                self.registerControl(rigCtl, 'rig')
                ikRigCtls.append(rigCtl)



        rigCtls = []
        for i, tok in enumerate(toks):

            if tok != 'head_tip':
                kwargs = {'color':'green',
                          'shape':'cube',
                          's': [5,1,5]}

                rigCtl = control.makeControl(namer(tok, r='fk'), **kwargs)
                self.registerControl(rigCtl, 'rig')
                rigCtls.append(rigCtl)
                utils.snap(jnts[i], rigCtl)
                MC.parent(rigCtl, jnts[i])

                #control.centeredCtl(jnts[i], jnts[i+1], rigCtl)
                control.setEditable(rigCtl, True)

        #make a tip joint control
        tipCtl = control.makeControl(namer('tip_layout'),
                                     shape='cube',
                                     s=[1,1,1],
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
        for ctl in fkCtls:
            control.setLockTag(ctl, uk=['r'])

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

        for ctl in ikCtls:
            control.setLockTag(ctl, uk=['r', 't'])

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

        ikNode, ikHandle = setupSpineIkNode(ikCtls, ikJnts[:-1], nodeName='splinik', namer=namer,
                         crv=crv, surf=srf)
        self.setNodeCateogry(ikNode, 'dnt')
        MC.setAttr("%s.v" % ikNode, 0)
        #tag this node so the master connect the uniform scale
        core.Root.tagInputScaleAttr(ikNode, 'inputScaleAmt')

        MC.addAttr(ikCtls[-1], ln='fkIk', dv=0, k=1, min=0, max=1)
        MC.addAttr(ikCtls[-1], ln='stretchAmt', dv=0, k=1, min=0, max=1)
        MC.addAttr(ikCtls[-1], ln='evenStretchAmt', dv=0, k=1, min=0, max=1)

        control.setLockTag(ikCtls[-1], uk=['fkIk', 'stretchAmt', 'evenStretchAmt'])

        MC.connectAttr('%s.stretchAmt' % ikCtls[-1], '%s.stretchAmt' % ikNode)
        MC.connectAttr('%s.evenStretchAmt' % ikCtls[-1], '%s.evenStretchAmt' % ikNode)


        ikReverse = utils.blendJointChains(fkCtls, ikJnts[:-1], bndJnts[:-1], '%s.fkIk' % ikCtls[-1], namer)
        for ctl in fkCtls:
            MC.connectAttr('%s.outputX' % (ikReverse), '%s.v' % ctl)
        for ctl in ikCtls[1:-1]:
            MC.connectAttr('%s.fkIk' % (ikCtls[-1]), '%s.v' % ctl)

core.WidgetRegistry().register(HeadNeck, "Neck and Head", "An Fk Neck and head")
