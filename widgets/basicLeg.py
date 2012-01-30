import beings.core as core
import beings.control as control
import beings.utils as utils
import pymel.core as pm
import maya.cmds as MC

import logging
_logger = logging.getLogger(__name__)


class BasicLeg(core.Widget):
    def __init__(self, part='basicleg', **kwargs):
        super(BasicLeg, self).__init__(part=part, **kwargs)
        #add parentable Nodes
        self.addParentPart('bnd_hip')
        self.addParentPart('bnd_knee')
        self.addParentPart('bnd_ankle')
                    
    def _makeLayout(self, namer):
        """
        build the layout
        """
        toks = ['hip', 'knee', 'ankle', 'ball', 'toe', 'toetip']
        positions = [(0,5,0),
                     (0,2.75,1),
                     (0,.5,0),
                     (0,0,0.5),
                     (0,0,1),
                     (0,0,1.5)]

        legJoints = {}
        legCtls = {}
        pm.select(cl=1)

        #create/register bind joints and layout controls
        for i, tok in enumerate(toks):
            legJoints[tok] = pm.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            self.registerBindJoint(tok, legJoints[tok])
            legCtls[tok] = control.makeControl(shape='sphere',
                                               scale=[0.3, 0.3, 0.3],
                                               name = namer.name(x='ctl', d=tok, r='layout'))
            self.registerControl(tok, legCtls[tok])
            utils.snap(legJoints[tok], legCtls[tok], orient=False)
            pm.select(legJoints[tok])
            
        for i, tok in enumerate(toks):
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])            
            legCtls[tok].r.setLocked(True)
        legCtls['ankle'].ry.setLocked(False)
        ankleCtl = legCtls['ankle']
        for tok in ['ball', 'toe', 'toetip']:
            ctl = legCtls[tok]
            ctl.setParent(ankleCtl)
            ctl.tx.setLocked(True)

        pm.pointConstraint(legCtls['hip'], legJoints['hip'], mo=False)
        pm.pointConstraint(legCtls['knee'], legJoints['knee'], mo=False)
        pm.pointConstraint(legCtls['ankle'], legJoints['ankle'], mo=True)
        #create up-vec locs
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['knee'], l,
                          aimVector=[0,0,1], upVector=[1,0,0],
                          worldUpType='object',
                          worldUpObject = legCtls['hip'])
        l.v.set(0)
        
        #aim the hip at the knee
        pm.aimConstraint(legCtls['knee'], legJoints['hip'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)
        #aim the knee at the ankle
        pm.aimConstraint(legCtls['ankle'], legJoints['knee'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)
        
        #setup IK
        for pr in [('ankle', 'ball'), ('ball', 'toe'), ('toe', 'toetip')]:
            handle = pm.ikHandle(solver='ikSCsolver', sj=legJoints[pr[0]],
                                 ee=legJoints[pr[1]],
                                 n=namer.name(d='%s_ikh' % pr[1]))[0]
            handle.setParent(legCtls[pr[1]])
            pm.makeIdentity(handle)
            handle.v.set(0)
            utils.createStretch(legCtls[pr[0]], legCtls[pr[1]], legJoints[pr[0]], namer)
            #pm.pointConstraint(legCtls[pr[1]], legJoints[pr[1]])            
            
        #make rig controls
        #ankleIK
        ankleIkCtl = control.makeControl(name=namer.name(d='ankle', r='ik', x='animctl'), shape='jack', color='blue')
        self.registerControl('ankleIK', ankleIkCtl, ctlType='rig')
        utils.snap(legJoints['ankle'], ankleIkCtl, orient=False)
        par = utils.insertNodeAbove(ankleIkCtl)
        pm.pointConstraint(legJoints['ankle'], par, mo=False)

        #kneeIK
        kneeIkCtl = control.makeControl(name=namer.name(d='knee', r='ik', x='animctl'),
                                        shape='jack', color='red', scale=[.5, .5, .5])
        self.registerControl('kneeIK', kneeIkCtl, ctlType='rig')
        utils.snap(legJoints['knee'], kneeIkCtl, orient=False)
        par = utils.insertNodeAbove(kneeIkCtl)
        pm.pointConstraint(legJoints['knee'], par, mo=False)

        #heel
        heelCtl = control.makeControl(name=namer.name(d='heel', x='animctl'),
                                      shape='jack', color='red', scale=[.5,.5,.5])
        self.registerControl('heelIK', heelCtl, ctlType='rig')
        utils.snap(legJoints['ball'], heelCtl, orient=False)
        heelCtl.tz.set(-.5)
        par = utils.insertNodeAbove(heelCtl)
        pm.parentConstraint(legJoints['ball'], par, mo=True)
        
        #FK
        
        for tok, jnt in legJoints.items():
            if tok == 'toetip':
                continue

            ctl = pm.createNode('transform', name=namer.name(d=tok, r='fk', x='animctl'))
            utils.snap(jnt, ctl)
            control.makeControl(xform=ctl, shape='cube', color='yellow', scale=[.35, .35, .35])
            self.registerControl(tok, ctl, ctlType='rig')

            #center and scale it
            childJnt = legJoints[toks[toks.index(tok)+1]]            
            control.centeredCtl(jnt, childJnt, ctl)
            
        return namer
    
    def __setupFkCtls(self, bndJnts, rigCtls, fkToks):
        """Set up the fk controls.  This will delete the original controls that were passed
        in and rebuild the control shapes on a duplicate of the bind joints
        @return: dict of {tok:ctl}
        """
        fkCtls = utils.dupJntDct(bndJnts, '_bnd_', '_fk_')
        unusedToks = set(fkCtls.keys()).difference(fkToks)            
        for tok in fkToks:            
            newCtl = fkCtls[tok]
            oldCtl = rigCtls[tok]
            info = control.getInfo(oldCtl)
            control.setInfo(newCtl, control.getInfo(oldCtl))            
            utils.parentShape(newCtl, oldCtl)
            
        for tok in unusedToks:            
            ctl = fkCtls.pop(tok)
            if set(ctl.listRelatives()).intersection(fkCtls.values()):
                _logger.warning("Warning - deleting a parent of other controls")
            pm.delete(ctl)
            #also delete the rig ctl
            try:
                pm.delete(rigCtls.pop(tok))
            except KeyError:
                pass
        return fkCtls
    def __blendJointChains(self, fkChain, ikChain, bindChain, fkIkAttr, reverse):
        for tok in bindChain.keys():
            if (tok not in fkChain) or (tok not in ikChain):
                _logger.debug("Skipping blending %s" % tok)
                continue
            for cstType in ['point', 'orient', 'scale']:
                fnc = getattr(pm, '%sConstraint' % cstType)
                cst = fnc(fkChain[tok], ikChain[tok], bindChain[tok])
                fkAttr = getattr(cst, '%sW0' % fkChain[tok].nodeName())
                ikAttr = getattr(cst, '%sW1' % ikChain[tok].nodeName())
                reverse.outputX.connect(fkAttr)
                fkIkAttr.connect(ikAttr)

    def _setupRevFoot(self, namer, ikJnts, rigCtls, ikCtl, orientation, ankleIKH):
            
        #make the heel ctl a movable pivot
        heelMoveZero = pm.createNode('transform', n=namer.name(d='heel', x='ctl_zero'))
        utils.snap(rigCtls['heelIK'], heelMoveZero)        
        heelMoveNegpiv = pm.duplicate(heelMoveZero, n=namer.name(d='heel', x='ctl_negpiv'))[0]
        heelMoveNegpiv.setParent(rigCtls['heelIK'])
        rigCtls['heelIK'].setParent(heelMoveZero)
        
        heelMoveMdn = pm.createNode('multiplyDivide', n=namer.name(r='ik', d='heel_pvt', x='mdn'))
        rigCtls['heelIK'].t.connect(heelMoveMdn.input1)
        heelMoveMdn.input2.set(-1, -1, -1) 
        heelMoveMdn.output.connect(heelMoveNegpiv.t)        

        #create the ik hanldes
        ikHandles = {}
        toks = ['ankle', 'ball', 'toe', 'toetip']
        for i in range(len(toks)-1):
            start = toks[i]
            end = toks[i+1]
            name = namer.name(d='revfoot_%s_to_%s' % (start, end),
                                 x='ikh',
                                 r='ik')
            r = pm.ikHandle(sj=ikJnts[start], ee=ikJnts[end], n=name, sol='ikSCsolver')
            ikHandles[toks[i+1]] = pm.PyNode(r[0])
            eff = pm.PyNode(r[1])
            r[1].rename(name + '_eff')

        #make reverse foot joints, snap them all to the heel and aimed at the toetip
        revFootJnts = {}
        revFtToks = ['heel', 'toetip', 'toe', 'toetap', 'ball']
        for tok in revFtToks:
            name=namer.name(d='revfoot_%s' % tok, r='ik', x='jnt')
            revFootJnts[tok] = pm.createNode('joint', n=name)

        #position and orient the groups
        utils.snap(rigCtls['heelIK'], revFootJnts['heel'])
        aimAt(ikJnts['toetip'], revFootJnts['heel'], ikJnts['ankle'], orientation)        
        utils.snap(ikJnts['toetip'], revFootJnts['toetip'])
        aimAt(ikJnts['toe'], revFootJnts['toetip'], ikJnts['ankle'], orientation)
        utils.snap(ikJnts['toe'], revFootJnts['toe'])
        aimAt(ikJnts['ball'], revFootJnts['toe'], ikJnts['ankle'], orientation)
        utils.snap(ikJnts['toe'], revFootJnts['toetap'])
        aimAt(ikJnts['ball'], revFootJnts['toetap'], ikJnts['ankle'], orientation)
        utils.snap(ikJnts['ball'], revFootJnts['ball'])
        aimAt(ikJnts['ankle'], revFootJnts['ball'], ikJnts['ankle'], orientation)
        revFootJnts['ball'].setParent(revFootJnts['toe'])
        revFootJnts['toetap'].setParent(revFootJnts['toetip'])
        revFootJnts['toe'].setParent(revFootJnts['toetip'])
        revFootJnts['toetip'].setParent(revFootJnts['heel'])
        pm.makeIdentity(revFootJnts.values(), apply=True, r=1)
        
        ikHandles['ball'].setParent(revFootJnts['toe'])
        ikHandles['toe'].setParent(revFootJnts['toetip'])
        ikHandles['toetip'].setParent(revFootJnts['toetap'])
        ankleIKH.setParent(revFootJnts['ball'])

        heelZero = pm.createNode('transform',
                                 n = namer.name(d='revfoot_%s' % tok, r='ik', x='jnt_zero'))
        utils.snap(revFootJnts['heel'], heelZero)
        
        revFootJnts['heel'].setParent(heelZero)
        heelZero.setParent(heelMoveNegpiv)
        heelMoveZero.setParent(ikCtl)

        #create attrs on the ik handle to control the reverse foot
        attrs = {revFootJnts['heel']:[('heelLift', 'rx', -1),
                                      ('heelRock', 'rz', 1),
                                      ('heelRoll', 'ry', 1)],
                 revFootJnts['toetip']:[('toeTipLift', 'rx', 1),
                                        ('toeTipRock', 'rz', 1),
                                        ('toeTipRoll', 'ry', 1)],                 
                 revFootJnts['toe']:[('toeLift', 'rx', 1),
                                     ('toeTwist', 'ry', 1)],
                 revFootJnts['toetap']:[('toeTap', 'rx', 1)],
                 revFootJnts['ball']: [('ballLift', 'rx', 1),
                                       ('ballTwist', 'ry', 1)]}
        
        for jnt, attrGrp in attrs.items():
            
            for attr, axis, mult in attrGrp:
                mdn = pm.createNode('multiplyDivide', n=namer.name(r='ik', d=attr, x='mdn'))                
                ikCtl.addAttr(attr, k=1, dv=0)
                pm.connectAttr('%s.%s' % (ikCtl, attr), mdn.input1X.name())
                mdn.input2X.set(10*mult)
                pm.connectAttr(mdn.outputX.name(), '%s.%s' % (jnt, axis))
        heelMoveNegpiv.v.set(0)
        return revFootJnts
    
    def _makeRig(self, namer, bndJnts, rigCtls):
        #add the parenting nodes - this is a required step.  It registers the actual nodes
        #the rig uses to parent widgets to each other
        for tok in ['hip', 'knee', 'ankle']:
            self.setParentNode('bnd_%s' % tok, bndJnts[tok])
        
        o = utils.Orientation()
        side = self.options.getValue('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts.values())
            
        fkJnts = self.__setupFkCtls(bndJnts, rigCtls,
                                    ['hip', 'knee', 'ankle', 'ball', 'toe'])
        ikJnts = utils.dupJntDct(bndJnts, '_bnd_', '_ik_')
        ikCtl = rigCtls['ankleIK']
        ikCtl.addAttr('fkIk', min=0, max=1, dv=1, k=1)
        fkIkRev = pm.createNode('reverse', n=namer.name(d='fkik', x='rev'))
        
        self.__blendJointChains(fkJnts, ikJnts, bndJnts, ikCtl.fkIk, fkIkRev)
        
        ikCtl.fkIk.connect(fkIkRev.inputX)
        for tok, jnt in ikJnts.items():                        
            ikCtl.fkIk.connect(jnt.v)
            if fkJnts.get(tok):
                fkIkRev.outputX.connect(fkJnts[tok].v)
        namer.setTokens(r='ik')
        
        
        self.setNodeCateogry(ikCtl, 'ik')
        utils.snap(bndJnts['ankle'], ikCtl, orient=False)
        ikHandle, ikEff = pm.ikHandle(sj=ikJnts['hip'],
                                      ee=ikJnts['ankle'],
                                      solver='ikRPsolver',
                                      n=namer.name(x='ikh'))
        ikHandle.setParent(ikCtl)

        revFootJnts = self._setupRevFoot(namer, ikJnts, rigCtls, ikCtl, o, ikHandle)
        return locals()
    
def aimAt(master, slave, upRotObject, orientation, flipUp=False):
    aimVec = orientation.getAxis('aim')
    upVec = orientation.getAxis('up')
    worldUpVec = upVec
    if flipUp:
        worldUpVec = [x*-1 for x in worldUpVec]        
    cst = pm.aimConstraint(master, slave, aim=aimVec, u=upVec, wu=worldUpVec,
                     mo=False, wut='objectRotation')
    pm.delete(cst)
    
core.WidgetRegistry().register(BasicLeg, "Leg", "A basic IK/FK leg")
