import beings.core as core
import beings.control as control
import beings.utils as utils
import pymel.core as pm
import maya.cmds as MC

import logging
_logger = logging.getLogger(__name__)


class Leg(core.Widget):
    def __init__(self, part='leg', **kwargs):
        super(Leg, self).__init__(part=part, **kwargs)
        #add parentable Nodes

        self.addPlug('bnd_hip')
        self.addPlug('bnd_knee')
        self.addPlug('bnd_ankle')

        self.__toks = ['hip', 'knee', 'ankle', 'ball', 'toe', 'toetip']

    def _makeLayout(self, namer):
        """
        build the layout
        """
        positions = [(0,20,0),
                     (0,12,1),
                     (0,3,0),
                     (0,0,3),
                     (0,0,6),
                     (0,0,8)]

        legJoints = {}
        legCtls = {}
        MC.select(cl=1)

        #create/register bind joints and layout controls
        for i, tok in enumerate(self.__toks):
            legJoints[tok] = MC.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            self.registerBindJoint(legJoints[tok])

            legCtls[tok] = control.makeControl(namer.name(d='%s_layout' % tok, r='ctl'),
                                               shape='sphere',
                                               color='purple')

            if tok == 'ankle':
                self.registerControl(legCtls[tok], 'layout', uk=['t', 'ry'])
            elif tok in ['ball', 'toe']:
                self.registerControl(legCtls[tok], 'layout', uk=['ty', 'tz'])
            elif tok == 'toetip':
                self.registerControl(legCtls[tok], 'layout', uk=['tz'])
            else:
                self.registerControl(legCtls[tok], 'layout', uk=['t'])

            utils.snap(legJoints[tok], legCtls[tok], orient=False)
            MC.select(legJoints[tok])

        for i, tok in enumerate(self.__toks):
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])


        ankleCtl = legCtls['ankle']
        for tok in ['ball', 'toe']:
            ctl = legCtls[tok]
            MC.parent(ctl, ankleCtl)

        MC.parentConstraint(legCtls['ankle'], utils.insertNodeAbove(legCtls['toetip']),
                            skipTranslate=['y'], mo=True)

        MC.pointConstraint(legCtls['hip'], legJoints['hip'], mo=False)
        MC.pointConstraint(legCtls['knee'], legJoints['knee'], mo=False)
        MC.pointConstraint(legCtls['ankle'], legJoints['ankle'], mo=True)

        #create up-vec locs
        l = MC.spaceLocator(n=namer.name(d='orientor_loc'))[0]
        MC.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        MC.aimConstraint(legCtls['knee'], l,
                          aimVector=[0,0,1], upVector=[1,0,0],
                          worldUpType='object',
                          worldUpObject = legCtls['hip'])
        MC.setAttr('%s.v' % l, 0)

        #aim the hip at the knee
        MC.aimConstraint(legCtls['knee'], legJoints['hip'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)

        #aim the knee at the ankle
        MC.aimConstraint(legCtls['ankle'], legJoints['knee'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)

        #setup IK
        for pr in [('ankle', 'ball'), ('ball', 'toe'), ('toe', 'toetip')]:
            handle = MC.ikHandle(solver='ikSCsolver', sj=legJoints[pr[0]],
                                 ee=legJoints[pr[1]],
                                 n=namer.name(d='%s_ikh' % pr[1]))[0]
            MC.parent(handle, legCtls[pr[1]])
            MC.makeIdentity(handle)
            MC.setAttr("%s.v" % handle, 0)
            utils.createStretch(legCtls[pr[0]], legCtls[pr[1]], legJoints[pr[0]], namer)

        #kneeIK
        toeIkCtl = control.makeControl(namer('toe_ctl', r='ik'),
                                        shape='circle',
                                        color='red',
                                        s=[2,2,2])
        toeLayoutCtl = control.makeControl(namer('toe_layout_ctl', r='ik'),
                                                 shape='cube',
                                                 color='purple',
                                                 s=[2, .75, 2])
        control.setEditable(toeIkCtl, True)
        self.registerControl(toeIkCtl, 'rig')

        self.registerControl(toeLayoutCtl, 'layout', uk=['tx', 'tz'])
        MC.parent(toeIkCtl, toeLayoutCtl)


        utils.snap(legJoints['toe'], toeLayoutCtl, orient=False)
        par = utils.insertNodeAbove(toeLayoutCtl)
        pm.pointConstraint(legJoints['toe'], par, mo=False, skip='y')

        #heel
        heelCtl = control.makeControl(namer.name(d='heel_ctl', r='ik'),
                                      shape='jack',
                                      color='red',
                                      s=[2,2,2])

        heelLayoutCtl = control.makeControl(namer('heel_layout_ctl', r='ik'),
                                                 shape='cube',
                                                 color='purple',
                                                 s=[3, 1, 3])
        self.registerControl(heelLayoutCtl, 'layout', uk=['tx', 'tz'])
        MC.parent(heelCtl, heelLayoutCtl)

        utils.snap(legJoints['ball'], heelLayoutCtl, orient=False)
        MC.setAttr("%s.tz" % heelLayoutCtl, -.5)
        par = utils.insertNodeAbove(heelLayoutCtl)
        pm.parentConstraint(legCtls['ankle'], par, mo=True, skipTranslate=['y'])
        control.setEditable(heelCtl, True)
        self.registerControl(heelCtl, 'rig')

        #FK
        for tok, jnt in legJoints.items():
            if tok == 'toetip':
                continue
            ctl = control.makeControl(namer.name(tok, r='fk'),
                                shape='cube',
                                color='green',
                s=[2,2,2])
            control.setEditable(ctl, True)
            utils.snap(jnt, ctl)

            self.registerControl(ctl, ctlType='rig')

            #center and scale it
            childJnt = legJoints[self.__toks[self.__toks.index(tok)+1]]
            control.centeredCtl(jnt, childJnt, ctl)

        return namer


    def __setupFootRoll(self, ikCtl, revFootJnts, namer):

        #setup the foot roll
        MC.addAttr(ikCtl, ln='roll', dv=0, k=1)
        MC.addAttr(ikCtl, ln='ballBreakAngle', dv=30, k=1)
        MC.addAttr(ikCtl, ln='toeBreakAngle', dv=45, k=1)

        control.setLockTag(ikCtl, uk=['roll', 'ballBreakAngle', 'toeBreakAngle'])

        setRangeNodes = {'ball':'',
                             'toe':'',
                             'toetip':''}

        for setRangeNode in setRangeNodes.keys():
            setRangeNodes[setRangeNode] = MC.createNode('setRange',
                                                        n=namer('roll_%s_srg' % setRangeNode,
                                                                r='ik'))
            MC.connectAttr('%s.roll' % ikCtl, '%s.valueX' % setRangeNodes[setRangeNode])

        #the ball joint's max rotation is the roll angle.
        MC.setAttr('%s.minX' % setRangeNodes['ball'], -360)
        MC.setAttr('%s.oldMinX' % setRangeNodes['ball'], -360)
        MC.connectAttr('%s.ballBreakAngle' % ikCtl, '%s.maxX' % setRangeNodes['ball'])
        MC.connectAttr('%s.ballBreakAngle' % ikCtl, '%s.oldMaxX' % setRangeNodes['ball'])
        MC.connectAttr('%s.outValueX' % setRangeNodes['ball'], '%s.rx' % revFootJnts['ball'])

        #the toe joint's max rotation is the toe break angle, and min is the ball break
        ballRollPMA = MC.createNode('plusMinusAverage', n=namer('roll_toe_pma', r='ik'))
        MC.setAttr("%s.operation" % ballRollPMA, 2)
        MC.connectAttr('%s.toeBreakAngle' % ikCtl, '%s.input1D[0]' % ballRollPMA)
        MC.connectAttr('%s.ballBreakAngle' % ikCtl, '%s.input1D[1]' % ballRollPMA)
        MC.connectAttr('%s.output1D' % ballRollPMA, '%s.maxX' % setRangeNodes['toe'])
        MC.connectAttr('%s.ballBreakAngle' % ikCtl, '%s.oldMinX' % setRangeNodes['toe'])
        MC.connectAttr('%s.toeBreakAngle' % ikCtl, '%s.oldMaxX' % setRangeNodes['toe'])
        MC.connectAttr('%s.outValueX' % setRangeNodes['toe'], '%s.rx' % revFootJnts['toe'])

        #the last joint
        ballRollPMA = MC.createNode('plusMinusAverage', n=namer('roll_toetip_pma', r='ik'))
        MC.setAttr("%s.input1D[0]" % ballRollPMA, 360)
        MC.connectAttr('%s.toeBreakAngle' % ikCtl, '%s.input1D[1]' % ballRollPMA)
        MC.connectAttr('%s.output1D' % ballRollPMA, '%s.oldMaxX' % setRangeNodes['toetip'])
        MC.connectAttr('%s.toeBreakAngle' % ikCtl, '%s.oldMinX' % setRangeNodes['toetip'])
        MC.setAttr('%s.maxX' % setRangeNodes['toetip'], 360)
        MC.connectAttr('%s.outValueX' % setRangeNodes['toetip'], '%s.rx' % revFootJnts['toetip'])

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

        MC.makeIdentity(bndJnts, apply=True, r=1, t=1, s=1)
        for jnt in bndJnts:
            control.setLockTag(jnt, uu=['t', 'r', 's'])

        for i, tok in enumerate(self.__toks[:3]):
            self.setPlugNode('bnd_%s' % tok, bndJnts[i])

        o = utils.Orientation()
        side = self.options.getValue('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts)

        fkCtls = control.setupFkCtls(bndJnts[:-1], fkCtls, self.__toks[:-1], namer)
        for ctl in fkCtls:
            control.setLockTag(ctl, uk=['r'])

        namer.setTokens(r='ik')
        ikJnts = utils.dupJntList(bndJnts, self.__toks, namer)
        MC.setAttr('%s.v' % ikJnts[0], 0)


        ikCtl = namer('heel_ctl', r='ik')
        if not MC.objExists(ikCtl):
            raise RuntimeError("Cannot find '%s'" % ikCtl)

        MC.addAttr(ikCtl, ln='fkIk', min=0, max=1, dv=1, k=1)

        fkIkRev = utils.blendJointChains(fkCtls, ikJnts[:-1], bndJnts[:-1],
                                         '%s.fkIk' % ikCtl, namer)

        for ctl in fkCtls:
            MC.connectAttr('%s.outputX' % fkIkRev, '%s.v' % ctl)
        

        ikHandle, ikEff = MC.ikHandle(sj=ikJnts[0],
                                      ee=ikJnts[2],
                                      solver='ikRPsolver',
                                      n=namer.name('ikh'))

        #use the no-flip setup
        xp = utils.getXProductFromNodes(ikJnts[1],  ikJnts[0], ikJnts[2])
        sp = MC.xform(ikJnts[0], q=1, ws=1, t=1)
        l = MC.spaceLocator()[0]
        MC.xform(l, t=[sp[0] + xp[0], sp[1]+xp[1], sp[2]+xp[2]], ws=1)
        MC.delete(MC.poleVectorConstraint(l, ikHandle))
        MC.delete(l)
        MC.setAttr("%s.twist" % ikHandle, 90)

        MC.addAttr(ikCtl, ln='twist', dv=0, k=1)
        control.setLockTag(ikCtl, uk=['twist'])

        pma = MC.createNode('plusMinusAverage', n=namer('twist_pma'))
        MC.connectAttr("%s.twist" % ikCtl, "%s.input1D[0]" % pma)
        MC.setAttr("%s.input1D[1]" % pma, 90)
        MC.connectAttr("%s.output1D" % pma, "%s.twist" % ikHandle)

        del l, sp, xp


        ##set up the reverse foot
        #create the ik hanldes
        ikHandles = {}
        names = ['ankle', 'ball', 'toe', 'toetip']
        for i in range(len(names)-1):

            startIndex = self.__toks.index(names[i])
            endIndex = self.__toks.index(names[i+1])
            start = names[i]
            end = names[i+1]

            name = namer.name(d='revfoot_%s_to_%s_ikh' % (start, end),
                                 r='ik')
            handle = MC.ikHandle(sj=ikJnts[startIndex], ee=ikJnts[endIndex], n=name, sol='ikSCsolver')
            ikHandles[names[i+1]] = handle[0]
            MC.rename(handle[1], name + '_eff')



        #setup the toe control to have an inverse pivot
        toeCtl = namer('toe_ctl', r='ik')
        MC.connectAttr("%s.fkIk" % ikCtl, "%s.v" % toeCtl)
        
        MC.parent(toeCtl, ikCtl)
        utils.insertNodeAbove(toeCtl)

        toeCtlInv = MC.createNode('transform', n = namer('toe_inv', r='ik'))

        MC.parent(toeCtlInv, toeCtl)


        toeCtlInvMdn = MC.createNode('multiplyDivide', n=namer('toe_inv_mdn', r='ik'))
        MC.connectAttr('%s.t' % toeCtl, '%s.input1' % toeCtlInvMdn)
        MC.setAttr('%s.input2' % toeCtlInvMdn, -1, -1, -1, type='double3')
        MC.connectAttr('%s.output' % toeCtlInvMdn, '%s.t' % toeCtlInv)

        #setup the rev foot joints
        revFootJnts = {}
        revFkToks = ['heel', 'toetip', 'toe', 'ball', 'ankle']
        positions = [ikCtl, bndJnts[-1], bndJnts[-2], bndJnts[-3], bndJnts[-4]]


        MC.select(cl=1)
        for i in range(len(revFkToks)):
            tok = revFkToks[i]
            posNode = positions[i]
            pos = MC.xform(posNode, q=1, t=1, ws=1)
            if i == 1:
                pos[1] = MC.xform(positions[0], q=1, t=1, ws=1)[1]

            j = MC.joint(name=namer('%s_revfoot_jnt' % tok, r='ik'),
                     p = pos )
            revFootJnts[tok] = j
            if i == 0:
                MC.setAttr('%s.v' % j, 0)
        del i, j


        #orient the joints to aim down pos y and up axis along the plane formed by
        #the upper leg
        xp = utils.getXProductFromNodes(ikJnts[1],  ikJnts[0], ikJnts[2])
        for jnt in revFootJnts.values():
            utils.orientJnt(jnt, aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[xp[0],0,xp[2]])
        del jnt, xp


        MC.parent(revFootJnts['heel'], toeCtlInv)
        MC.parent(ikHandles['toetip'], revFootJnts['toetip'])
        MC.parent(ikHandles['toe'], revFootJnts['toe'])
        MC.parent(ikHandles['ball'], revFootJnts['ball'])
        MC.parent(ikHandle, revFootJnts['ankle'])


        #setup the foot roll
        self.__setupFootRoll(ikCtl, revFootJnts, namer)

        control.setLockTag(toeCtl, uk=['r', 't'])
        control.setLockTag(ikCtl, uk=['r', 't', 'fkIk'])
        
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

core.WidgetRegistry().register(Leg, "Leg", "A basic IK/FK leg")
