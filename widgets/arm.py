import beings.core as core
import beings.control as control
import beings.utils as utils
import pymel.core as pm
import maya.cmds as MC

import logging
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class Arm(core.Widget):
    def __init__(self, part='arm', **kwargs):
        super(Arm, self).__init__(part=part, **kwargs)
        #add parentable Nodes

        self.addParentPart('bnd_uparm')
        self.addParentPart('bnd_loarm')
        self.addParentPart('bnd_hand')

        self.__toks = ['uparm', 'loarm', 'hand', 'hand_tip']

    def _makeLayout(self, namer):
        """
        build the layout
        """
        positions = [(0,0,0),
                     (2.5,0,-.5),
                     (5,0,0),
                     (6,0,0)]
        MC.select(cl=1)

        jnts = {}
        layoutCtls = {}
        #create/register bind joints and layout controls
        for i, tok in enumerate(self.__toks):
            jnts[tok] = MC.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            self.registerBindJoint(jnts[tok])
            layoutCtls[tok] = control.makeControl(namer.name(d='%s_layout' % tok, r='ctl'),
                                               shape='sphere',
                                               s=[0.3, 0.3, 0.3])

            self.registerControl(layoutCtls[tok], 'layout')
            utils.snap(jnts[tok], layoutCtls[tok], orient=False)
            MC.select(jnts[tok])

        for i, tok in enumerate(self.__toks):
            utils.orientJnt(jnts[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])

            MC.setAttr('%s.s' % layoutCtls[tok], l=1)
            if tok != 'ankle':
                MC.setAttr('%s.r' % layoutCtls[tok], l=1)

        for tok in self.__toks[:-1]:
            MC.pointConstraint(layoutCtls[tok], jnts[tok], mo=False)

        #create up-vec locs
        l = MC.spaceLocator(n=namer.name(d='orientor_loc'))[0]
        MC.pointConstraint(layoutCtls['uparm'], layoutCtls['hand'], l)
        MC.aimConstraint(layoutCtls['loarm'], l,
                          aimVector=[0,0,1], upVector=[1,0,0],
                          worldUpType='object',
                          worldUpObject = layoutCtls['uparm'])
        MC.setAttr('%s.v' % l, 0)

        #aim the hip at the knee
        MC.aimConstraint(layoutCtls['loarm'], jnts['uparm'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)

        #aim the knee at the ankle
        MC.aimConstraint(layoutCtls['hand'], jnts['loarm'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)

        # #setup IK
        # for pr in [('ankle', 'ball'), ('ball', 'toe'), ('toe', 'toetip')]:
        #     handle = MC.ikHandle(solver='ikSCsolver', sj=legJoints[pr[0]],
        #                          ee=legJoints[pr[1]],
        #                          n=namer.name(d='%s_ikh' % pr[1]))[0]
        #     MC.parent(handle, layoutCtls[pr[1]])
        #     MC.makeIdentity(handle)
        #     MC.setAttr("%s.v" % handle, 0)
        #     utils.createStretch(layoutCtls[pr[0]], layoutCtls[pr[1]], legJoints[pr[0]], namer)



        #hand
        handCtl = control.makeControl(namer.name(d='hand', r='ik'),
                                      shape='jack',
                                      color='red',
                                      s=[.5,.5,.5])

        self.registerControl(handCtl, 'rig')
        par = utils.insertNodeAbove(handCtl)
        MC.pointConstraint(jnts['hand'], par)

        #setup hand tip
        MC.parent(layoutCtls['hand_tip'], layoutCtls['hand'])
        handUpCtl = control.makeControl(namer('hand_up', r='ctl'),
                                                    shape='cube',
                                                    s=[.2, .2, .2],
                                                    color='green')
        self.registerControl(handUpCtl, 'layout')
        MC.parent(handUpCtl, layoutCtls['hand'])
        MC.makeIdentity(handUpCtl, t=1, r=1, s=1)
        MC.setAttr('%s.ty' % handUpCtl, 1)
        MC.aimConstraint(layoutCtls['hand_tip'], jnts['hand'], aimVector=[0,1,0],
                         upVector=[-1,0,0],
                         worldUpType='object',
                         worldUpObject=handUpCtl)

        #pole vector
        pvPar = MC.createNode('transform', name=namer('pv_par_pvPar'))
        MC.pointConstraint(layoutCtls['uparm'], layoutCtls['hand'], pvPar)
        MC.aimConstraint(layoutCtls['hand'], pvPar, aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpType='object',
                         worldUpObject=layoutCtls['loarm'])

        pv = control.makeControl(namer('polevec', r='ik'),
                                       shape='diamond',
                                       color='salmon',
                                       s=[.2,.2,.2])

        self.registerControl(pv, 'rig')
        MC.parent(pv, pvPar)
        MC.makeIdentity(pv, t=1, r=1, s=1)
        zero = utils.insertNodeAbove(pv)

        dst = MC.createNode('distanceBetween', name=namer('pv_dst'))
        MC.connectAttr('%s.worldMatrix' % pvPar, '%s.im1' % dst)
        MC.connectAttr('%s.worldMatrix' % layoutCtls['uparm'], '%s.im2' % dst)
        mdn = MC.createNode('multiplyDivide', n=namer('pv_dst_mdn'))
        MC.connectAttr('%s.distance' % dst, '%s.input1X' % mdn)
        MC.setAttr('%s.input2X' % mdn, 2)
        MC.connectAttr("%s.outputX" % mdn, "%s.tx" % zero)
        MC.setAttr('%s.tz' % pv, l=1)

        #FK
        for tok, jnt in jnts.items():
            if tok == 'hand_tip':
                continue
            ctl = control.makeControl(namer.name(tok, r='fk'),
                                shape='cube',
                                color='yellow',
                                s=[.35, .35, .35])
            control.setEditable(ctl, True)
            utils.snap(jnt, ctl)

            self.registerControl(ctl, ctlType='rig')

            #center and scale it
            childJnt = jnts[self.__toks[self.__toks.index(tok)+1]]
            control.centeredCtl(jnt, childJnt, ctl)

        return namer


    def _makeRig(self, namer):

        #gather the bind joints and fk controls that were built
        bndJnts = []
        fkCtls = []
        for tok in self.__toks[:-1]:
            fkCtl = namer(tok, r='fk')
            if not MC.objExists(fkCtl):
                raise RuntimeError('%s does not exist'  % fkCtl)
            fkCtls.append(fkCtl)

        for tok in self.__toks:
            jnt = namer(tok, r='bnd')
            if not MC.objExists(jnt):
                raise RuntimeError('%s does not exist'  % jnt)
            bndJnts.append(jnt)
            if tok != 'hand_tip':
                self.setParentNode('bnd_%s' % tok, jnt)

        MC.makeIdentity(bndJnts, apply=True, r=1, t=1, s=1)


        o = utils.Orientation()
        side = self.options.getValue('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts)

        fkCtls = control.setupFkCtls(bndJnts[:-1], fkCtls, self.__toks[:-1], namer)

        namer.setTokens(r='ik')
        ikJnts = utils.dupJntList(bndJnts, self.__toks, namer)
        MC.setAttr('%s.v' % ikJnts[0], 0)


        ikCtl = namer('hand', r='ik')
        MC.addAttr(ikCtl, ln='fkIk', min=0, max=1, dv=1, k=1)
        fkIkRev = utils.blendJointChains(fkCtls, ikJnts[:-1], bndJnts[:-1],
                                         '%s.fkIk' % ikCtl, namer)
        for ctl in fkCtls:
            MC.connectAttr('%s.outputX' % fkIkRev, '%s.v' % ctl)

        ikHandle, ikEff = MC.ikHandle(sj=ikJnts[0],
                                      ee=ikJnts[2],
                                      solver='ikRPsolver',
                                      n=namer.name('ikh'))
        MC.parent(ikHandle, ikCtl)
        MC.setAttr('%s.v' % ikHandle, 0)

        #setup pole vec for ik ctl
        pv = namer('polevec', r='ik')
        MC.poleVectorConstraint(pv, ikHandle)
        self.setNodeCateogry(utils.insertNodeAbove(pv), 'ik')

        toks = ['%s_handjnt' % n for n in self.__toks[-2:]]
        ikHandJnts = utils.dupJntList(bndJnts[-2:], toks, namer)
        MC.parent(ikHandJnts[0], ikJnts[1])
        oc = MC.orientConstraint(ikHandJnts[0], ikJnts[2])[0]
        utils.fixInverseScale(ikHandJnts)
        utils.fixJointConstraints(ikJnts[2])

        MC.addAttr(ikCtl, ln='handIk', min=0, max=1, dv=0, k=1)
        MC.connectAttr('%s.handIk' % ikCtl, '%s.%sW0' % (oc, ikHandJnts[0]))

        tipIkHandle, tipIkEff = MC.ikHandle(sj=ikHandJnts[0],
                                      ee=ikHandJnts[-1],
                                      solver='ikSCsolver',
                                      n=namer.name('tip_ikh'))
        MC.parent(tipIkHandle, ikCtl)
        tipHandlePos = o.newOrientSpaceVector([2, 0, 0])
        _logger.debug('new tip handle pos: %r' % tipHandlePos)
        MC.setAttr("%s.t" % tipIkHandle, *tipHandlePos, type='double3')
        MC.setAttr("%s.v" % tipIkHandle, 0)


        #use the no-flip setup
        # xp = utils.getXProductFromNodes(ikJnts[1],  ikJnts[0], ikJnts[2])
        # sp = MC.xform(ikJnts[0], q=1, ws=1, t=1)
        # l = MC.spaceLocator()[0]
        # MC.xform(l, t=[sp[0] + xp[0], sp[1]+xp[1], sp[2]+xp[2]], ws=1)
        # MC.delete(MC.poleVectorConstraint(l, ikHandle))
        # MC.delete(l)
        # MC.setAttr("%s.twist" % ikHandle, 90)

        return

        self.setNodeCateogry(utils.insertNodeAbove(ikCtl, 'transform'), 'ik')


def aimAt(master, slave, upRotObject, orientation, flipUp=False):
    aimVec = orientation.getAxis('aim')
    upVec = orientation.getAxis('up')
    worldUpVec = upVec
    if flipUp:
        worldUpVec = [x*-1 for x in worldUpVec]
    cst = pm.aimConstraint(master, slave, aim=aimVec, u=upVec, wu=worldUpVec,
                     mo=False, wut='objectRotation')
    pm.delete(cst)

core.WidgetRegistry().register(Arm, "Arm", "A basic IK/FK arm")
