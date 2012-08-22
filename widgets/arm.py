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

        self.addPlug('bnd_uparm')
        self.addPlug('bnd_loarm')
        self.addPlug('bnd_hand')

        self.__toks = ['uparm', 'loarm', 'hand', 'hand_tip']

    def _makeLayout(self, namer):
        """
        build the layout
        """
        positions = [(0,0,0),
                     (10,0,-2),
                     (20,0,0),
                     (25,0,0)]
        MC.select(cl=1)

        jnts = {}
        layoutCtls = {}
        #create/register bind joints and layout controls
        for i, tok in enumerate(self.__toks):
            jnts[tok] = MC.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            self.registerBindJoint(jnts[tok])
            layoutCtls[tok] = control.makeControl(namer.name(d='%s_layout' % tok, r='ctl'),
                                               shape='sphere', color='purple')

            self.registerControl(layoutCtls[tok], 'layout', uk=['t', 'r'])
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





        #setup hand tip
        MC.parent(layoutCtls['hand_tip'], layoutCtls['hand'])
        handUpCtl = control.makeControl(namer('hand_up', r='ctl'),
                                                    shape='cube',
                                                    s=[.75, .75, .75],
                                                    color='blue')
        self.registerControl(handUpCtl, 'layout', uk=['t', 'r'])
        MC.parent(handUpCtl, layoutCtls['hand'])
        MC.makeIdentity(handUpCtl, t=1, r=1, s=1)
        MC.setAttr('%s.ty' % handUpCtl, 3)


        aimVec = [0,1,0]
        upVec = [-1,0,0]
        if self.options.getValue('side') == 'rt':
            upVec = [1,0,0]

        MC.aimConstraint(layoutCtls['hand_tip'], jnts['hand'],
                         aimVector=aimVec,
                         upVector=upVec,
                         worldUpType='object',
                         worldUpObject=handUpCtl)

        MC.pointConstraint(layoutCtls['hand_tip'], jnts['hand_tip'])


        #hand
        handCtl = control.makeControl(namer.name(d='ctl', r='ik'),
                                      shape='jack',
                                      color='red',
                                      s=[2,2,2])


        control.setEditable(handCtl, True)

        self.registerControl(handCtl, 'rig')

        par = utils.insertNodeAbove(handCtl)
        utils.snap(jnts['hand'], par, orient=False)

        MC.parentConstraint(jnts['hand'], par, mo=True)


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
                                       s=[.5,.5,.5])
        MC.parent(pv, pvPar)
        MC.makeIdentity(pv, t=1, r=1, s=1)

        control.setEditable(pv, True)
        self.registerControl(pv, 'rig')

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
                                s=[2,2,2])

            control.setEditable(ctl, True)
            utils.snap(jnt, ctl)

            self.registerControl(ctl, ctlType='rig')

            #center and scale it
            childJnt = jnts[self.__toks[self.__toks.index(tok)+1]]
            control.centeredCtl(jnt, childJnt, ctl)

        return namer


    def _preMirror(self, thisCtl, otherCtl, thisNamer, otherNamer):
        """do ik control mirroring"""
        direct = ['tx', 'ty', 'sx', 'sy', 'sz', 'rz']
        inverted = ['tz', 'ry', 'rx']

        if thisCtl == thisNamer('ctl_editor', r='ik'):

            for attr in direct:

                MC.connectAttr('%s.%s' % (thisCtl, attr),
                               '%s.%s' % (otherCtl, attr))

            for attr in inverted:
                fromAttr = '%s.%s' % (thisCtl, attr)
                toAttr = '%s.%s' % (otherCtl, attr)
                mdn = MC.createNode('multiplyDivide',
                                    n=thisNamer.name(d='%s%sTo%s%s' % (thisCtl,attr,otherCtl,attr)))

                MC.setAttr('%s.input2X' % mdn, -1)
                MC.setAttr('%s.operation' % mdn, 1)

                MC.connectAttr(fromAttr, '%s.input1X' % mdn)
                MC.connectAttr('%s.outputX' % mdn, toAttr)

            return True


        return False

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
                self.setPlugNode('bnd_%s' % tok, jnt)

        MC.makeIdentity(bndJnts, apply=True, r=1, t=1, s=1)

        ikCtl = namer('ctl', r='ik')
        if not MC.objExists(ikCtl):
            raise RuntimeError("cannot find '%s'" % ikCtl)

        o = utils.Orientation()
        side = self.options.getValue('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts)
            MC.setAttr('%s.rx' % ikCtl,
                       (180 + MC.getAttr('%s.rx' % ikCtl) % 360))
            MC.setAttr('%s.rz' % ikCtl,
                       (180 + MC.getAttr('%s.rz' % ikCtl) % 360))


        fkCtls = control.setupFkCtls(bndJnts[:-1], fkCtls, self.__toks[:-1], namer)
        for ctl in fkCtls:
            control.setLockTag(ctl, uk=['r'])


        namer.setTokens(r='ik')
        ikJnts = utils.dupJntList(bndJnts, self.__toks, namer)
        for jnt in ikJnts:
            control.setLockTag(jnt, uu=['r', 't', 's'])

        MC.setAttr('%s.v' % ikJnts[0], 0)



        #keep the ik hand control rotated
        par = MC.createNode('transform', n='%s_zero' % ikCtl)
        utils.snap(ikCtl, par, orient=False)
        MC.parent(ikCtl, par)

        self.setNodeCateogry(par, 'ik')

        MC.addAttr(ikCtl, ln='fkIk', min=0, max=1, dv=1, k=1)
        fkIkRev = utils.blendJointChains(fkCtls, ikJnts[:-1], bndJnts[:-1],
                                         '%s.fkIk' % ikCtl, namer)
        control.setLockTag(ikCtl, uk=['t', 'r', 'fkIk'])

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
        MC.setAttr('%s.r' % pv, 0, 0, 0, type='double3')
        control.setLockTag(ikCtl, uk=['t'])

        MC.poleVectorConstraint(pv, ikHandle)
        MC.parent(utils.insertNodeAbove(pv), ikCtl)


        #orient the hand to the ik control
        handOrientJnt = MC.duplicate(ikJnts[2], rc=1, po=1)[0]
        handOrientJnt = MC.rename(handOrientJnt, namer('handorient_space', r='ik'))
        MC.parent(handOrientJnt, ikCtl)
        MC.setAttr('%s.v' % handOrientJnt, 0)
        MC.orientConstraint(handOrientJnt, ikJnts[2])



core.WidgetRegistry().register(Arm, "Arm", "A basic IK/FK arm")
