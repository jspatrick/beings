import logging
from string import ascii_lowercase
import maya.cmds as MC
import maya.mel as MM
import maya.OpenMaya as OM
import pymel.core as pm

import beings.core as core
import beings.utils as utils
import beings.control as CTL

reload(utils)
reload(CTL)
reload(core)

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
    return pm.PyNode(MM.eval(cmd)).getParent()


ORIG_ARC_LEN_ATTR = 'origArcLen%i'
ORIG_ARC_PERCENTAGE_ATTR = 'origArcPercentage%i'
ORIG_PARAM_ATTR = 'origParam%i'
DIST_TO_NEXT = 'distToNext%i'

def getDistanceNode(startNode, endNode, name, namer, num):
    dd = pm.createNode('distanceBetween', name=namer(name, x='dst', alphaSuf=num))
    startNode.t.connect(dd.p1)
    startNode.parentMatrix.connect(dd.im1)
        
    endNode.t.connect(dd.p2)
    endNode.parentMatrix.connect(dd.im2)

    return dd
    
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


# def paramAtNode(crv, node):
#     """
#     Return param
#     """    
#     npoc = pm.createNode('nearestPointOnCurve')
    
#     pm.connectAttr('%s.worldSpace[0]' % getShape(crv), '%s.inputCurve' % npoc)
#     pos = pm.xform(node, q=1, ws=1, rp=1)
#     pm.setAttr('%s.ip' % npoc, *pos)
#     p = pm.getAttr('%s.parameter' % npoc)
#     pm.delete(npoc)
#     return p


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
    

def createAimedLocs(posLocs, upLocs, name, namer, singleUpNode=None, upType='object'):
    result = []
    for i in range (len(posLocs)):
        upVec = [1,0,0]
        posLoc = posLocs[i]
        if singleUpNode:
            upLoc = singleUpNode
        else:
            upLoc = upLocs[i]
            
        finalLoc = pm.spaceLocator(name=namer(name, x='loc', alphaSuf=i))
        
        #final loc
        if i == (len(posLocs)-1):
            aimLoc = posLocs[i-1]
            aimVec = [0,-1,0]
        else:            
            aimLoc = posLocs[i+1]
            aimVec = [0,1,0]
            
            dist=getDistanceNode(posLoc, aimLoc, name, namer, i)
            mdn = pm.createNode('multiplyDivide', n=namer('%s_scl' % name, x='mdn', alphaSuf=i))
            dist.distance.connect(mdn.input1X)
            mdn.input2X.set(dist.distance.get())
            mdn.operation.set(2)
            mdn.outputX.connect(finalLoc.sy)
        
        aimCst = pm.aimConstraint(aimLoc, finalLoc, aimVector=aimVec, upVector=upVec,
                                  worldUpType=upType, worldUpObject=upLoc)
        posLocs[i].t.connect(finalLoc.t)
        result.append(finalLoc)
        
    return result
        

def createIkSpineSystem(jnts, ctls, namer=None, part=None):
    if namer is None:
        if part is None:
            part = 'spine'
        namer = utils.Namer(character='char', part=part)
        
    ikSpineNode = pm.createNode('transform', n=namer('ikspine'))
    ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
    ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)
    ikSpineNode.addAttr('inputScale', k=1, dv=1)    
    origCurve = cvCurveFromNodes(ctls)
    pm.rename(origCurve, namer('crv', x='crv'))
    pm.parent(origCurve, ikSpineNode)
    
    origCurve = getShape(origCurve)
    bindControlsToShape(ctls, str(origCurve))

    #build a curve with a single span that has uniform parameterization
    uniCurve = pm.rebuildCurve(origCurve, kep=1, kt=1, d=7, rt=0, s=1, ch=1, rpo=False)[0]
    uniCurve.rename(namer('ns', x='crv'))
    uniCurve = uniCurve.listRelatives(type='nurbsCurve')[0]
    uniCurve = getShape(uniCurve)
    
    surf = surfaceFromNodes(ctls)
    pm.rename(surf, namer('surf', x='nrb'))
    pm.parent(surf, ikSpineNode)
    
    bindControlsToShape(ctls, surf)
    surf = getShape(surf)
    
    #get an arclength to measure the whole curve
    curveAL = pm.createNode('curveInfo')
    
    origCurve.worldSpace[0].connect(curveAL.inputCurve)
    totalOrigAL = curveAL.arcLength.get()
    
    #crvJnts = createCrvJnts(jnts, uniCurve, asLocs=True)
    crvJnts = createCrvJnts(jnts, origCurve)
    crvJnts[0].setParent(ikSpineNode)
    
    for i, jnt in enumerate(crvJnts):
        jnt.rename(namer(d='ikcrv', x='jnt', alphaSuf=i))
        
    

    arcLenMultMDN = pm.createNode('multiplyDivide', name=namer('arclen_diff', s='mdn'))
    arcLenMultMDN.operation.set(2)
    curveAL.arcLength.connect(arcLenMultMDN.input1X)
    arcLenMultMDN.input2X.set(totalOrigAL)
    
    curveMaxParam = origCurve.maxValue.get()

    addJointAttrs(crvJnts, origCurve, ikSpineNode)
    stretchPosLocs = []
    stretchUpLocs = []    
    for i, jnt in enumerate(crvJnts):
        # for each joint, get a param value along the original curve.

        #blend between two parameter values on the original curve - uniform and non uniform stretch
        stretchParamBlend = pm.createNode('blendColors', name=namer('stretch_param', x='blc', alphaSuf=i))
        ikSpineNode.uniformStretch.connect(stretchParamBlend.b)
        poci = pm.createNode('pointOnCurveInfo', name=namer('stretch_result_pos', x='pci', alphaSuf=i))
        origCurve.worldSpace[0].connect(poci.inputCurve)
        stretchParamBlend.opr.connect(poci.pr)

        #create a locator on the curve at the blended parameter
        resultPosLoc = pm.spaceLocator(name=namer('stretch_result_pos', x='loc', alphaSuf=i))
        resultPosLoc.setParent(ikSpineNode)
        resultPosLoc.v.set(0)
        poci.p.connect(resultPosLoc.t)
        stretchPosLocs.append(resultPosLoc)
        
        #create a loctor on the nurbs surf at the blended parameter in u an .9 in v
        resultUpLoc = pm.spaceLocator(name=namer('stretch_result_up', x='loc', alphaSuf=i))        
        resultUpLoc.setParent(ikSpineNode)
        resultUpLoc.v.set(0)
        posi = pm.createNode('pointOnSurfaceInfo', name=namer('stretch_result_up', x='loc', alphaSuf=i))
        surf.worldSpace[0].connect(posi.inputSurface)
        stretchParamBlend.opr.connect(posi.u)
        posi.v.set(0.9)
        posi.p.connect(resultUpLoc.t)                             
        stretchUpLocs.append(resultUpLoc)
        
        
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
        
    stretchFinalLocs = createAimedLocs(stretchPosLocs, stretchUpLocs, 'stretch_result', namer)
    pm.parent(stretchFinalLocs, ikSpineNode)
    
    #use splineIK for non-stretching joints
    nsCurveJnts = utils.makeDuplicatesAndHierarchy(crvJnts, toReplace='ikcrv', replaceWith='ns_ikcrv')
    nsCurveJnts[0].setParent(ikSpineNode)
    
    handle, ee = pm.ikHandle(solver='ikSplineSolver', sj=nsCurveJnts[0], ee=nsCurveJnts[-1], curve=origCurve,
                simplifyCurve=False, parentCurve=False, createCurve=False)    
    handle.v.set(0)
    handle.rename(namer('ns_ik', x='ikh'))
    handle.setParent(ikSpineNode)
    ee.rename(namer('ns_ik', x='ee'))

              
    nsPosLocs = []    
    for i, jnt in enumerate(nsCurveJnts):
        loc = pm.spaceLocator(name=namer('ns_result_pos', x='loc', alphaSuf=i))

        pm.pointConstraint(jnt, loc)
        nsPosLocs.append(loc)
        jnt.v.set(0)
        loc.v.set(0)
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
        upLoc.v.set(0)
        upLoc.setParent(ikSpineNode)
        nsUpLocs.append(upLoc)
        posi.p.connect(upLoc.t)

    #aim each loc at the next - (reverse aim the final loc)
    nsFinalLocs = createAimedLocs(nsPosLocs, nsUpLocs, 'ns_result', namer)
    pm.parent(nsFinalLocs, ikSpineNode)


    #blend the non-stretch and stretch final locs to get the final position and orientation
    finalLocs = []
    #the scale constraints have some odd bugs when used with orient/aim constraints on joints..
    #this is a work-around for it
    interCrvJnts = utils.makeDuplicatesAndHierarchy(crvJnts, toReplace='ikcrv', replaceWith='intermediate_ikcrv')
    interCrvJnts[0].setParent(ikSpineNode)
    
    for i in range(len(nsFinalLocs)):        
        blends = {}
        blends['t'] = pm.createNode('blendColors', n=namer('final_pos', x='blc', alphaSuf=i))
        blends['r'] = pm.createNode('blendColors', n=namer('final_rot', x='blc', alphaSuf=i))
        blends['s'] = pm.createNode('blendColors', n=namer('final_scl', x='blc', alphaSuf=i))
        pm.select(cl=1)
        loc = pm.spaceLocator(name=namer('final', x='loc', alphaSuf=i))
        loc.v.set(0)
        loc.setParent(ikSpineNode)
        
        for attr, blend in blends.items():
            ikSpineNode.stretchAmt.connect(blend.blender)
            getattr(stretchFinalLocs[i], attr).connect(blend.c1)
            getattr(nsFinalLocs[i], attr).connect(blend.c2)
            blend.output.connect(getattr(loc, attr))

        stretchFinalLocs[i].v.set(0)
        nsFinalLocs[i].v.set(0)

        pm.pointConstraint(loc, interCrvJnts[i])
        pm.orientConstraint(loc, interCrvJnts[i])
        interCrvJnts[i].r.connect(crvJnts[i].r)
        loc.sy.connect(crvJnts[i].sy)
        interCrvJnts[i].v.set(0)
        
        #if i != (len(nsFinalLocs)-1):
            #loc.sy.connect(crvJnts[i].sy)
            #pm.scaleConstraint(loc, crvJnts[i])
    
    #constrain the original input joints to the crvJnts
    for i in range(len(crvJnts)):
        pm.pointConstraint(crvJnts[i], jnts[i], mo=True)
        pm.orientConstraint(crvJnts[i], jnts[i], mo=True)
        crvJnts[i].sy.connect(jnts[i].sy)
        
    return    
        

class Spine(core.Widget):
    def __init__(self, part='spine', **kwargs):
        super(Spine, self).__init__(part=part, **kwargs)
        self.options.setPresets('side', 'cn')
        self.options.addOpt('numBndJnts', 5, optType=int, min=3, max=24)
        self.options.addOpt('numIkCtls', 4, optType=int, min=2)
        
        for i in range(self.options.getValue('numBndJnts')):
            self.addParentPart('bnd_%s' % ascii_lowercase[i])
            self.addParentPart('fkCtl_%s' % ascii_lowercase[i])
            
        for i in range(self.options.getValue('numIkCtls')):
            self.addParentPart('ikCtl_%s' % ascii_lowercase[i])
        
    def childCompletedBuild(self, child, buildType):            
        super(Spine, self).childCompletedBuild(child, buildType)

    def _makeLayout(self, namer):
        
        baseLayoutCtl = CTL.makeControl(shape='circle',
                        color='yellow',
                        scale=[4,4,4],
                        name = namer('base_layout', x='ctl', r='lyt'))        
        self.registerControl('base', baseLayoutCtl)
        
        spineJnts = []
        spineCtls = {}
        jntSpacing = 2
        numJnts = self.options.getValue('numBndJnts')
        
        pm.select(cl=1)

        #create fk rig controls
        fkCtls = []
        for i in range(numJnts):
            tok = ascii_lowercase[i]
            fkTok = 'fk_%s' % tok
            
            jnt = pm.joint(p=[0, i*jntSpacing, 0], n = namer.name(r='bnd', d=tok))
            spineJnts.append(jnt)
            
            self.registerBindJoint(tok, jnt)
            fkCtl = CTL.makeControl(shape='square',
                                    scale=[1, 0.3, 0.5],
                                    name = namer.name(fkTok, x='ctl', r='rig'))            
            fkCtls.append(fkCtl)
            self.registerControl(fkTok, fkCtl, ctlType='rig')
            utils.snap(jnt, fkCtl, orient=False)
            zero = utils.insertNodeAbove(fkCtl)
            pm.parentConstraint(jnt, zero)
            pm.select(jnt)
        
        #create ik rig and layout controls
        maxHeight = (numJnts-1) * jntSpacing
        numIkCtls = self.options.getValue('numIkCtls')
        ikSpacing = float(maxHeight)/(numIkCtls-1)
        ikCtls = []
        for i in range(numIkCtls):
            tok = ascii_lowercase[i]
            ikTok = 'ik_%s' % tok
            ikRigCtl = CTL.makeControl(shape='cube',
                                       scale=[1.5, 0.2, 1.5],
                                       color='lite blue',
                                       name = namer.name(ikTok, x='ctl', r='rig'))            
            self.registerControl(ikTok, ikRigCtl, ctlType='rig')
            
            
            ikLayoutCtl = CTL.makeControl(shape='cube',
                                          scale=[2, 0.3, 2],
                                          color='green',
                                          name = namer.name(ikTok, x='ctl', r='lyt'))
            self.registerControl(ikTok, ikLayoutCtl, ctlType='layout')
            ikLayoutCtl.ty.set(ikSpacing * i)
            zero = utils.insertNodeAbove(ikLayoutCtl)
            utils.snap(ikLayoutCtl, ikRigCtl)
            ikRigCtl.setParent(ikLayoutCtl)
            ikCtls.append(ikLayoutCtl)
            
            zero.setParent(baseLayoutCtl)

            #lock some stuff
            pm.setAttr(ikLayoutCtl.tx.name(), l=1, k=0, cb=0)
            pm.setAttr(ikLayoutCtl.r.name(), l=1, k=0, cb=0)
            pm.setAttr(ikLayoutCtl.s.name(), l=1, k=0, cb=0)
        
        #get closest param to jnt
        #get poci node
        
        ikCrv = namer.rename(cvCurveFromNodes(ikCtls), 'ctlguide', x='crv', r='lyt')
        upCrv = namer.rename(pm.duplicate(ikCrv)[0], 'up_ctlguide', x='crv', r='lyt')
        upCrv.tx.set(1)
        ikCrv = getShape(ikCrv)
        upCrv = getShape(upCrv)
        
        ikCrv.template.set(1)
        upCrv.v.set(0)
        bindControlsToShape(ikCtls, ikCrv)
        bindControlsToShape(ikCtls, upCrv)
        #uniCrv = rebuildCurve(ikCrv, kep=1, kt=1, d=7, rt=0, s=1, ch=1, rpo=False)[0]

        locs = []
        upLocs = []
        for i, jnt in enumerate(spineJnts):
            param = closestParamOnCurve(ikCrv, jnt)
            
            fkCtls[i].addAttr('param',dv=param, at='double', k=1, max=ikCrv.maxValue.get())                        
            
            poci = pm.createNode('pointOnCurveInfo', n=namer('crvinfo', r='lyt', x='pci',alphaSuf = i))
            ikCrv.worldSpace[0].connect(poci.inputCurve)

            pociUp = pm.createNode('pointOnCurveInfo', n=namer('crvinfo_up', r='lyt', x='pci',alphaSuf = i))
            upCrv.worldSpace[0].connect(pociUp.inputCurve)
            
            
            loc = pm.spaceLocator(name=namer('crvinfo', r='lyt', x='loc', alphaSuf=i))
            loc.v.set(0)
            locs.append(loc)

            upLoc = pm.spaceLocator(name=namer('up_crvinfo', r='lyt', x='upLoc', alphaSuf=i))
            upLoc.v.set(0)
            upLocs.append(upLoc)
            
            fkCtls[i].param.connect(poci.pr)
            fkCtls[i].param.connect(pociUp.pr)
            poci.p.connect(loc.t)
            pociUp.p.connect(upLoc.t)

        # up = pm.createNode('transform', n=namer('spline_up', x='grp', r='lyt'))
        # up.tx.set(5)
        # up.setParent(baseLayoutCtl)
        aimLocs = createAimedLocs(locs, upLocs, 'layout', namer)
        
        for i, loc in enumerate(aimLocs):
            pm.parentConstraint(loc, spineJnts[i])
            loc.v.set(0)
        
    def _makeRig(self, namer, jnts, ctls):
        for k, v in jnts.items():
            self.setParentNode('bnd_%s' % k, v)
            self.setParentNode('fkCtl_%s' % k, ctls['fk_%s' % k])
        for i in range(self.options.getValue('numIkCtls')):
            l = ascii_lowercase[i]
            self.setParentNode('ikCtl_%s' % l, ctls['fk_%s' % l])
        return (namer, jnts, ctls)

core.WidgetRegistry().register(Spine, 'Spine', 'An ik/fk spine')


def _testSpine(path =  None):
    import maya.cmds as MC
    import pymel.core as pm
    if not path:
        path = '/Users/jspatrick/Documents/maya/projects/beingsTests/scenes/spineJnts.mb'
        
    MC.file(path, f=1, o=1)

    ctls = [pm.PyNode(n) for n in [u'ctl_a', u'ctl_b', u'ctl_c', u'ctl_d']]
    jnts = [pm.PyNode(n) for n in [u'bnd_a', u'bnd_b', u'bnd_c', u'bnd_d', u'bnd_e']]
    createIkSpineSystem(jnts, ctls)
    
if __name__ == '__main__':
    import maya.cmds as MC
    import maya.mel as MM
    import os, sys
    import pymel.core as pm
    import beings.core as C
    import beings.widgets.spine as S

    reload(C)    
    reload(S)
    
    pm.newFile(f=1)

    s = S.Spine()
    s.buildLayout()

    s.buildRig()
    
