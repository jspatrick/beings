import logging
import maya.cmds as MC
import maya.OpenMaya as OM
import pymel.core as pm
import beings.utils as utils
reload(utils)
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)


def cvCurveFromNodes(nodes, name='crv'):
    cmd = ['curve -d 2 -k 0 -name "%s"' % name]

    for i in range(len(nodes)-1):
        cmd.append('-k %i' % i)
        
    cmd.append('-k %i' % (len(nodes)-2))
    
    for node in nodes:
        p = pm.xform(node, q=1, ws=1, rp=1)
        cmd.append('-p %f %f %f' % (p[0], p[1], p[2]))
        
    cmd = ' '.join(cmd)
    _logger.debug(cmd)
    return MM.eval(cmd)


def bindControlsToShape(ctls, shape):
    """
    Cluster bind the controls to a curve.  Curve must have same num of points in u
    as num ctls
    """
    _logger.debug('binding %s' % shape)
    s = MC.listRelatives(shape, type='geometryShape')
    if s:       
        shape = s[0]
        
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
        wsp = pm.xform(node, q=1, rp=1, ws=1)
        cmd.append("-p %f %f %f" % (wsp[0] + inPos[0],
                                    wsp[1] + inPos[1],
                                    wsp[2] + inPos[2]))

        cmd.append("-p %f %f %f" % (wsp[0] + outPos[0],
                                    wsp[1] + outPos[1],
                                    wsp[2] + outPos[2]))

    cmd = " ".join(cmd)
    _logger.debug(cmd)    
    return MM.eval(cmd)


ORIG_ARC_LEN_ATTR = 'origArcLen'
ORIG_ARC_PERCENTAGE_ATTR = 'origArcPercentage'
ORIG_PARAM_ATTR = 'origParam'
DIST_TO_NEXT = 'distToNext'

def addDistanceAttrs(nodes, keepConnection=True):
    result = []
    for i in range(len(nodes)-1):
        
        startNode = nodes[i]
        endNode = nodes[i+1]
        dd = pm.createNode('distanceBetween')
        startNode.t.connect(dd.p1)
        startNode.parentMatrix.connect(dd.im1)
        
        endNode.t.connect(dd.p2)
        endNode.parentMatrix.connect(dd.im2)

        dist = dd.distance.get()
        startNode.addAttr(DIST_TO_NEXT, dv=dist, k=1)
        if keepConnection:
            MC.connectAttr(str(dd.d),
                           '%s.%s' % (startNode, DIST_TO_NEXT))
        result.append(dist) 
    return result
    
def addJointAttrs(jnts, crv, mkAttrs=True):
    """
    Add the following attributes to a set of joints:
    origArcLen
    origArcLenPercentage
    origParam
    distToNext
    """
    sc = pm.createNode('subCurve')
    ci = pm.createNode('curveInfo')
    crv = pm.PyNode(crv)
    crv.worldSpace[0].connect(ci.inputCurve)
    totalLen = ci.arcLength.get()
    crv.worldSpace[0].disconnect(ci.inputCurve)
    
    sc.outputCurve.connect(ci.inputCurve, force=1)
    
    result = []
    for jnt in jnts:
        
        jnt = pm.PyNode(jnt)
        p = closestParamOnCurve(crv, jnt)

        #otherwise subcurve will build a full curve
        if p == 0:
            result.append(0)
        else:
            crv.worldSpace[0].connect(sc.inputCurve, force=1)
            sc.max.set(p)
            result.append(ci.arcLength.get())
            
        if mkAttrs:

            prc = result[-1]/totalLen            
            pm.addAttr(jnt, ln=ORIG_ARC_LEN_ATTR, dv=result[-1], k=1)
            pm.addAttr(jnt, ln=ORIG_PARAM_ATTR, dv=p, k=1)            
            pm.addAttr(jnt, ln=ORIG_ARC_PERCENTAGE_ATTR, dv=prc, k=1)
            
    addDistanceAttrs(jnts, keepConnection=False)
        
    return result


#TODO:  make up vecs align to orig jnts
def createCrvJnts(ikJnts, crv, upVec=[1,0,0], aimVec=[0,1,0]):
    "from a set of joints, get the closest points and create new joints"
    positions = []
    for jnt in ikJnts:
        positions.append(closestPointOnNurbsObj(crv, jnt))

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
    pnt = closestPointOnNurbsObj(crv, node)
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
    
def paramAtNode(crv, node):
    """
    Return param
    """    
    npoc = pm.createNode('nearestPointOnCurve', n=name)
    
    pm.connectAttr('%s.worldSpace[0]' % getShape(crv), '%s.inputCurve' % npoc)
    pos = pm.xform(node, q=1, ws=1, rp=1)
    pm.setAttr('%s.ip' % npoc, *pos)
    p = pm.getAttr('%s.parameter' % npoc)
    pm.delete(npoc)
    return p


def createIkSpineSystem(jnts, ctls, namer=None):
    if namer is None:
        namer = utils.Namer(character='char', part='spine')
        
    origCurve = cvCurveFromNodes(ctls)
    bindControlsToShape(ctls, origCurve)

    #build a curve with a single span that has uniform parameterization
    uniCurve = pm.rebuildCurve(origCurve, kep=1, kt=1, d=7, rt=0, s=1, ch=1, rpo=False)[0]
    uniCurve = uniCurve.listRelatives(type='nurbsCurve')[0]
    
    surf = surfaceFromNodes(ctls)
    bindControlsToShape(ctls, surf)

    #get an arclength to measure the whole curve
    curveAL = pm.createNode('curveInfo')
    
    uniCurve.worldSpace[0].connect(curveAL.inputCurve)
    totalOrigAL = curveAL.arcLength.get()
    
    crvJnts = createCrvJnts(jnts, uniCurve)
    crvJnts = [pm.rename(j, namer(d='ikcrv', alphaSuf=i)) for i, j in enumerate(crvJnts)]
    addJointAttrs(crvJnts, uniCurve)

    arcLenDiffInverseMDN = pm.createNode('multiplyDivide', name=namer('arclen_diff', s='mdn'))
    arcLenDiffInverseMDN.operation.set(2)
    curveAL.arcLength.connect(arcLenDiffInverseMDN.input2X)
    arcLenDiffInverseMDN.input1X.set(totalOrigAL)
    
    curveMaxParam = uniCurve.maxValue.get()
    
    ikSpineNode = pm.createNode('transform', n=namer('ikspine'))
    ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
    ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)

    finalPosLocs = []
    for i, jnt in enumerate(crvJnts):
        
        nsMultMDN = pm.createNode('multiplyDivide', name=namer('ns_param_mult', s='mdn', alphaSuf=i))
        pm.connectAttr('%s.%s' % (jnt, ORIG_ARC_PERCENTAGE_ATTR), '%s.input1X' % nsMultMDN)
        arcLenDiffInverseMDN.outputX.connect(nsMultMDN.input2X)

        nsParamMDN = pm.createNode('multiplyDivide', name=namer('ns_param', s='mdn', alphaSuf=i))
        nsMultMDN.outputX.connect(nsParamMDN.input1X)
        nsParamMDN.input2X.set(curveMaxParam)

        nsPosLoc = pm.spaceLocator(name=namer('ns_pos', s='loc', alphaSuf=i))
        nsPosLoc.v.set(0)
        nsPosPCI = pm.createNode('pointOnCurveInfo', n=namer('ns_pos', s='pci', alphaSuf=i))
        uniCurve.worldSpace[0].connect(nsPosPCI.inputCurve)
        nsParamMDN.outputX.connect(nsPosPCI.parameter)
        nsPosPCI.p.connect(nsPosLoc.t)
        #TODO:  get result position when curve is squashed

        #get non-uniform stretch
        nusPosLoc = pm.spaceLocator(name=namer('nus_pos', s='loc', alphaSuf=i))
        nusPosLoc.v.set(0)
        nusPosPCI = pm.createNode('pointOnCurveInfo', n=namer('ns_pos', s='pci', alphaSuf=i))
        uniCurve.worldSpace[0].connect(nusPosPCI.inputCurve)
        MC.connectAttr('%s.%s' % (jnt, ORIG_PARAM_ATTR), str(nusPosPCI.parameter))
        nusPosPCI.p.connect(nusPosLoc.t)

        #get uniform stretch
        usPosLoc = pm.spaceLocator(name=namer('us_pos', s='loc', alphaSuf=i))
        usPosLoc.v.set(0)
        #TODO:  actually set this up
        nusPosPCI.p.connect(usPosLoc.t)

        posLoc = pm.spaceLocator(name=namer('final_pos', s='loc', alphaSuf=i))
        stretchBlendPos = pm.createNode('blendColors', name=namer('stretch', s='blc', alphaSuf=i))
        nsBlendPos = pm.createNode('blendColors', name=namer('ns', s='blc', alphaSuf=i))

        ikSpineNode.uniformStretch.connect(stretchBlendPos.b)        
        usPosLoc.t.connect(stretchBlendPos.c1)
        nusPosLoc.t.connect(stretchBlendPos.c2)

        ikSpineNode.stretchAmt.connect(nsBlendPos.b)        
        nsPosLoc.t.connect(nsBlendPos.c2)
        stretchBlendPos.op.connect(nsBlendPos.c1)

        nsBlendPos.op.connect(posLoc.t)
        
        finalPosLocs.append(posLoc)
        
    addDistanceAttrs(finalPosLocs, keepConnection=True)

    upVecLocs = []
    for i in range(len(finalPosLocs)-1):
        loc = finalPosLocs[i]
        nextLoc = finalPosLocs[i+1]
        
        cps = pm.createNode('closestPointOnSurface', n=namer('final_pos_up', s='cps'))
        upLoc = pm.spaceLocator(name=namer('final_pos_up', s='loc'))
        surfShape = getShape(surf)
        surfShape.worldSpace[0].connect(cps.inputSurface)
        loc.t.connect(cps.ip)
        posi = pm.createNode('pointOnSurfaceInfo', n=namer('final_pos_up', s='psi'))
        surfShape.worldSpace[0].connect(posi.inputSurface)
        cps.u.connect(posi.u)
        posi.v.set(cps.v.get() + .1)
        posi.p.connect(upLoc.t)

        scaleMDN = pm.createNode('multiplyDivide', n=namer('scl', s='mdn'))
        loc.distToNext.connect(scaleMDN.input1X)
        crvJnts[i].distToNext.connect(scaleMDN.input2X)
        scaleMDN.operation.set(2)
        
        scaleMDN.outputX.connect(crvJnts[i].sy)
        
        pm.pointConstraint(loc, crvJnts[i])
        pm.aimConstraint(nextLoc, crvJnts[i], aimVector=[0,1,0], upVector=[1,0,0],
                         worldUpType='object', worldUpObject=str(upLoc))
        
    #get the percentage arclen
    
    
    #curve param - minValue/maxValue
    #srf param - crv.maxRangeU.get()
    
    #get a stretchpointOnCurveInfo at the orig param for stretch
    #get a pointOnCurveInfo 
    #get original arc length of joints
    #
    return
        
    
if __name__ == '__main__':  
    ctls = [pm.PyNode(n) for n in [u'ctl_a', u'ctl_b', u'ctl_c', u'ctl_d']]
    jnts = [pm.PyNode(n) for n in [u'bnd_a', u'bnd_b', u'bnd_c', u'bnd_d', u'bnd_e']]
    createIkSpineSystem(jnts, ctls)
