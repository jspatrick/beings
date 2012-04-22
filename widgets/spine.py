import logging
import maya.cmds as MC
import pymel.core as PM

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

def arclenOfJoints(jnts, inclusive=True):
    pass

def distanceOfJoints(jnts):
    pass

def epCurveFromJnts(jnts):
    pass


def cvCurveFromNodes(nodes, name='crv'):
    cmd = ['curve -d 2 -k 0 -name "%s"' % name]

    for i in range(len(nodes)-1):
        cmd.append('-k %i' % i)
        
    cmd.append('-k %i' % (len(nodes)-2))
    
    for node in nodes:
        p = MC.xform(node, q=1, ws=1, rp=1)
        cmd.append('-p %f %f %f' % (p[0], p[1], p[2]))
        
    cmd = ' '.join(cmd)
    _logger.debug(cmd)
    return MM.eval(cmd)

def bindControlsToShape(ctls, shape):
    """
    Cluster bind the controls to a curve.  Curve must have same num of points in u
    as num ctls
    """
    shape = MC.listRelatives(shape, type='geometryShape')
    if shape is None:
        shape = shape
    else:
        shape = shape[0]
        
    if MC.objectType(shape, isAType='nurbsSurface'):

        dv = MC.getAttr('%s.degreeV' % shape)
        suff = '[0:%i]' % dv
    elif MC.objectType(shape, isAType='nurbsCurve'):
        suff = ""
    else:
        raise RuntimeError("Bad input shape %s" % shape)
    
    for i, ctl in enumerate(ctls):
        cls, handle = MC.cluster('%s.cv[%i]%s' % (shape, i, suff))
        handleShape  = MC.listRelatives(handle)[0]

        MC.disconnectAttr('%s.worldMatrix[0]' % handle, '%s.matrix' % cls)
        MC.disconnectAttr('%s.clusterTransforms[0]' % handleShape, '%s.clusterXforms' % cls)

        MC.delete(handle)

        MC.setAttr('%s.bindPreMatrix' % cls, MC.getAttr('%s.worldInverseMatrix[0]' % ctl), type='matrix')
        MC.connectAttr('%s.worldMatrix[0]' % ctl, '%s.matrix' % cls)
    
def surfaceFromNodes(nodes, name='jntsSrf', upAxis=0):
    inPos = [0,0,0]
    outPos = [0,0,0]
    inPos[upAxis] = -1
    outPos[upAxis] = 1
    
    cmd = ['surface -du 2 -dv 1 -name "%s" ' % name]

    cmd.append('-ku 0')
    for i in range(len(nodes)-1):
        cmd.append('-ku %i' % i)
    cmd.append('-ku %i' % (len(nodes)-2))
    
    cmd.append('-kv 0 -kv 1')
    
    for node in nodes:
        wsp = MC.xform(node, q=1, rp=1, ws=1)
        cmd.append("-p %f %f %f" % (wsp[0] + inPos[0],
                                    wsp[1] + inPos[1],
                                    wsp[2] + inPos[2]))

        cmd.append("-p %f %f %f" % (wsp[0] + outPos[0],
                                    wsp[1] + outPos[1],
                                    wsp[2] + outPos[2]))

    cmd = " ".join(cmd)
    _logger.debug(cmd)    
    return MM.eval(cmd)
        
    

def createJntAttrs(jnt):
    pass
    #uniformStretchParam
    #stretchParam
    #noStretchParam

def createSurfaceJnts(ikJnts):
    pass


def closestPointOnSurface(node, surface, attr='closestPoint'):
    """
    Create a closest point on surface node.  Create an attr on the
    joint that the closestPoint is wired to
    """
    pass

def createIkSpineSystem(jnts, ctls):
    ikSpineNode = PM.createNode('transform', n='ikSpineNode')
    ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
    ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)
    for i, jnt in enumerate(jnts):
        ikSpineNode.addAttr('spinePos%i' % i)
        ikSpineNode.addAttr('spineRot%i' % i)
        ikSpineNode.addAttr('spineScl%i' % i)
        
    
