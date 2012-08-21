"""
import maya.cmds as MC
import beings.widgets.fkChain as FKC

MC.file(new=1, f=1)
reload(FKC)
fkc = FKC.FkChain()
fkc.buildLayout()
"""
from string import ascii_lowercase
import maya.cmds as MC
import beings.core as core
import logging
from beings import control
from beings import utils

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

class FkChain(core.Widget):
    def __init__(self):
        super(FkChain, self).__init__('fkchain')
        self.options.addOpt('numBones', 1, min=1, optType=int)
        self.options.subscribe('optChanged', self.__optionChanged)
        self.__setPlugs(1)

    def __setPlugs(self, newNumBones):
        newPlugs = set(['fk_%s' % ascii_lowercase[i] for i in range(newNumBones)])
        currentPlugs = set(self.plugs())
        toRemove = currentPlugs.difference(newPlugs)
        toAdd = newPlugs.difference(currentPlugs)
        _logger.debug("Adding plugs: %s; Removing plugs: %s" % (toAdd, toRemove))

        for plug in toRemove:
            self.rmPlug(plug)
        for plug in toAdd:
            self.addPlug(plug)


    def __optionChanged(self, event):
        if event.optName != 'numBones':
            return
        self.__setPlugs(event.newVal)


    def _makeLayout(self, namer):
        jntCnt =  self.options.getValue('numBones') + 1

        MC.select(cl=1)
        jnts = []
        layoutCtlZeros = []
        rigCtls = []
        ups = []
        for i in range(jntCnt):
            jnt = MC.joint(p=[0,i*2, 0], n=namer(r='bnd', alphaSuf=i))
            self.registerBindJoint(jnt)
            jnts.append(jnt)
            if i < jntCnt -1:
                rigCtl = control.makeControl(namer(r='fk', alphaSuf=i), color='green',
                                         shape='cube')

                control.setEditable(rigCtl, True)
                self.registerControl(rigCtl, 'rig')
                rigCtls.append(rigCtl)

            layoutCtl = control.makeControl(namer('layout_ctl', r='fk', alphaSuf=i),
                                            color='purple', shape='sphere')

            if i < (jntCnt-1):
                upCtl = control.makeControl(namer('layout_twist_ctl', r='fk', alphaSuf=i),
                                            color='blue', shape='triangle', t=[1.5,0,0],
                                            s=[.2, .2, .2])

                up = MC.createNode('transform', n=namer('layout_twist_up', r='fk', alphaSuf=i))
                MC.parent(up, upCtl)
                MC.setAttr('%s.t' % up, 2, 0, 0, type='double3')
                ups.append(up)
                utils.snap(jnt, upCtl)
                MC.parent(upCtl, layoutCtl)
                self.registerControl(upCtl, 'layout', uk=['ry'])

            utils.snap(jnt, layoutCtl)
            utils.snap(jnt, rigCtl)

            layoutCtlZeros.append(utils.insertNodeAbove(layoutCtl))
            MC.parent(rigCtl, jnt)


            MC.pointConstraint(layoutCtl, jnt)

            utils.fixJointConstraints(jnt)


            self.registerControl(layoutCtl, 'layout', uk=['t'])


            MC.select(jnt)

        MC.select(cl=1)

        #aim each fkControl at the next one
        for i in range(len(layoutCtlZeros)-1):


            nextCtl = MC.listRelatives(layoutCtlZeros[i+1])[0]
            thisZero = layoutCtlZeros[i]
            thisCtl = MC.listRelatives(thisZero)[0]

            control.centeredCtl(jnts[i], jnts[i+1], rigCtls[i])

            upVec = [1,0,0]

            MC.aimConstraint(nextCtl, thisCtl,
                             aimVector=[0,1,0],
                             upVector=[1,0,0],
                             worldUpVector=[1,0,0])

            MC.aimConstraint(nextCtl, jnts[i],
                             aimVector=[0,1,0],
                             upVector=upVec,
                             worldUpType='object',
                             worldUpObject = ups[i])

            utils.fixJointConstraints(thisCtl)

            lck = ['tx', 'ty', 'tz', 'rx', 'rz', 'sx', 'sy', 'sz']
            for attr in lck:
                par = MC.listRelatives(ups[i], parent=1)[0]
                #MC.setAttr('%s.%s' % (ups[i], attr) , l=1)
                MC.setAttr('%s.%s' % (par, attr) , l=1)


    def _makeRig(self, namer):
        jntCnt =  self.options.getValue('numBones') + 1
        toks = ascii_lowercase[:jntCnt]
        bndJnts = [namer(r='bnd', alphaSuf=i) for i in range(jntCnt)]
        for jnt in bndJnts:
            MC.makeIdentity(jnt, apply=True, r=1, s=1, t=1)
        fkCtls = [namer(r='fk', alphaSuf=i) for i in range(jntCnt-1)]


        o = utils.Orientation()
        side = self.options.getValue('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts)
        return

        fkCtls = control.setupFkCtls(bndJnts[:-1], fkCtls, toks[:-1], namer)

        for ctl in fkCtls:
            control.setLockTag(ctl, uk=['r', 's'])

        MC.delete(bndJnts[0])
        for i, ctl in enumerate(fkCtls):
            self.setPlugNode('fk_%s' % ascii_lowercase[i], ctl)

core.WidgetRegistry().register(FkChain, "Fk Chain", "An Fk joint chain")
