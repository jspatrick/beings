import logging
from string import ascii_lowercase
import maya.cmds as MC
import maya.mel as MM
import maya.OpenMaya as OM
import pymel.core as pm

import beings.core as core
import beings.utils as utils
reload(utils)
import beings.control as CTL
from PyQt4 import QtCore

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
    dd = pm.createNode('distanceBetween', name=namer('%s_dst' % name, alphaSuf=num))
    startNode.t.connect(dd.p1)
    startNode.parentMatrix.connect(dd.im1)

    endNode.t.connect(dd.p2)
    endNode.parentMatrix.connect(dd.im2)

    return dd

def addJointAttrs(jnts, crv, node, inputScaleAttr, namer):
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
            pm.addAttr(node, ln=ORIG_ARC_LEN_ATTR % i, dv=result[-1], k=1)
        else:
            sc.inputCurve.disconnect()
            crv.worldSpace[0].connect(sc.inputCurve)
            sc.max.set(p)
            mdn = pm.createNode('multiplyDivide', n=namer('orig_arclen_scale_compensate_mdn', alphaSuf=i))
            mdn.input1X.set(ci.arcLength.get())
            inputScaleAttr.connect(mdn.input2X)
            result.append(ci.arcLength.get())
            pm.addAttr(node, ln=ORIG_ARC_LEN_ATTR % i, dv=result[-1], k=1)
            attr = pm.PyNode('%s.%s' % (node, ORIG_ARC_LEN_ATTR % i))
            mdn.outputX.connect(attr)



        prc = result[-1]/totalLen

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
        #shape.worldSpace[0].connect(endPoci.ic)
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


def createAimedLocs(posLocs, upLocs, name, namer, uniScaleAttr=None, upType='object'):
    result = []
    baseXform = None

    pm.select(cl=1)
    for i in range(len(posLocs)):
        posLoc = posLocs[i]
        upLoc = upLocs[i]

        #aim pos locs
        if i == len(posLocs) -1:
            aimLoc = posLocs[i-1]
            aimVec = [0,-1,0]
        else:
            aimLoc = posLocs[i+1]
            aimVec = [0,1,0]

        dist=getDistanceNode(posLoc, aimLoc, name, namer, i)
        mdn = pm.createNode('multiplyDivide', n=namer('%s_scl_mdn' % name, alphaSuf=i))
        dist.distance.connect(mdn.input1X)
        mdn.input2X.set(dist.distance.get())
        mdn.operation.set(2)
        mdn.outputX.connect(posLoc.sy)

        if uniScaleAttr:
            uniScaleAttr.connect(posLoc.sx)
            uniScaleAttr.connect(posLoc.sz)

        upVec = [1,0,0]
        aimCst = pm.aimConstraint(aimLoc, posLoc, aimVector=aimVec, upVector=upVec,
                                  worldUpType=upType, worldUpObject=upLoc)
        result.append(posLoc)

    return result





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

        self.options.subscribe('optSet', self.__optionSet)

    def childCompletedBuild(self, child, buildType):
        super(Spine, self).childCompletedBuild(child, buildType)

    def __optionSet(self, event):
        if event.optName != 'numBndJnts':
            return

        for part in self.plugs():
            self.rmPlug(part)

        for i in range(self.options.getValue('numBndJnts')):
            self.addParentPart('bnd_%s' % ascii_lowercase[i])
            self.addParentPart('fkCtl_%s' % ascii_lowercase[i])


    def _makeLayout(self, namer):

        baseLayoutCtl = CTL.makeControl(shape='circle',
                        color='yellow',
                        scale=[4,4,4],
                        name = namer('base_layout_ctl', r='ctl'))
        self.registerControl(baseLayoutCtl)

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

            self.registerBindJoint(jnt)
            fkCtl = CTL.makeControl(namer.name('%s_ctl' % fkTok, r='rig'),
                                    shape='square',
                                    scale=[1, 0.3, 0.5])
            fkCtls.append(pm.PyNode(fkCtl))
            self.registerControl(fkCtl, ctlType='rig')
            utils.snap(jnt, fkCtl, orient=False)
            zero = pm.PyNode(utils.insertNodeAbove(fkCtl))
            zero.setParent(baseLayoutCtl)
            pm.parentConstraint(jnt, zero)
            pm.select(jnt)
        spineJnts[0].setParent(baseLayoutCtl)

        #create ik rig and layout controls
        maxHeight = (numJnts-1) * jntSpacing
        numIkCtls = self.options.getValue('numIkCtls')
        ikSpacing = float(maxHeight)/(numIkCtls-1)
        ikCtls = []
        ikRigCtls = []
        for i in range(numIkCtls):
            tok = ascii_lowercase[i]
            ikTok = 'ik_%s' % tok
            ikRigCtl = CTL.makeControl(namer.name('%s_ctl' % ikTok, r='rig'),
                                       shape='cube',
                                       scale=[1.5, 0.2, 1.5],
                                       color='lite blue')            
            self.registerControl(ikRigCtl, ctlType='rig')
            ikRigCtl = pm.PyNode(ikRigCtl)

            ikLayoutCtl = CTL.makeControl(namer.name('%s_ctl' % ikTok, r='lyt'),
                                          shape='cube',
                                          scale=[2, 0.3, 2],
                                          color='green')
            ikLayoutCtl = pm.PyNode(ikLayoutCtl)
            self.registerControl(ikLayoutCtl, ctlType='layout')
            ikLayoutCtl.ty.set(ikSpacing * i)
            zero = pm.PyNode(utils.insertNodeAbove(ikLayoutCtl))
            utils.snap(ikLayoutCtl, ikRigCtl)
            ikRigCtl.setParent(ikLayoutCtl)

            ikCtls.append(ikLayoutCtl)
            ikRigCtls.append(ikRigCtl)

            zero.setParent(baseLayoutCtl)

            #lock some stuff
            pm.setAttr(ikLayoutCtl.tx.name(), l=1, k=0, cb=0)
            pm.setAttr(ikLayoutCtl.r.name(), l=1, k=0, cb=0)
            pm.setAttr(ikLayoutCtl.s.name(), l=1, k=0, cb=0)

        #get closest param to jnt
        #get poci node

        ikCrv = namer.rename(cvCurveFromNodes(ikCtls), 'ctlguide_crv', r='lyt')
        upCrv = namer.rename(pm.duplicate(ikCrv)[0], 'up_ctlguide_crv', r='lyt')
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
        for i in [0, -1]:
            ctl = ikRigCtls[i]
            jnt = spineJnts[i]
            zero = utils.insertNodeAbove(ctl)
            pm.orientConstraint(jnt, zero)

        for i, jnt in enumerate(spineJnts):


            param = closestParamOnCurve(ikCrv, jnt)

            fkCtls[i].addAttr('param',dv=param, at='double', k=1, max=ikCrv.maxValue.get())

            poci = pm.createNode('pointOnCurveInfo', n=namer('crvinfo_pci', r='lyt', alphaSuf = i))
            ikCrv.worldSpace[0].connect(poci.inputCurve)

            pociUp = pm.createNode('pointOnCurveInfo', n=namer('crvinfo_up_pci', r='lyt', alphaSuf = i))
            upCrv.worldSpace[0].connect(pociUp.inputCurve)

            loc = pm.spaceLocator(name=namer('crvinfo_loc', r='lyt', alphaSuf=i))
            loc.v.set(0)
            locs.append(loc)

            upLoc = pm.spaceLocator(name=namer('up_crvinfo_uploc', r='lyt', alphaSuf=i))
            upLoc.v.set(0)
            upLocs.append(upLoc)

            fkCtls[i].param.connect(poci.pr)
            fkCtls[i].param.connect(pociUp.pr)
            poci.p.connect(loc.t)
            pociUp.p.connect(upLoc.t)

        aimLocs = createAimedLocs(locs, upLocs, 'layout', namer)

        for i, loc in enumerate(aimLocs):
            pm.parentConstraint(loc, spineJnts[i])
            loc.v.set(0)

    def _makeRig(self, namer, jnts, ctls):

        jntList = []
        ikCtlList = []
        fkCtlList = []
        toks = []
        numJnts = self.options.getValue('numBndJnts')
        numIkCtls = self.options.getValue('numIkCtls')


        for i in range(numJnts):
            l = ascii_lowercase[i]
            toks.append(l)

            fkCtl = ctls['fk_%s' % l]
            self.setParentNode('bnd_%s' % l, jnts[l])
            self.setParentNode('fkCtl_%s' % l, fkCtl)
            jntList.append(jnts[l])
            fkCtlList.append(fkCtl)

        for i in range(numIkCtls):
            l = ascii_lowercase[i]
            ikCtl = ctls['ik_%s' % l]
            utils.insertNodeAbove(ikCtl)
            self.setParentNode('ikCtl_%s' % l, ikCtl)
            ikCtlList.append(ikCtl)

        #parent the ik controls to each other -
        numOthers = numIkCtls-2
        for i in range(int(numOthers)/2):
            ikCtlList[i+1].getParent().setParent(ikCtlList[i])
            ikCtlList[-2-i].getParent().setParent(ikCtlList[-1-i])

        if numOthers % 2 != 0:
            _logger.warning("non-even num ik ctls - implement a solution for mid ctl")

        tipIkCtl = ikCtlList[-1]
        tipIkCtl.addAttr('fkIkBlend', dv=1, max=1, min=0, k=1, at='double')
        tipIkCtl.addAttr('ikStretchAmt', dv=1, max=1, min=0, k=1, at='double')
        tipIkCtl.addAttr('uniformIkStretch', dv=1, max=1, min=0, k=1, at='double')


        ikJnts = utils.duplicateHierarchy(jntList, toReplace='bnd', replaceWith='ik')
        self.setNodeCateogry(ikJnts[0], 'parent')

        ikSpineNode = self.createIkSpineSystem(ikJnts, ikCtlList, namer=namer)
        self.setNodeCateogry(ikSpineNode, 'dnt')

        ikSpineNode.v.set(0)
        tipIkCtl.ikStretchAmt.connect(ikSpineNode.stretchAmt)
        tipIkCtl.uniformIkStretch.connect(ikSpineNode.uniformStretch)

        #move shapes in controls to joints
        fkCtls = CTL.setupFkCtls(jntList, fkCtlList, toks, namer)


        utils.blendJointChains(fkCtls, ikJnts, jntList, tipIkCtl.fkIkBlend, namer)


        #set visibility
        ikJnts[0].v.set(0)


        return (namer, jnts, ctls)

    def createIkSpineSystem(self, jnts, ctls, namer=None, part=None):
        """
        Create an ik spine setup.
        @return ikSpineNode

        Notes
        -----

        The returned node should be put in dnt.  It has attrs that control the solve:

        stretchAmt
        uniformStretch
        """


        if namer is None:
            if part is None:
                part = 'spine'
            namer = utils.Namer(character='char', part=part)

        ikSpineNode = pm.createNode('transform', n=namer('ikspine'))
        self.setNodeCateogry(ikSpineNode, 'parent')

        ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
        ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)

        ikSpineNode.addAttr('inputScale', k=1, dv=1)
        core.Root.tagInputScaleAttr(ikSpineNode, 'inputScale')

        origCurve = cvCurveFromNodes(ctls)
        pm.rename(origCurve, namer('crv'))
        pm.parent(origCurve, ikSpineNode)

        origCurve = getShape(origCurve)
        bindControlsToShape(ctls, str(origCurve))

        #build a curve with a single span that has uniform parameterization
        uniCurve = pm.rebuildCurve(origCurve, kep=1, kt=1, d=7, rt=0, s=1, ch=1, rpo=False)[0]
        uniCurve.rename(namer('ns_crv'))
        uniCurve.setParent(ikSpineNode)
        uniCurve = uniCurve.listRelatives(type='nurbsCurve')[0]
        uniCurve = getShape(uniCurve)

        surf = surfaceFromNodes(ctls)
        pm.rename(surf, namer('surf_nrb'))
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
            jnt.rename(namer(d='ikcrv_jnt', alphaSuf=i))

        curveMaxParam = origCurve.maxValue.get()

        addJointAttrs(crvJnts, origCurve, ikSpineNode, ikSpineNode.inputScale, namer)
        stretchPosLocs = []
        stretchUpLocs = []
        for i, jnt in enumerate(crvJnts):
            # for each joint, get a param value along the original curve.

            #blend between two parameter values on the original curve - uniform and non uniform stretch
            stretchParamBlend = pm.createNode('blendColors', name=namer('stretch_param_blc', alphaSuf=i))
            ikSpineNode.uniformStretch.connect(stretchParamBlend.b)
            poci = pm.createNode('pointOnCurveInfo', name=namer('stretch_result_pos_pci', alphaSuf=i))
            origCurve.worldSpace[0].connect(poci.inputCurve)
            stretchParamBlend.opr.connect(poci.pr)

            #create a locator on the curve at the blended parameter
            resultPosLoc = pm.spaceLocator(name=namer('stretch_result_pos_loc', alphaSuf=i))
            resultPosLoc.setParent(ikSpineNode)
            resultPosLoc.v.set(0)

            poci.p.connect(resultPosLoc.t)
            stretchPosLocs.append(resultPosLoc)

            #create a loctor on the nurbs surf at the blended parameter in u an .9 in v
            resultUpLoc = pm.spaceLocator(name=namer('stretch_result_up_loc',  alphaSuf=i))
            resultUpLoc.setParent(ikSpineNode)
            resultUpLoc.v.set(0)
            posi = pm.createNode('pointOnSurfaceInfo', name=namer('stretch_result_up_loc', alphaSuf=i))
            surf.worldSpace[0].connect(posi.inputSurface)
            stretchParamBlend.opr.connect(posi.u)
            posi.v.set(0.9)
            posi.p.connect(resultUpLoc.t)
            stretchUpLocs.append(resultUpLoc)

            #get the param for the non-uniform stretch -
            p = closestParamOnCurve(origCurve, jnt)
            pci = pm.createNode('pointOnCurveInfo', name=namer('stretch_pci',  alphaSuf=i))
            origCurve.worldSpace[0].connect(pci.inputCurve)
            pci.pr.set(p)
            pci.pr.connect(stretchParamBlend.c2r)

            #get the point in space along the uniform curve
            p = closestParamOnCurve(uniCurve, jnt)
            pci = pm.createNode('pointOnCurveInfo', name=namer('unistretch_pci', alphaSuf=i))
            uniCurve.worldSpace[0].connect(pci.inputCurve)
            pci.pr.set(p)

            #get the param on the non-uniform curve to that point
            npc = pm.createNode('nearestPointOnCurve', name=namer('unistretch_point_to_orig', alphaSuf=i))
            origCurve.worldSpace[0].connect(npc.inputCurve)
            pci.p.connect(npc.ip)

            npc.pr.connect(stretchParamBlend.c1r)

        stretchFinalLocs = createAimedLocs(stretchPosLocs, stretchUpLocs, 'stretch_result', namer,
                                           uniScaleAttr=ikSpineNode.inputScale)



        #use splineIK for non-stretching joints
        nsCurveJnts = utils.duplicateHierarchy(crvJnts, toReplace='ikcrv', replaceWith='ns_ikcrv')
        self.setNodeCateogry(nsCurveJnts[0], 'parent')

        handle, ee = pm.ikHandle(solver='ikSplineSolver', sj=nsCurveJnts[0], ee=nsCurveJnts[-1], curve=origCurve,
                    simplifyCurve=False, parentCurve=False, createCurve=False)
        handle.v.set(0)
        handle.rename(namer('ns_ik_ikh'))
        ee.rename(namer('ns_ik_ee'))
        self.setNodeCateogry(handle, 'parent')


        nsPosLocs = []
        for i, jnt in enumerate(nsCurveJnts):
            loc = pm.spaceLocator(name=namer('ns_result_pos_loc', alphaSuf=i))

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
            cps = pm.createNode('closestPointOnSurface', n=namer('ns_up_pos_cps', alphaSuf=i))
            surf.worldSpace[0].connect(cps.inputSurface)
            loc.t.connect(cps.ip)

            cnd = pm.createNode('condition', n=namer('ns_up_arclen_cnd',  alphaSuf=i))
            origArcLen = getattr(ikSpineNode, 'origArcLen%i' % i)
            origArcLen.connect(cnd.secondTerm)
            curveAL.al.connect(cnd.firstTerm)
            cnd.operation.set(5)
            cnd.colorIfTrueR.set(curveMaxParam)
            cps.u.connect(cnd.colorIfFalseR)

            posi = pm.createNode('pointOnSurfaceInfo', n=namer('ns_up_pos_psi', alphaSuf=i))
            surf.worldSpace[0].connect(posi.inputSurface)
            cnd.outColorR.connect(posi.u)
            posi.v.set(.9)

            upLoc = pm.spaceLocator(name=namer('ns_result_up_loc', alphaSuf=i))
            upLoc.v.set(0)
            upLoc.setParent(ikSpineNode)
            nsUpLocs.append(upLoc)
            posi.p.connect(upLoc.t)

        #aim each loc at the next - (reverse aim the final loc)
        nsFinalLocs = createAimedLocs(nsPosLocs, nsUpLocs, 'ns_result', namer, uniScaleAttr=ikSpineNode.inputScale)



        rev = pm.createNode('reverse', name=namer('stretch_amt_rev'))
        ikSpineNode.stretchAmt.connect(rev.inputX)

        createdNodes = set()

        for i in range(len(nsFinalLocs)):
            csts = {}
            csts['pc'] = pm.pointConstraint(stretchFinalLocs[i], nsFinalLocs[i], crvJnts[i])
            csts['oc'] = pm.orientConstraint(stretchFinalLocs[i], nsFinalLocs[i], crvJnts[i])
            csts['sc'] = pm.scaleConstraint(stretchFinalLocs[i], nsFinalLocs[i], crvJnts[i])
            utils.fixJointConstraints(crvJnts[i])
            for cstType, cst in csts.items():
                stretchWtAttr  = pm.PyNode('%s.%sW0' % (cst.name(), stretchFinalLocs[i].name()))
                nsWtAttr  = pm.PyNode('%s.%sW1' % (cst.name(), nsFinalLocs[i].name()))

                ikSpineNode.stretchAmt.connect(stretchWtAttr)
                rev.outputX.connect(nsWtAttr)


        for i in range(len(crvJnts)):

            #add an attr to the end control to orient to it
            if i == (len(crvJnts) -1):
                oc = pm.orientConstraint(crvJnts[i], ctls[-1], jnts[i], mo=True)
                jntWtAttr = '%s.%sW0' % (oc.nodeName(), crvJnts[i].nodeName())
                ctlWtAttr = '%s.%sW1' % (oc.nodeName(), ctls[-1].nodeName())
                ctls[-1].addAttr('matchOrientation', dv=1, max=1, min=0, k=1)
                rev = pm.createNode('reverse', name=namer('tip_orient_match_rev'))
                ctls[-1].matchOrientation.connect(rev.inputX)
                ctls[-1].matchOrientation.connect(ctlWtAttr)
                rev.outputX.connect(jntWtAttr)
            else:
                pm.orientConstraint(crvJnts[i], jnts[i], mo=True)

            pm.pointConstraint(crvJnts[i], jnts[i], mo=True)
            pm.scaleConstraint(crvJnts[i], jnts[i], mo=False)

            utils.fixJointConstraints(jnts[i])

        return ikSpineNode


core.WidgetRegistry().register(Spine, 'Spine', 'An ik/fk spine')


def _testSpine(path =  None):
    import maya.cmds as MC
    import pymel.core as pm
    if not path:
        path = '/Users/jspatrick/Documents/maya/projects/beingsTests/scenes/spineJnts.mb'

    MC.file(path, f=1, o=1)

    ctls = [pm.PyNode(n) for n in [u'defaultchar_rig_cn_spine_ik_a_ctl', u'defaultchar_rig_cn_spine_ik_b_ctl', u'defaultchar_rig_cn_spine_ik_c_ctl', u'defaultchar_rig_cn_spine_ik_d_ctl']]
    jnts = [pm.PyNode(n) for n in [u'defaultchar_bnd_cn_spine_a', u'defaultchar_bnd_cn_spine_b', u'defaultchar_bnd_cn_spine_c', u'defaultchar_bnd_cn_spine_d', u'defaultchar_bnd_cn_spine_e']]
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
