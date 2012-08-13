import maya.cmds as MC
from beings import core
from beings import control


class FkChain(core.Widget):
    def __init__(self):
        super(FkChain, self).__init__()
        self.options.addOpt('numBones', 1, min=1, optType=int)
        

    def _makeLayout(self, namer):
        jntCnt =  self.options.getValue('numBones') + 1

        MC.select(cl=1)
        jnts = []
        for i in range(jntCnt):
            jnts.append(MC.joint(p=[0,i*2, 0], n=namer(r='fk', alphaSuf=i)))

        MC.select(cl=1)
        for jnt in jnts:
            self.registerBindJoint(jnt)
        
