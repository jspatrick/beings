import logging
import maya.cmds as MC
import pymel.core as PM

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

def arclenOfJoints(jnts, crv, inclusive=True):
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

#TODO:  make up vecs align to orig jnts
def createCrvJnts(ikJnts, crv, upVec=[1,0,0], aimVec=[0,1,0]):
    "from a set of joints, get the closest points and create new joints"
    positions = []
    for jnt in ikJnts:
        positions.append(closestPointOnCurve(crv, jnt))

    pm.select(cl=1)

    newJnts = []
    for i in range(len(ikJnts)):
        newJnts.append(pm.joint(p=positions[i]))
    for jnt in newJnts:
        utils.orientJnt(jnt, aimVec=aimVec, upVec=upVec)

    return newJnts

#TODO:  get space other than local
def closestPointOnNurbsObj(crv, node):
    """Get closest point to a nurbs surface or curve"""
    shape = getShape(crv)
    fn = shape.__apimfn__()
    
    wsPos = pm.xform(node, q=1, rp=1, ws=1)
    pnt = fn.closestPoint(OM.MPoint(*wsPos))
    return [pnt.x, pnt.y, pnt.z]

def closestParamOnCurve(crv, node):
    pnt = closestPointOnCurve(crv, node)
    crvFn = getShape(crv).__apimfn__()
    su = OM.MScriptUtil()
    pDouble = su.asDoublePtr()
    
    crvFn.getParamAtPoint(OM.MPoint(*pnt), pDouble)

    return su.getDouble(pDouble)

    

def getShape(node):
    node = pm.PyNode(node)
    shapes = pm.listRelatives(node)
    if shapes:
        if not pm.objectType(shapes[0], isAType='geometryShape'):
            raise RuntimeError('invalid node %s' % node)
        else:
            return pm.PyNode(shapes[0])
        
    elif pm.objectType(node, isAType='geometryShape'):
        return pm.PyNode(node)
    
    else:
        raise RuntimeError('invalid node %s' % node)
    
def paramAtNode(crv, node, name='closePoint', keepNode=False):
    """
    Return param
    """    
    npoc = MC.createNode('nearestPointOnCurve', n=name)
    
    MC.connectAttr('%s.worldSpace[0]' % getShape(crv), '%s.inputCurve' % npoc)
    pos = MC.xform(node, q=1, ws=1, rp=1)
    MC.setAttr('%s.ip' % npoc, *pos)
    p = MC.getAttr('%s.parameter' % npoc)
    MC.delete(npoc)
    return p
                   
def createIkSpineSystem(jnts, ctls):
    origCurve = cvCurveFromNodes(ctls)
    bindControlsToShape(ctls, origCurve)
    uniCurve = MC.rebuildCurve(origCurve, kep=1, kt=1, d=7, rt=0, s=1, ch=1, rpo=False)[0]

    surf = surfaceFromNodes(jnts)
    bindControlsToShape(ctls. surf)
    
    pos = createNode('transform', n='ikSpine%i_pos' % i)
    poci = MC.createNode('pointOnCurveInfo', n='ikSpine%i_pi' % i)
    MC.connectAttr('%s.worldSpace[0]' % uniCurve, '%s.inputCurve' % poci)
    
    ikSpineNode = PM.createNode('transform', n='ikSpineNode')
    ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
    ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)
    
    for i, jnt in enumerate(jnts):
        npoc = MC.createNode('nearestPointOnCurve', n='ikSpine%i_npc' % i)
        #MC.connectAttr('%s.worldSpace[0]' % MC.listRelatives(uniCurve)[0]
        ikSpineNode.addAttr('spinePos%i' % i)
        ikSpineNode.addAttr('spineRot%i' % i)
        ikSpineNode.addAttr('spineScl%i' % i)
        
    
