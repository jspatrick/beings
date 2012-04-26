import logging
import maya.cmds as MC
import maya.mel as MM
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
    return pm.PyNode(MM.eval(cmd))


def bindControlsToShape(ctls, shape):
    """
    Cluster bind the controls to a curve.  Curve must have same num of points in u
    as num ctls
    """
    _logger.debug('binding %s' % shape)
    shape = getShape(shape)
    if pm.objectType(shape, isAType='nurbsSurface'):

        dv = pm.getAttr('%s.degreeV' % shape)
        suff = '[0:%i]' % dv
    elif pm.objectType(shape, isAType='nurbsCurve'):
        suff = ""
    else:
        raise RuntimeError("Bad input shape %s" % shape)
    
    for i, ctl in enumerate(ctls):
        cls, handle = pm.cluster('%s.cv[%i]%s' % (shape, i, suff))
        handleShape  = pm.listRelatives(handle)[0]

        pm.disconnectAttr('%s.worldMatrix[0]' % handle, '%s.matrix' % cls)
        pm.disconnectAttr('%s.clusterTransforms[0]' % handleShape, '%s.clusterXforms' % cls)

        pm.delete(handle)

        pm.setAttr('%s.bindPreMatrix' % cls, pm.getAttr('%s.worldInverseMatrix[0]' % ctl), type='matrix')
        pm.connectAttr('%s.worldMatrix[0]' % ctl, '%s.matrix' % cls)
    

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


ORIG_ARC_LEN_ATTR = 'origArcLen%i'
ORIG_ARC_PERCENTAGE_ATTR = 'origArcPercentage%i'
ORIG_PARAM_ATTR = 'origParam%i'
DIST_TO_NEXT = 'distToNext%i'

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
    
def addJointAttrs(jnts, crv, node):
    """
    Add the following attributes to a set of joints:
    origArcLen<i>
    origArcLenPercentage<i>
    origParam<i>    
    """
    sc = pm.createNode('subCurve')
    ci = pm.createNode('curveInfo')
    crv = pm.PyNode(crv)
    crv.worldSpace[0].connect(ci.inputCurve)
    totalLen = ci.arcLength.get()
    crv.worldSpace[0].disconnect(ci.inputCurve)
    
    sc.outputCurve.connect(ci.inputCurve, force=1)
    
    result = []
    for i, jnt in enumerate(jnts):
        
        jnt = pm.PyNode(jnt)
        p = closestParamOnCurve(crv, jnt)

        #otherwise subcurve will build a full curve
        if p == 0:
            result.append(0)
        else:
            crv.worldSpace[0].connect(sc.inputCurve, force=1)
            sc.max.set(p)
            result.append(ci.arcLength.get())
            


        prc = result[-1]/totalLen            
        pm.addAttr(node, ln=ORIG_ARC_LEN_ATTR % i, dv=result[-1], k=1)
        pm.addAttr(node, ln=ORIG_PARAM_ATTR % i, dv=p, k=1)            
        pm.addAttr(node, ln=ORIG_ARC_PERCENTAGE_ATTR % i, dv=prc, k=1)
            
    #addDistanceAttrs(jnts, keepConnection=False)
        
    return result


#TODO:  make up vecs align to orig jnts
def createCrvJnts(ikJnts, crv, upVec=[1,0,0], aimVec=[0,1,0], asLocs=False):
    "from a set of joints, get the closest points and create new joints"
    positions = []
    for jnt in ikJnts:
        positions.append(closestPointOnNurbsObj(crv, jnt))

    pm.select(cl=1)

    newJnts = []
    for i in range(len(ikJnts)):
        if asLocs:
            loc = pm.spaceLocator()
            newJnts.append(loc)
            loc.t.set(positions[i])
            
        else:
            newJnts.append(pm.joint(p=positions[i]))
    if asLocs:
        for i in range(len(newJnts)):
            if i == len(newJnts) - 1 :
                nl = newJnts[i-1]
                aimVec = [0,-1,0]
            else:
                nl = newJnts[i+1]
                aimVec = [0,1,0]
                
            l = newJnts[i]
            pm.delete(pm.aimConstraint(nl, l,
                                       aimVector=aimVec,
                                       upVector=[1,0,0],
                                       worldUpVector=[1,0,0]))
            
            
    else:
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


g_epociNodes = {}
def getExtensionPointOnCurveInfo(curve):
    #we can reuse some nodes
    shape = getShape(curve)
    
    global g_epociNodes
    nodes = g_epociNodes.get(str(shape), {})    
    if not nodes:        
        endPoci = pm.createNode('pointOnCurveInfo')
        endPoci.pr.set(shape.maxValue.get())
        shape.worldSpace[0].connect(endPoci.ic)
        nodes['endPoci'] = endPoci

        cvi = pm.createNode('curveInfo')
        shape.worldSpace[0].conenct(cvi.inputCurve)
        nodes['cvi'] = cvi
        
    else:
        cvi = nodes['cvi']
        endPoci = nodes['endPoci']

    epoci =  pm.createNode(type='network')
    epoci.addAttr(ln = 'inputCurve', sn='ic', dt='nurbsCurve')
    epoci.addAttr(ln = 'parameter', sn='pr', at='double', dv=0)
    epoci.addAttr(ln = 'position', sn='p', at='double')    
    shape.worldSpace[0].connect(epoci.ic)
    
    
    paramMult = pm.createNode('multiplyDivide')
    epoci.parameter.connect(paramMult.input1X)
    paramMult.input2X.get(curve.maxValue.get())
    paramMult.operation.set(2)

    magMult = pm.createNode('multipyDivide')
    paramMult.outputX.connect(magMult.input1X)
    cvi.arcLength.connect(paramMult.input2X)
    
    
    
    
def getLoc(infoNode, name, i=None):
    pass

def createIkSpineSystem(jnts, ctls, namer=None):
    if namer is None:
        namer = utils.Namer(character='char', part='spine')
        
    ikSpineNode = pm.createNode('transform', n=namer('ikspine'))
    ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
    ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)
        
    origCurve = cvCurveFromNodes(ctls)
    pm.parent(origCurve, ikSpineNode)
    
    origCurve = getShape(origCurve)
    bindControlsToShape(ctls, str(origCurve))

    #build a curve with a single span that has uniform parameterization
    uniCurve = pm.rebuildCurve(origCurve, kep=1, kt=1, d=7, rt=0, s=1, ch=1, rpo=False)[0]
    uniCurve = uniCurve.listRelatives(type='nurbsCurve')[0]
    uniCurve = getShape(uniCurve)
    
    surf = surfaceFromNodes(ctls)
    pm.parent(surf, ikSpineNode)
    
    bindControlsToShape(ctls, surf)
    surf = getShape(surf)
    
    #get an arclength to measure the whole curve
    curveAL = pm.createNode('curveInfo')
    
    origCurve.worldSpace[0].connect(curveAL.inputCurve)
    totalOrigAL = curveAL.arcLength.get()
    
    #crvJnts = createCrvJnts(jnts, uniCurve, asLocs=True)
    crvJnts = createCrvJnts(jnts, origCurve)
    for i, jnt in enumerate(crvJnts):
        jnt.rename(namer(d='ikcrv', x='jnt', alphaSuf=i))
        
    

    arcLenMultMDN = pm.createNode('multiplyDivide', name=namer('arclen_diff', s='mdn'))
    arcLenMultMDN.operation.set(2)
    curveAL.arcLength.connect(arcLenMultMDN.input1X)
    arcLenMultMDN.input2X.set(totalOrigAL)
    
    curveMaxParam = origCurve.maxValue.get()

    

    addJointAttrs(crvJnts, origCurve, ikSpineNode)
    stretchPosLocs = []
    for i, jnt in enumerate(crvJnts):
        # for each joint, get a param value along the original curve.

        #blend between two parameter values on the original curve - uniform and non uniform stretch
        stretchParamBlend = pm.createNode('blendColors', name=namer('stretch_param', x='blc', alphaSuf=i))
        ikSpineNode.uniformStretch.connect(stretchParamBlend.b)
        poci = pm.createNode('pointOnCurveInfo', name=namer('stretch_result_pos', x='pci', alphaSuf=i))
        origCurve.worldSpace[0].connect(poci.inputCurve)
        stretchParamBlend.opr.connect(poci.pr)

        resultLoc = pm.spaceLocator(name=namer('stretch_result_pos', x='loc', alphaSuf=i))
        resultLoc.setParent(ikSpineNode)
        
        stretchPosLocs.append(resultLoc)
        
        poci.p.connect(resultLoc.t)
        
        #get the param for the non-uniform stretch - 
        p = closestParamOnCurve(origCurve, jnt)
        pci = pm.createNode('pointOnCurveInfo', name=namer('stretch', x='pci', alphaSuf=i))
        origCurve.worldSpace[0].connect(pci.inputCurve)
        pci.pr.set(p)
        pci.pr.connect(stretchParamBlend.c2r)

        #get the point in space along the uniform curve
        p = closestParamOnCurve(uniCurve, jnt)
        pci = pm.createNode('pointOnCurveInfo', name=namer('unistretch', x='pci', alphaSuf=i))
        uniCurve.worldSpace[0].connect(pci.inputCurve)
        pci.pr.set(p)
        #get the param on the non-uniform curve to that point
        npc = pm.createNode('nearestPointOnCurve', name=namer('unistretch_point_to_orig', x='npc', alphaSuf=i))
        origCurve.worldSpace[0].connect(npc.inputCurve)
        pci.p.connect(npc.ip)
        
        npc.pr.connect(stretchParamBlend.c1r)

        

    #use splineIK for non-stretching joints
    nsCurveJnts = utils.makeDuplicatesAndHierarchy(crvJnts, toReplace='ikcrv', replaceWith='ns_ikcrv')
    handle, ee = pm.ikHandle(solver='ikSplineSolver', sj=nsCurveJnts[0], ee=nsCurveJnts[-1], curve=origCurve,
                simplifyCurve=False, parentCurve=False, createCurve=False)
    handle.v.set(0)
    
    nsPosLocs = []    
    for i, jnt in enumerate(nsCurveJnts):
        loc = pm.spaceLocator(name=namer('ns_result_pos', x='loc', alphaSuf=i))

        pm.pointConstraint(jnt, loc)
        nsPosLocs.append(loc)
        jnt.v.set(0)
        
        loc.setParent(ikSpineNode)


    #create up vector locs for the no stretch joints.  For each joint, if the arc length
    #of the curve is less than the original arc length, use the max param value in U.  Otherwise,
    #use the U val of the closest point on the surface.  The V will always be .9 (near the edge)
    
    nsUpLocs = []
    for i, loc in enumerate(nsPosLocs):
        cps = pm.createNode('closestPointOnSurface', n=namer('ns_up_pos', x='cps', alphaSuf=i))
        surf.worldSpace[0].connect(cps.inputSurface)
        loc.t.connect(cps.ip)
        
        cnd = pm.createNode('condition', n=namer('ns_up_arclen', x='cnd', alphaSuf=i))
        origArcLen = getattr(ikSpineNode, 'origArcLen%i' % i)
        origArcLen.connect(cnd.secondTerm)
        curveAL.al.connect(cnd.firstTerm)
        cnd.operation.set(5)
        cnd.colorIfTrueR.set(curveMaxParam)
        cps.u.connect(cnd.colorIfFalseR)

        posi = pm.createNode('pointOnSurfaceInfo', n=namer('ns_up_pos', x='psi', alphaSuf=i))
        surf.worldSpace[0].connect(posi.inputSurface)
        cnd.outColorR.connect(posi.u)
        posi.v.set(.9)

        upLoc = pm.spaceLocator(name=namer('ns_result_up', x='loc', alphaSuf=i))
        posi.p.connect(upLoc.t)
        
    #blend the non-stretch and stretch positions to get the final position
    finalLocs = []
    finalPosBlends = []
    for i in range(len(nsPosLocs)):
        blend = pm.createNode('blendColors', n=namer('pos_result', x='blc'))
        stretchPosLocs[i].t.connect(blend.c1)
        nsPosLocs[i].t.connect(blend.c2)
        ikSpineNode.stretchAmt.connect(blend.blender)
        
        nsPosLocs[i].v.set(0)
        stretchPosLocs[i].v.set(0)

        loc = pm.spaceLocator(name=namer('result', x='loc', alphaSuf=i))
        blend.op.connect(loc.t)
        
        finalLocs.append(loc)
        finalPosBlends.append(blend)
        
    return

    addDistanceAttrs(finalPosLocs, keepConnection=True)

    upVecLocs = []
    for i in range(len(finalPosLocs)):
        
        loc = finalPosLocs[i]
        end=False
        if i == (len(finalPosLocs)-1):
            end=True
            nextLoc = finalPosLocs[i-1]
            aimVec = [0,-1,0]
        else:
            nextLoc = finalPosLocs[i+1]
            aimVec=[0,1,0]
        
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

        if not end:
            scaleMDN = pm.createNode('multiplyDivide', n=namer('scl', s='mdn'))
            loc.distToNext.connect(scaleMDN.input1X)
            crvJnts[i].distToNext.connect(scaleMDN.input2X)
            scaleMDN.operation.set(2)        
            scaleMDN.outputX.connect(crvJnts[i].sy)
        
        pm.pointConstraint(loc, crvJnts[i])
        
        pm.aimConstraint(nextLoc, crvJnts[i], aimVector=aimVec, upVector=[1,0,0],
                         worldUpType='object', worldUpObject=str(upLoc))
        

    return
        
def _doIt(path =  None):
    import maya.cmds as MC
    import pymel.core as pm
    if not path:
        path = '/Users/jspatrick/Documents/maya/projects/beingsTests/scenes/spineJnts.mb'
        
    MC.file(path, f=1, o=1)

    ctls = [pm.PyNode(n) for n in [u'ctl_a', u'ctl_b', u'ctl_c', u'ctl_d']]
    jnts = [pm.PyNode(n) for n in [u'bnd_a', u'bnd_b', u'bnd_c', u'bnd_d', u'bnd_e']]
    createIkSpineSystem(jnts, ctls)
    
if __name__ == '__main__':
    _doIt()
