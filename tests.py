#control
import pymel.core as pm
import control as CTL
reload(CTL)

pm.newFile(force=1)
def testMakeControl():
    pm.newFile(f=1)
    ctl = CTL.Control()
    ctl.setColor('red')
    ctl.shapeNodes()
    pm.move(ctl.xformNode(), [5,5,5])
    ctl.setShape('circle')
    

def testControlFromNode():
    pm.newFile(f=1)
    xform = pm.createNode('joint', name='testControl')
    control = CTL.Control(xformNode=xform)
    xform.t.set([1,4,6])
    control.setShape('arrow', shapeType='srf')
    control.setColor('blue')
    
    
