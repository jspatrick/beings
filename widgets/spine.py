"""
import maya.cmds as MC
import beings.widgets.fkChain as FKC

MC.file(new=1, f=1)
reload(FKC)
fkc = FKC.Neck()
fkc.buildLayout()
"""
from string import ascii_lowercase
import maya.cmds as MC
import maya.mel as MM
import maya.OpenMaya as OM

import beings.core as core
import logging
from beings import control
from beings import utils

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

def strToObj(node, asHandle=False):
    """
    Return an MObject from a string node
    @param node: the node name
    @type node: str
    @param asHandle: Return an MObjectHandle
    @type asHandle: True
    @return: the api object
    @rtype: MObject or MObjectHandle
    """
    sl = OM.MSelectionList()
    sl.add(node)
    obj = OM.MObject()
    sl.getDependNode(0, obj)
    if asHandle:
        obj = OM.MObjectHandle(obj)

    return obj


def strToDagPath(node):
    """
    Return an MDagPath instance form a string node
    @param node: the node name
    @type node: str
    @return: MDagPath instace
    @rtype: MDagPath
    """
    sl = OM.MSelectionList()
    sl.add(node)
    dp = OM.MDagPath()
    sl.getDagPath(0, dp)
    return dp


def nodeToStr(node):
    """Get a string node name from an api object
    @param node: the node object
    @type node: MObject, MObjectHandle, or MDagPath
    @return: node name
    @rtype: str
    """
    if isinstance(node, OM.MDagPath):
        return node.partialPathName()

    if isinstance(node, OM.MObjectHandle):
        if not node.isValid:
            raise RuntimeError("object no longer exists")
        node = node.object()

    if not isinstance(node, OM.MObject):
        raise RuntimeError("Invalid arg - %r" % node)

    if node.hasFn(OM.MFn.kDagNode):
        pathArray = OM.MDagPathArray()

        OM.MDagPath.getAllPathsTo(node, pathArray)
        if pathArray.length() > 1:
            _logger.warning("Multiple paths for node, returning first")

        return pathArray[0].partialPathName()

    return OM.MFnDependencyNode(node).name()


def getShape(crv):
    """If crv is a shape node, return it.  If it is
    a transform with a single shape parent, return the shape.

    @param crv: the shape or transform node
    @raise RuntimeError: if node is not a shape and has multiple
      or no shape children
    """

    if MC.objectType(crv, isAType='geometryShape'):
        return crv

    result = None
    shapes = MC.listRelatives(crv) or []
    for shape in shapes:
        #ni flag broken?
        if MC.getAttr('%s.intermediateObject' % shape):
            continue

        if MC.objectType(shape, isAType='geometryShape'):
            if result is not None:
                raise RuntimeError("Multiple shapes under '%s'" % crv)
            result = shape

    if result is None:
        raise RuntimeError("No shapes under '%s'" % crv)
    return result


def closestPointOnNurbsObj(xformNode, nurbsObj, worldSpace=False):
    """Get closest point to a nurbs surface or curve in the curve's
    object space

    @param xformNode: a transform node
    @type xformNode: str
    @param nurbsObj: the curve xform or shape node
    @type nurbsObj: str
    @param: return the point in worldspace
    @return: closest world-space position on the nurbs object
    @rtype: 3-float list, ie [3.4, 2.3, 4.4]
    """

    shape = getShape(nurbsObj)
    shapeXform = MC.listRelatives(shape, parent=1)[0]
    dp = strToDagPath(shape)
    node = dp.node()
    if node.hasFn(OM.MFn.kNurbsCurve):
        fn = OM.MFnNurbsCurve(dp)
    elif node.hasFn(OM.MFn.kNurbsSurface):
        fn = OM.MFnNurbsSurface(dp)

    crvParentMatrix = strToDagPath(shapeXform).inclusiveMatrix()

    #get the position in objet space of the curve
    nodePos = OM.MPoint(*MC.xform(xformNode, q=1, rp=1, ws=1))
    if worldSpace:
        nodePos *= crvParentMatrix.inverse()

    pnt = fn.closestPoint(nodePos)

    if worldSpace:
        #back to world space
        pnt *= crvParentMatrix

    return [pnt.x, pnt.y, pnt.z]


def closestParamOnCurve(node, crv):
    """Get the closest parameter on the curve to the node"""
    pnt = closestPointOnNurbsObj(node, crv)
    print
    crv = getShape(crv)
    crvFn = OM.MFnNurbsCurve(strToDagPath(crv))
    su = OM.MScriptUtil()
    pDouble = su.asDoublePtr()

    crvFn.getParamAtPoint(OM.MPoint(*pnt), pDouble)

    return su.getDouble(pDouble)


def pointAtParam(crv, param):
    """
    Get the world-space position of a point along a nurbs curv
    """
    crv = getShape(crv)
    poci = MC.createNode('pointOnCurveInfo')
    MC.connectAttr('%s.worldSpace[0]' % crv, '%s.inputCurve' % poci)
    MC.setAttr('%s.pr' % poci, param)
    v = MC.getAttr("%s.p" % poci)[0]
    MC.delete(poci)
    return v

def pointAtParamPercentage(crv, pct):
    """
    Get the world-space position of a point at a certain
    percentage value along the curves parameterization
    @param crv: the curve
    @type crv: str
    @param pct: the percentage value along the curve, between 0 and 1
    @type pct: float
    """
    crv = getShape(crv)
    pct = min(max(pct, 0.0), 1.0)
    max_ = MC.getAttr('%s.maxValue' % crv)
    min_ = MC.getAttr('%s.minValue' % crv)

    return pointAtParam(crv, (min_ + max_ * pct))


def closestParamOnSurface(node, surf):
    surf = getShape(surf)

    pnt = closestPointOnNurbsObj(node, surf)
    srfFn = OM.MFnNurbsSurface(strToDagPath(surf))
    suU = OM.MScriptUtil()
    suV = OM.MScriptUtil()
    pDoubleU = suU.asDoublePtr()
    pDoubleV = suV.asDoublePtr()

    srfFn.getParamAtPoint(OM.MPoint(*pnt), pDoubleU, pDoubleV)

    return (suU.getDouble(pDoubleU), suV.getDouble(pDoubleV))


def curveFromNodes(nodes, name='crv', doubleEndPoints=False):
    #cmd = ['curve -d 2 -k 0 -name "%s"' % name]
    cmd = ['curve -d 2 -name "%s"' % name]

    # for i in range(len(nodes)-1):
    #     if not doubleEndPoints:
    #         cmd.append('-k %i' % i)
    # if not doubleEndPoints:
    #     cmd.append('-k %i' % (len(nodes)-2))
    positions = []

    for i, node in enumerate(nodes):
        positions.append(MC.xform(node, q=1, ws=1, rp=1))

    for i, p in enumerate(positions):
        if doubleEndPoints and i == len(nodes)-1:

            cmd.append('-p %f %f %f' % (p[0], p[1], p[2]))
            cmd.append('-p %f %f %f' % (p[0], p[1], p[2]))

        else:
            cmd.append('-p %f %f %f' % (p[0], p[1], p[2]))

    cmd = ' '.join(cmd)
    _logger.debug(cmd)
    return MM.eval(cmd)


def surfaceFromNodes(nodes, name='jntsSrf', upAxis=0, doubleEndPoints=False):
    """
    Create a 2-degree nurbs surface from the position of a list of
    node (generally, the IK controls)
    @param nodes: controls that will dictate the CV positions
    @type nodes: list of strings
    @param name: the name of the surface
    @type name: str
    @param upAxis: the direction of the width of the surface
    @type upAxis: int representing x(0), y(1) or z(2)
    """
    inPos = [0,0,0]
    outPos = [0,0,0]
    inPos[upAxis] = -1
    outPos[upAxis] = 1

    crv1 = curveFromNodes(nodes, doubleEndPoints=doubleEndPoints)
    crv2 = curveFromNodes(nodes, doubleEndPoints=doubleEndPoints)

    MC.xform(crv1, t=outPos)
    MC.xform(crv2, t=inPos)

    srf = MC.loft(crv1, crv2, u=1, c=0, ch=0, ar=1, d=1, ss=1, rn=0, po=0, rsn=True)[0]
    srf = MC.rename(srf, name)
    MC.delete(crv1, crv2)

    return srf


def bindControlsToShape(ctls, shape, doubleEndPoints=False):
    """
    Cluster bind the controls to a curve.  Curve must have same num of points in u
    as num ctls


    """
    _logger.debug('binding %s' % shape)
    shape = getShape(shape)
    if MC.objectType(shape, isAType='nurbsSurface'):
        dv = MC.getAttr('%s.degreeV' % shape)
        suff = '[0:%i]' % dv

    elif MC.objectType(shape, isAType='nurbsCurve'):
        suff = ""
    else:
        raise RuntimeError("Bad input shape %s" % shape)

    for i, ctl in enumerate(ctls):

        if doubleEndPoints:
            if i == len(ctls)-1:
                cmpts = '%s.cv[%i:%i]%s' % (shape, i, i+1, suff)
            else:
                cmpts = '%s.cv[%i]%s' % (shape, i, suff)

        else:
            cmpts = '%s.cv[%i]%s' % (shape, i, suff)

        print cmpts
        cls, handle = MC.cluster(cmpts)
        handleShape  = MC.listRelatives(handle)[0]

        MC.disconnectAttr('%s.worldMatrix[0]' % handle, '%s.matrix' % cls)
        MC.disconnectAttr('%s.clusterTransforms[0]' % handleShape, '%s.clusterXforms' % cls)

        MC.delete(handle)

        MC.setAttr('%s.bindPreMatrix' % cls, MC.getAttr('%s.worldInverseMatrix[0]' % ctl), type='matrix')
        MC.connectAttr('%s.worldMatrix[0]' % ctl, '%s.matrix' % cls)


def createBeingsSplineObjs(numIkCtls, numBndJnts, ctlSep=2, namer=None, ctlKwargs=None, doubleEndPoints=False):
    """
    Create the components needed for a spline setup - ik controls, joints,
    a nurbs plane and a nurbs curve.
    @param numIkCtls: the number of ik controls to create
    @param numBndJnts: the number of bind joints to create.  An extra 'tip' joint will
      also be created, so the total joints returned will be 1+numBndJnts
    """
    if not namer:
        namer = utils.Namer('char', 'cn', 'spine')


    result = {}


    MC.select(cl=1)
    bndJnts = []
    bndPosInc = ((numIkCtls-1) * ctlSep)/float(numBndJnts-1)
    for i in range(numBndJnts):
        pos = [0, i*bndPosInc, 0]
        name = namer(alphaSuf = i, r='bnd')
        if i == numBndJnts-1:
            name = namer('tip', r='bnd')
        j = MC.joint(p=pos, n=name)

        bndJnts.append(j)

    ikCtls = []

    if not ctlKwargs:
        ctlKwargs = {'s': [2.5,.5, 2.5]}

    for i in range(numIkCtls):
        ikCtl = control.makeControl(namer('layout_ctl', r='ik', alphaSuf=i), **ctlKwargs)
        if i < numIkCtls:
            MC.setAttr('%s.ty' % ikCtl, i * ctlSep)
        else:
            MC.setAttr('%s.ty' % ikCtl, ((i-1) * ctlSep)+bndPosInc)
        ikCtls.append(ikCtl)


    result['curve'] = crv = curveFromNodes(ikCtls, name=namer('ikspline_crv'), doubleEndPoints=doubleEndPoints)
    result['surface'] = srf = surfaceFromNodes(ikCtls, name=namer('ikspline_srf'), doubleEndPoints=doubleEndPoints)

    result['ikCtls'] = ikCtls


    utils.fixInverseScale(bndJnts)

    result['jnts']  = bndJnts

    bindControlsToShape(ikCtls, crv,  doubleEndPoints=doubleEndPoints)
    bindControlsToShape(ikCtls, srf,  doubleEndPoints=doubleEndPoints)
    return result



def setupIkSplineJnts(jntList, crv, surf, ikNode,
                         nodeName='beings_splineik', namer=None,
                         tipCtl=None):

    """
    Setup a splineIk system, but use a nurbs surface to control orientation.
    This allows full twist control along the length of the chain

    @param jntList: the list of original joints; they will be duplicated
    @param crv: the curve to use for the spline ik system
    @param surf: the surface to use for the twist
    @param namer: the namer to use for naming; a generic will be assigned if none provided
    @param tipCtl: a control to use for orienting the last joint.  If none provided,
    it will be oriented to the plane
    """
    if not namer:
        namer = utils.Namer('char', 'cn', 'spine')


    namer.setTokens(r='ik')
    #use the splineik node to get joints to 'slip' alone the curve.  These are intermediate
    #joints, we're just using their position to get us a point on the nurbs surface so we
    #can use the surface for orientation
    jntNames = ['%s_pos_jnt_%s' % (nodeName, ascii_lowercase[i]) for i in range(len(jntList))]
    splinePosJnts = utils.dupJntList(jntList, jntNames, namer)
    for jnt in splinePosJnts:
        control.setLockTag(jnt, uu=['t', 'r'])

    #these are the actual joints that will be oriented and positioned correctly
    jntNames = ['%s_jnt_%s' % (nodeName,ascii_lowercase[i]) for i in range(len(jntList))]
    splineJnts = utils.dupJntList(jntList, jntNames, namer)

    handle, ee = MC.ikHandle(solver='ikSplineSolver',
                             sj=splinePosJnts[0], ee=splinePosJnts[-1], curve=crv,
                             simplifyCurve=False, parentCurve=False, createCurve=False)
    MC.parent(handle, ikNode)
    xforms = []
    ups = []

    for i, jnt in enumerate(splinePosJnts):
        dcm = MC.createNode('decomposeMatrix', n=namer('%s_splinejnt_dcm' % nodeName, alphaSuf=i))
        cps = MC.createNode('closestPointOnSurface', n=namer('%s_splinejnt_cps' % nodeName, alphaSuf=i))

        posi = MC.createNode('pointOnSurfaceInfo', n=namer('%s_splinejnt_posi' % nodeName, alphaSuf=i))
        xform = MC.createNode('transform', n=namer('%s_splinejnt_grp' % nodeName, alphaSuf=i))
        xformUp = MC.createNode('transform', n=namer('%s_splinejnt_up_grp' % nodeName, alphaSuf=i))
        MC.parent(xform, ikNode)
        MC.parent(xformUp, ikNode)


        MC.connectAttr('%s.worldMatrix' % jnt, '%s.inputMatrix' % dcm)
        MC.connectAttr("%s.worldSpace[0]" % surf, '%s.inputSurface' % cps)
        MC.connectAttr("%s.outputTranslate" % dcm, "%s.ip" % cps)
        MC.connectAttr("%s.p" % cps, "%s.t" % xform)

        MC.connectAttr("%s.worldSpace[0]" % surf, '%s.inputSurface' % posi)
        MC.connectAttr("%s.u" % cps, "%s.u" % posi)
        MC.setAttr("%s.v" % cps, MC.getAttr("%s.v" % cps) + .1)
        MC.connectAttr("%s.p" % posi, "%s.t" % xformUp)
        xforms.append(xform)
        ups.append(xformUp)
        MC.pointConstraint(splinePosJnts[i], splineJnts[i])

    for i in range(len(splinePosJnts)-1):
        MC.aimConstraint(splinePosJnts[i+1],
                         xforms[i],
                         aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpType='object',
                         worldUpObject=ups[i])

        utils.fixJointConstraints(xforms[i])
        MC.orientConstraint(xforms[i], splineJnts[i])
        utils.fixJointConstraints(splineJnts[i])
    if tipCtl:
        MC.orientConstraint(tipCtl, splineJnts[-1])
        utils.fixJointConstraints(splineJnts[-1])

    MC.setAttr("%s.v" % splinePosJnts[0], 0)
    MC.setAttr("%s.v" % handle, 0)

    return (splineJnts, splinePosJnts, ups)


def aimXforms(xforms, upXforms, posiNodes, ikNode):
    numXforms = len(xforms)



def setupSpineIkNode(ctlList, jntList, surf=None, crv=None, nodeName='beings_splineik', namer=None):
    """
    Create an ik spline system using controls in the ctlList that will drive jnts in jntList
    """
    if not namer:
        namer = utils.Namer('char', 'cn', 'spine')
    if not surf:
        surf = surfaceFromNodes(ctlList)
    surf = getShape(surf)
    if not crv:
        crv = curveFromNodes(ctlList)
    crv = getShape(crv)

    ikNode = MC.createNode('transform', name=namer(nodeName))
    MC.parent(MC.listRelatives(surf, parent=1)[0], ikNode)
    MC.parent(MC.listRelatives(crv, parent=1)[0], ikNode)

    namer.setTokens(r='ik')
    names = ['stretch_%s' % ascii_lowercase[i] for i in range(len(jntList))]
    stretchJnts = utils.dupJntList(jntList, names, namer)

    #rebuild the curve so that we get more even parameterization for 'even stretch'
    #joints.  Use a 7 degree curve so we can build with a single span
    evenStretchCrv = MC.rebuildCurve(MC.listRelatives(crv, parent=1)[0],
                    ch=1, rpo=0, rt=0, end=1, kr=2, kcp=0, kep=1, kt=0, s=1, d=7, tol=0.01)[0]
    evenStretchCrv = MC.rename(evenStretchCrv, "%s_evenstretch" % crv)
    MC.parent(evenStretchCrv, ikNode)
    evenStretchCrv = getShape(evenStretchCrv)


    nodes = {'posi':[], 'cps': [], 'posiUp':[], 'xform':[], 'xformUp':[]}

    #for each joint, get the param at the rebuilt curve.  Use this position to get
    #the closest point on the surface, then get the u and v values at that surface
    #point.
    for i, jnt in enumerate(stretchJnts):
        suff = ascii_lowercase[i]
        #get point on rebuild curve near each jnt
        poci = MC.createNode('pointOnCurveInfo', n='%s_%s_evenstretch_poci' % (ikNode, suff))
        MC.connectAttr("%s.worldSpace[0]" % evenStretchCrv, '%s.ic' % poci)
        MC.setAttr('%s.pr' % poci, closestParamOnCurve(jnt, evenStretchCrv))

        #get closest point on surface
        cps = MC.createNode("closestPointOnSurface", n='%s_%s_evenstretch_cps' % (ikNode, suff))
        MC.connectAttr("%s.worldSpace[0]" % surf, '%s.is' % cps)
        MC.connectAttr("%s.p" % poci, "%s.ip" % cps)
        nodes['cps'].append(cps)


    MC.addAttr(ikNode, ln='evenStretchAmt', min=0, max=1, k=1)

    for i, jnt in enumerate(stretchJnts):

        #create a point on surface info node at each point
        suff = ascii_lowercase[i]
        posi = MC.createNode('pointOnSurfaceInfo', n='%s_%s_posi' % (ikNode, suff))
        posiUp = MC.createNode('pointOnSurfaceInfo', n='%s_%s_up_posi' % (ikNode, suff))
        MC.connectAttr('%s.worldSpace[0]' % surf, '%s.is' % posi)
        MC.connectAttr('%s.worldSpace[0]' % surf, '%s.is' % posiUp)

        u, v = closestParamOnSurface(jnt, surf)

        for node in [posi, posiUp]:
            blender = MC.createNode("blendColors", name='%s_%s_evenstretch_blc' % (ikNode, suff))
            MC.connectAttr('%s.evenStretchAmt' % ikNode, '%s.blender' % blender)
            #as the evenStretchAmt increases, shift towards the u value of the even stretch crv
            MC.connectAttr("%s.u" % nodes['cps'][i], "%s.c1r" % blender)
            MC.setAttr("%s.c2r" % blender, u)
            MC.connectAttr("%s.opr" % blender, '%s.u' % node)


        MC.setAttr('%s.v' % posi, v)
        MC.setAttr('%s.v' % posiUp, v-.25)

        posXform = MC.createNode("transform", n='%s_%s_grp' % (ikNode, suff))
        upXform = MC.createNode("transform", n='%s_%s_up_grp' % (ikNode, suff))
        MC.parent(posXform, ikNode)
        MC.parent(upXform, ikNode)

        MC.connectAttr("%s.p" % posi, "%s.t" % posXform)
        MC.connectAttr("%s.p" % posiUp, "%s.t" % upXform)

        MC.pointConstraint(posXform, jnt)
        utils.fixJointConstraints(posXform)

        nodes['posi'].append(posi)
        nodes['posiUp'].append(posiUp)
        nodes['xform'].append(posXform)
        nodes['xformUp'].append(upXform)

    #now that all the xforms are created, aim them at each other and
    #measure the start stretch distance
    MC.addAttr(ikNode, ln='inputScaleAmt', dv=1, k=1)

    for i in range(len(stretchJnts)-1):
        suff = ascii_lowercase[i]
        nextSuff = ascii_lowercase[i+1]

        dst = MC.createNode('distanceBetween', n='%s_%s_to_%s_dist' % \
                      (ikNode,suff, nextSuff))

        MC.connectAttr("%s.p" % nodes['posi'][i], '%s.p1' % dst)
        MC.connectAttr("%s.p" % nodes['posi'][i+1], '%s.p2' % dst)
        MC.addAttr(ikNode, ln = "origDistToNext_%s" % suff, h=False,
                   dv=MC.getAttr("%s.d" % dst))
        stretchMdn = MC.createNode("multiplyDivide",
                                   n='%s_%s_stretch_mdn' % (ikNode, suff))

        MC.connectAttr('%s.d' % dst, '%s.input1X' % stretchMdn)
        MC.connectAttr('%s.origDistToNext_%s' % (ikNode, suff),
                       '%s.input2X' % stretchMdn)
        MC.setAttr('%s.operation' % stretchMdn, 2)

        stretchSclMdn = MC.createNode("multiplyDivide",
                                   n='%s_%s_stretch_scl_mdn' % (ikNode, suff))

        MC.setAttr('%s.operation' % stretchSclMdn, 2)
        MC.connectAttr('%s.outputX' % stretchMdn, '%s.input1X' % stretchSclMdn)
        MC.connectAttr('%s.inputScaleAmt' % ikNode, '%s.input2X' % stretchSclMdn)

        MC.addAttr(ikNode, ln = "stretchAmt_%s" % suff, k=1)
        MC.connectAttr('%s.outputX' % stretchSclMdn, '%s.stretchAmt_%s' \
                       % (ikNode, suff))

        #connect stretch amount to joint scale
        MC.connectAttr('%s.stretchAmt_%s' % (ikNode, suff),
                       '%s.sy' % stretchJnts[i])


        #aim the xforms
        MC.aimConstraint(nodes['xform'][i+1],
                         nodes['xform'][i],
                         aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpType='object',
                         worldUpObject=nodes['xformUp'][i])


        MC.orientConstraint(nodes['xform'][i], stretchJnts[i])
        utils.fixJointConstraints(stretchJnts[i])
        utils.fixJointConstraints(nodes['xform'][i])

    MC.orientConstraint(ctlList[-1], stretchJnts[-1])
    utils.fixJointConstraints(stretchJnts[-1])

    nsJnts, nsPosJnts, esUps = setupIkSplineJnts(jntList, crv, surf, ikNode,
                         namer = namer,
                         nodeName='%s_ns' % nodeName,
                         tipCtl = ctlList[-1])

    MC.addAttr(ikNode, ln='stretchAmt', min=0, max=1, dv=0, k=1)
    utils.blendJointChains(nsJnts, stretchJnts, jntList, '%s.stretchAmt' % ikNode, namer)

    MC.setAttr("%s.v" % nsJnts[0], 0)
    MC.setAttr("%s.v" % stretchJnts[0], 0)


    return ikNode


def bindNodesToSurface(nodes, surface, skipTipOrient=False):
    """Bind a node to the closest point on a surface
    @param node: the dag node to bind
    @param surface: the surface to bind to
    @param skipTipOrient: do not constrain orientation of the last node"""
    surface = str(surface)

    xforms = []
    xformUps = []
    cposes = []
    for node in nodes:
        node = str(node)


        u, v = closestParamOnSurface(node, surface)
        cpos = MC.createNode('pointOnSurfaceInfo', name='%s_surfacebind' % node)
        cposUp = MC.createNode('pointOnSurfaceInfo', name='%s_surfacebind_up' % node)
        cposes.append(cpos)
        MC.setAttr("%s.u" % cpos, u)
        MC.setAttr("%s.v" % cpos, v)

        MC.setAttr("%s.u" % cposUp, u)
        MC.setAttr("%s.v" % cposUp, v-.1)

        MC.connectAttr("%s.worldSpace[0]" % surface, "%s.inputSurface" % cpos)
        MC.connectAttr("%s.worldSpace[0]" % surface, "%s.inputSurface" % cposUp)
        worldSpaceXform = MC.createNode('transform', n='%s_surfacebind_dnt' % node)
        worldSpaceXformUp = MC.createNode('transform', n='%s_surfacebind_up_dnt' % node)
        xforms.append(worldSpaceXform)
        xformUps.append(worldSpaceXformUp)

        MC.connectAttr("%s.p" % cpos, "%s.t" % worldSpaceXform)
        MC.connectAttr("%s.p" % cposUp, "%s.t" % worldSpaceXformUp)



    for i in range(len(nodes)):
        if i == len(nodes)-1:
            this = xforms[i]
            if skipTipOrient:
                MC.pointConstraint(this, nodes[i])
                return


            tgt = xformUps[i]
            up = xformUps[i-1]
            aimVec = [1,0,0]
            upVec = [0,-1,0]
        else:
            this = xforms[i]
            tgt = xforms[i+1]
            up = xformUps[i]
            aimVec = [0,1,0]
            upVec = [1,0,0]


        MC.aimConstraint(tgt, this,
                         upVector=upVec,
                         aimVector=aimVec,
                         worldUpType='object',
                         worldUpObject=up)

        MC.parentConstraint(this, nodes[i])
        #utils.fixJointConstraints(nodes[i])


class Spine(core.Widget):
    def __init__(self):
        super(Spine, self).__init__('spine')

        self.options.addOpt('numJnts', 6, min=2, optType=int)
        self.options.addOpt('numIkCtls', 4, min=2, optType=int)

        self.options.subscribe('optChanged', self.__optionChanged)

        self.__setPlugs()

    def __getToks(self, bndJnts=False, ikCtls=False):
        toks = []
        if bndJnts:
            toks = ['pelvis']
            for i in range(self.options.getValue('numJnts')):
                toks.append('%s' % ascii_lowercase[i])

        if ikCtls:
            for i in range(self.options.getValue('numIkCtls')):
                toks.append('ctl_%s' % ascii_lowercase[i])

        return toks

    def __setPlugs(self):

        newPlugs = set(self.__getToks(bndJnts=True, ikCtls=True))
        currentPlugs = set([x for x in self.plugs()])
        toRemove = currentPlugs.difference(newPlugs)
        toAdd = newPlugs.difference(currentPlugs)
        _logger.debug("Adding plugs: %s; Removing plugs: %s" % (toAdd, toRemove))

        for plug in toRemove:
            self.rmPlug(plug)
        for plug in toAdd:
            self.addPlug(plug)


    def __optionChanged(self, event):
        self.__setPlugs()


    def _makeLayout(self, namer):


        MC.select(cl=1)
        jnts = []
        layoutCtls= []
        rigCtls = []

        #the number of ik controls will really be 1 greater than this, because
        #we will parent the first ik control the the first fk control and hide
        #it
        numIkCtls = self.options.getValue('numIkCtls')
        numJnts = self.options.getValue('numJnts')

        ctlKwargs = {'shape': 'sphere',
                     'color': 'purple',
                     's': [1.5, .5, 1.5]}

        doubleEndPoints=False
        if numIkCtls == 2:
            doubleEndPoints=True

        nurbsObjs = createBeingsSplineObjs(numIkCtls, numJnts, namer=namer,
                                           ctlKwargs = ctlKwargs,
                                           doubleEndPoints=doubleEndPoints)

        jntToks = self.__getToks(bndJnts=True)

        #create a pelvis joint that will remain oriented to the base control
        jnts = nurbsObjs['jnts']
        baseJnt = MC.joint(name=jntToks[0])
        utils.fixInverseScale([baseJnt])
        jnts.insert(0, baseJnt)

        for i in range(len(jnts)):
            jnts[i] = MC.rename(jnts[i], namer(jntToks[i], r='bnd'))
            self.registerBindJoint(jnts[i])



        tipXform = MC.xform(jnts[-1], q=1, t=1, ws=1)
        tipXform[1] = tipXform[1] + 2
        MC.select(jnts[-1])
        tip = MC.joint(p=tipXform,
                 n=namer('tip', r='bnd'))
        jnts.append(tip)

        bindNodesToSurface(jnts[:-1], nurbsObjs['surface'], skipTipOrient=True)
        #MC.orientConstraint(nurbsObjs['ikCtls'][-1], jnts[-2])


        #create ik rig controls
        ikRigCtls = []
        ikToks = self.__getToks(ikCtls=True)
        for i, ctl in enumerate(nurbsObjs['ikCtls']):
            self.registerControl(ctl, 'layout', uk=['ty','tz'])

            kwargs = {'color': 'yellow',
                      'shape': 'circle',
                      's': [2, 2, 2]}

            n = namer(ikToks[i], r='ik')

            rigCtl = control.makeControl(n, **kwargs)
            MC.parent(rigCtl, ctl)
            MC.makeIdentity(rigCtl, t=1, r=1, s=1)
            control.setEditable(rigCtl, True)
            self.registerControl(rigCtl, 'rig')
            ikRigCtls.append(rigCtl)


        for i, tok in enumerate(jntToks[1:]):
            kwargs = {'color':'green',
                      'shape':'cube',
                      's': [2,2,2]}

            rigCtl = control.makeControl(namer(tok, r='fk'), **kwargs)
            utils.snap(jnts[i+1], rigCtl)
            MC.parent(rigCtl, jnts[i+1])

            control.setEditable(rigCtl, True)
            self.registerControl(rigCtl, 'rig')


        #make a tip joint control
        tipCtl = control.makeControl(namer('tip_layout'),
                                     shape='cube',
                                     s=[.75, .75, .75],
                                     color='purple')
        utils.snap(tip, tipCtl)
        MC.parent(tipCtl, nurbsObjs['ikCtls'][-1])
        self.registerControl(tipCtl, 'layout', uk=['ty', 'tz'])
        MC.pointConstraint(tipCtl, jnts[-1])
        MC.aimConstraint(tipCtl, jnts[-2],
                         aimVector = [0,1,0],
                         upVector = [1,0,0],
                         worldUpVector=[1,0,0])
        MC.parentConstraint(jnts[-2], ikRigCtls[-1])


    def _makeRig(self, namer):

        jntCnt =  self.options.getValue('numJnts')
        ikCtlCnt =  self.options.getValue('numIkCtls')
        jntToks = self.__getToks(bndJnts=True)
        ctlToks = self.__getToks(ikCtls=True)

        bndJnts = [namer(t, r='bnd') for t in jntToks]

        MC.makeIdentity(bndJnts, apply=True, r=1, t=1, s=1)

        namer.setTokens(r='fk')

        fkCtls = [namer(t, r='fk') for t in jntToks[1:]]
        fkCtls = control.setupFkCtls(bndJnts[1:], fkCtls, jntToks[1:], namer)
        for ctl in fkCtls:
            control.setLockTag(ctl, uk=['rx', 'ry', 'rz'])

        for i, tok in enumerate(jntToks):
            self.setPlugNode(tok, bndJnts[i])

        namer.setTokens(r='ik')
        ikJnts = utils.dupJntList(bndJnts[1:], jntToks[1:], namer)
        MC.setAttr('%s.v' % ikJnts[0], 0)

        ikCtls = []

        for tok in ctlToks:
            n = namer(tok, r='ik')
            utils.insertNodeAbove(n)
            control.setLockTag(n, uk=['r', 't'])
            ikCtls.append(n)
            self.setPlugNode(tok, n)

        #doubling the cvs on the end allows us to build a curve with only 2 controls,
        #but causes popping otherwise.  Only use if needed
        doubleEndPoints = False
        if ikCtlCnt == 2:
            doubleEndPoints = True

        crv = curveFromNodes(ikCtls, name=namer('ikspline_crv'), doubleEndPoints=doubleEndPoints )
        srf = surfaceFromNodes(ikCtls, name=namer('ikspline_srf'), doubleEndPoints=doubleEndPoints)

        bindControlsToShape(ikCtls, crv,  doubleEndPoints=doubleEndPoints)
        bindControlsToShape(ikCtls, srf,  doubleEndPoints=doubleEndPoints)

        ikNode = setupSpineIkNode(ikCtls, ikJnts, nodeName='splinik', namer=namer,
                         crv=crv, surf=srf)

        self.setNodeCateogry(ikNode, 'dnt')
        MC.setAttr("%s.v" % ikNode, 0)


        #parent the fk control to the ik control
        MC.parent(fkCtls[0], ikCtls[0])
        utils.fixInverseScale(fkCtls[0])

        #constrain the pelvis jnt to the first ik control
        MC.parentConstraint(ikCtls[0], bndJnts[0])
        MC.scaleConstraint(ikCtls[0], bndJnts[0])

        #tag this node so the master connect the uniform scale
        core.Root.tagInputScaleAttr(ikNode, 'inputScaleAmt')

        MC.addAttr(ikCtls[-1], ln='fkIk', dv=1, k=1, min=0, max=1)
        MC.addAttr(ikCtls[-1], ln='stretchAmt', dv=0, k=1, min=0, max=1)
        MC.addAttr(ikCtls[-1], ln='evenStretchAmt', dv=0, k=1, min=0, max=1)

        control.setLockTag(ikCtls[-1], uk=['fkIk', 'stretchAmt', 'evenStretchAmt'])

        MC.connectAttr('%s.stretchAmt' % ikCtls[-1], '%s.stretchAmt' % ikNode)
        MC.connectAttr('%s.evenStretchAmt' % ikCtls[-1], '%s.evenStretchAmt' % ikNode)


        #parent the ikCtls
        parentToFirst = []
        parentToLast = []

        numParentedCtlsPerSide = (int(ikCtlCnt)/2)-1

        parentToFirst = ikCtls[1:1+numParentedCtlsPerSide]
        parentToLast = ikCtls[-1 - numParentedCtlsPerSide - (ikCtlCnt % 2):-1]

        _logger.debug('parentToFirst: %s' % parentToFirst)
        _logger.debug('parentToLast: %s' % parentToLast)

        for node in parentToFirst:
            zero = MC.listRelatives(node, parent=1)[0]
            MC.parent(zero, ikCtls[0])

        for node in parentToLast:
            zero = MC.listRelatives(node, parent=1)[0]
            MC.parent(zero, ikCtls[-1])


        ikReverse = utils.blendJointChains(fkCtls, ikJnts, bndJnts[1:], '%s.fkIk' % ikCtls[-1], namer)
        for ctl in fkCtls:
            MC.connectAttr('%s.outputX' % (ikReverse), '%s.v' % ctl)
        for ctl in ikCtls[1:-1]:
            MC.connectAttr('%s.fkIk' % (ikCtls[-1]), '%s.v' % ctl)


core.WidgetRegistry().register(Spine, "Spine", "An Ik/Fk spine")
