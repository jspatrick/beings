"""
import maya.cmds as MC
import beings.widgets.fkChain as FKC

MC.file(new=1, f=1)
reload(FKC)
fkc = FKC.FkChain()
fkc.buildLayout()
"""
import maya.cmds as MC
import beings.core as core
from beings import control
from beings import utils

class FkChain(core.Widget):
    def __init__(self):
        super(FkChain, self).__init__()
        self.options.addOpt('numBones', 1, min=1, optType=int)


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
                self.registerControl(rigCtl, 'rig')
                rigCtls.append(rigCtl)
            layoutCtl = control.makeControl(namer('layout_ctl', r='fk', alphaSuf=i),
                                            color='yellow', shape='sphere')
            upCtl = control.makeControl(namer('layout_twist_ctl', r='fk', alphaSuf=i),
                                            color='blue', shape='triangle', t=[1.5,0,0],
                s=[.2, .2, .2])

            up = MC.createNode('transform', n=namer('layout_twist_up', r='fk', alphaSuf=i))
            MC.parent(up, upCtl)
            MC.setAttr('%s.t' % up, 2, 0, 0, type='double3')
            ups.append(up)

            utils.snap(jnt, layoutCtl)
            utils.snap(jnt, rigCtl)
            utils.snap(jnt, upCtl)
            layoutCtlZeros.append(utils.insertNodeAbove(layoutCtl))
            MC.parent(rigCtl, jnt)
            MC.parent(upCtl, layoutCtl)

            MC.pointConstraint(layoutCtl, jnt)

            utils.fixJointConstraints(jnt)


            self.registerControl(layoutCtl, 'layout')
            MC.select(jnt)
        MC.select(cl=1)

        #aim each fkControl at the next one
        for i in range(len(layoutCtlZeros)-1):


            nextCtl = MC.listRelatives(layoutCtlZeros[i+1])[0]
            thisZero = layoutCtlZeros[i]
            thisCtl = MC.listRelatives(thisZero)[0]

            control.centeredCtl(jnts[i], jnts[i+1], rigCtls[i])

            MC.aimConstraint(nextCtl, thisCtl,
                             aimVector=[0,1,0],
                             upVector=[1,0,0],
                             worldUpVector=[1,0,0])

            MC.aimConstraint(nextCtl, jnts[i],
                             aimVector=[0,1,0],
                             upVector=[1,0,0],
                             worldUpType='object',
                             worldUpObject = ups[i])

            utils.fixJointConstraints(thisCtl)

            lck = ['tx', 'ty', 'tz', 'rx', 'rz', 'sx', 'sy', 'sz']
            for attr in lck:
                par = MC.listRelatives(ups[i], parent=1)[0]
                #MC.setAttr('%s.%s' % (ups[i], attr) , l=1)
                MC.setAttr('%s.%s' % (par, attr) , l=1)

        #TODO: add twist ctl



core.WidgetRegistry().register(FkChain, "Fk Chain", "An Fk joint chain")
