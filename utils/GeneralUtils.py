'''
This module contains general utilities.  If a function is used in other 
utilities, it should be defined here.
'''
import logging, inspect, sys, re, string
import pymel.core as pm
import maya.cmds as MC
from beings.utils.Exceptions import * #@UnusedWildImport
_logger = logging.getLogger(__name__)

g_xformShortAttrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']
g_xformLongAttrs = ['translateX', 'translateY', 'translateZ',
                    'rotateX', 'rotateY', 'rotateZ',
                    'scaleX', 'scaleY', 'scaleZ']

def getConstraintTargets(cst):
    """
    Return a dict of {index: tagetNode}
    """
    
    cst= str(cst)
    indices = MC.getAttr('%s.target' % cst, mi=1)
    
    targets = {}
    
    for index in indices:
        attrs = MC.attributeQuery('target', listChildren=1, n=cst)
        nonMatrixAttrs = [x for x in attrs if 'Matrix' not in x]
        cnct = pm.connectionInfo("%s.target[%i].%s" % (cst, index, nonMatrixAttrs[0]), sfd=1)
        if cnct:
            node = cnct.split('.')[0]
            targets[index] = pm.PyNode(node)
            
    return targets

def getConstraintSlave(cst):
    
    cst= str(cst)    
    for cnct in MC.listConnections(cst, s=0, d=1, p=1):        
        
        parts = cnct.split('.')
        node = parts[0]
        attr = parts[-1]
        if attr in g_xformLongAttrs:
            return pm.PyNode(node)

def breakCncts(attr, s=1, d=1):
    if s:
        n=MC.connectionInfo(attr, sfd=1)
        if n:
            MC.disconnectAttr(n, attr)
    if d:
        for n in MC.connectionInfo(attr, dfs=1):
            MC.disconnectAttr(attr, n)

        
def getScaleCompJnt(jnt):
    jnt = str(jnt)
    
    par = MC.listRelatives(jnt, type='joint', parent=1)
    if not par:
        return None
    
    if MC.attributeQuery('scaleCompJnt', n=jnt, ex=1):
        cnct = MC.listConnections('%s.scaleCompJnt' % jnt, s=1, d=0)
        if cnct:
            return pm.PyNode(cnct[0])
    else:
        MC.addAttr(jnt, ln='scaleCompJnt', at='message')
        
    par = par[0]
    
    scJnt = MC.duplicate(par, n='%s_scalecomp' % jnt)[0]
    MC.delete(MC.listRelatives(scJnt, pa=1) or [])
    
    MC.setAttr("%s.v" % scJnt, 0)
    
    MC.parent(scJnt, par)

    breakCncts('%s.inverseScale' % scJnt)
    MC.connectAttr('%s.scale' % par, '%s.inverseScale' % scJnt, f=1)    
    
    MC.connectAttr('%s.message' % scJnt, '%s.scaleCompJnt' % jnt)

    return pm.PyNode(scJnt)

def fixJointConstraints(slaveNode):
    csts = pm.listConnections(slaveNode, s=1, d=0, type='constraint')
    if not csts:
        return
    for cst in csts:
        if isinstance(cst, pm.nt.PointConstraint):
            continue
        tgts = getConstraintTargets(cst)
        for index, tgt in tgts.items():
            
            sc = getScaleCompJnt(tgt)
            if not sc:
                continue

            cst.target[index].targetParentMatrix.disconnect()            
            sc.worldMatrix[0].connect(cst.target[index].targetParentMatrix, f=1)
            
        slave = getConstraintSlave(cst)
        sc = getScaleCompJnt(slave)
        if not sc:
            continue
        cst.constraintParentInverseMatrix.disconnect()
        sc.worldInverseMatrix[0].connect(cst.constraintParentInverseMatrix, f=1)

        
class SilencePymelLogger(object):
    def __init__(self):
        self.level = 10
        self.pmLogger = logging.getLogger('pymel.core.nodetypes')
    def __enter__(self):
        self.pmLogger.propagate = 0
        self.level = self.pmLogger.level
        self.pmLogger.setLevel(50)
        return self

    def __exit__(self, exctype, excval, exctb):
        self.pmLogger.propagate = 1
        self.pmLogger.setLevel(self.level)

        

def setupFkCtls(bndJnts, rigCtls, fkToks, namer):
    """Set up fk controls from bndJnts.

    This will delete the original controls that were passed
    in and rebuild the control shapes on a duplicate of the bind joints
    @return: dict of {tok:ctl}
    """
    if len(bndJnts) != len(rigCtls) or len(bndJnts) != len(fkToks):
        _logger.warning("bind joint length must match rig ctls")
    
    fkCtls = duplicateHierarchy(bndJnts, toReplace='_bnd_', replaceWith='_fk_')
    for i in range(len(fkCtls)):            
        newCtl = fkCtls[i]
        oldCtl = rigCtls[i]
        info = control.getInfo(oldCtl)
        control.setInfo(newCtl, control.getInfo(oldCtl))
        utils.parentShape(newCtl, oldCtl)
        newCtl.rename(namer(fkToks[i], r='fk'))
        
    pm.delete(rigCtls)
    
    return fkCtls


        
def createStretch(distNode1, distNode2, stretchJnt, namer, stretchAttr='sy'):
    """
    Create a stretch
    """
    if not namer.getToken('part'):
        _logger.warning('You should really give the namer a part...')
    dist = pm.createNode('distanceBetween', n=namer.name(d='stretch', x='dst'))
    pm.select(dist)
    distNode1.worldMatrix.connect(dist.inMatrix1)
    distNode2.worldMatrix.connect(dist.inMatrix2)
    staticDist = dist.distance.get()
    mdn  = pm.createNode('multiplyDivide', n=namer.name(d='stretch', x='mdn'))
    dist.distance.connect(mdn.input1X)
    mdn.input2X.set(staticDist)
    mdn.operation.set(2) #divide
    mdn.outputX.connect(getattr(stretchJnt, stretchAttr))

def safeParent(self, **nodes):pass
    
        
def blendJointChains(fkChain, ikChain, bindChain, fkIkAttr, namer):
    """
    Blend an ik and fk joint chain into a bind joint chain.
    @params fkChain, ikChain, bindChain: list of jnts
    @param fkIkAttr: an attr that is in fk when set to 0 and ik when at 1
    @param directChannelBlend=True:  use blend color nodes instead of constraints
    
    @return: the reverse node created
    """
    result = []
    reverse = pm.createNode('reverse', n=namer.name(d='fkik', x='rev'))
    result.append(reverse)
    fkIkAttr.connect(reverse.inputX)
    
    fkJntList = []
    ikJntList = []
    bindJntList = []
    
    if isinstance(bindChain, dict):
        for tok in bindChain.keys():
            if (tok not in fkChain) or (tok not in ikChain):
                _logger.debug("Skipping blending %s" % tok)
                continue
            bindJntList = bindChain[tok]
            fkJntList = fkChain[tok]
            ikJntList = ikChain[tok]
    else:
        fkJntList = fkChain
        ikJntList = ikChain
        bindJntList = bindChain
        

    for i in range(len(bindJntList)):

        for cstType in ['point', 'orient', 'scale']:
            
            fnc = getattr(pm, '%sConstraint' % cstType)
            cst = fnc(fkJntList[i], ikJntList[i], bindJntList[i])                
            fkAttr = getattr(cst, '%sW0' % fkJntList[i].nodeName())
            ikAttr = getattr(cst, '%sW1' % ikJntList[i].nodeName())
            reverse.outputX.connect(fkAttr)
            fkIkAttr.connect(ikAttr)
            
            fixJointConstraints(bindJntList[i])

    return result

def freeze(*args):
    """
    freeze every provided node.  Don't freeze joint orients
    """
    freezeNodes = []
    for arg in args:
        if type(arg) == type([]) or type(arg) == type(()):
            freezeNodes.extend([pm.PyNode(node) for node in arg])
        else:
            freezeNodes.append(pm.PyNode(arg))

    for node in freezeNodes:
        pm.makeIdentity(node, apply=True, t=1, r=1, s=1)

def mirrorX(item):
    """Mirror an object's position and rotation across the X axis"""
    oldPos = pm.xform(item, q=1, t=1, ws=1)
    oldRot = pm.xform(item, q=1, rotation=1)
    newPos = pm.xform(item, t=[oldPos[0] * -1, oldPos[1], oldPos[2]])
    newRot = pm.xform(item, rotation=[oldRot[0], oldRot[1] * -1, oldRot[2]])

def makeUnkeyableAttr(obj, attr):
    """Create an unkeyable attribute on a node.  This is useful for separating
    attributes"""
    obj = pm.PyNode(obj)
    attr = str(attr)
    obj.addAttr(attr, keyable=False, at="bool")
    newAttr = pm.PyNode("%s.%s" % (obj.name(), attr))
    newAttr.showInChannelBox(True)
    return newAttr

def insertNodeAbove(node, nodeType=None, name=None, suffix='_zero'):
    '''Insert a node above node
    @param nodeType=None: make this type of node.  Defaults to the type that node is
    @param name=None: name of the new node.  Defaults to node name + suffix
    @param suffix='_zero': the name suffix
    '''
    if name is None:
        name = '%s%s' % (node.name(), suffix)
        
    if pm.objExists(name):
        _logger.warning("Node called '%s' already exists' % name")
    if isinstance(node, pm.nt.Joint):
        nodeType='joint'
    else:
        nodeType='transform'
    #if this is a joint, add it's orients to the rotations of the zero node.
    
    new = pm.createNode(nodeType, name=name)
    new.setParent(node.getParent())
    snap(node, new, ignoreOrient=True)
    node.setParent(new)
    return new

#===============================================================================
# shape utils
#===============================================================================

def filterShapes(*nodes):
    """
    Given a list of transform or shape nodes, return a sorted list of shapes
    @return [vertObjs, cvObjs, surfObjs]
    """

    vertObjs = []
    cvObjs = []
    surfObjs = []
    for shape in nodes:
        shape = pm.PyNode(shape)
        if isinstance(shape, pm.nodetypes.NurbsCurve):
            cvObjs.append(shape)
        elif isinstance(shape, pm.nodetypes.NurbsSurface):
            surfObjs.append(shape)
        elif isinstance(shape, pm.nodetypes.Mesh):
            vertObjs.append(shape)
        elif isinstance(shape, pm.nodetypes.Transform):
            shapes = shape.listRelatives(shapes=True)
            for shape in shapes:
                if isinstance(shape, pm.nodetypes.NurbsCurve):
                    cvObjs.append(shape)
                if isinstance(shape, pm.nodetypes.NurbsSurface):
                    surfObjs.append(shape)
                elif isinstance(shape, pm.nodetypes.Mesh):
                    vertObjs.append(shape)

    return [vertObjs, cvObjs, surfObjs]


def moveShapePos(node, vector=[0, 0, 0]):
    """
    Move a shape.  Node can be a shape node or a transform above shape nodes
    """

    vertObjs, cvObjs, surfObjs = filterShapes(node)

    for obj in vertObjs:
        hi = len(obj.getPoints()) - 1
        pm.xform(obj.name() + ".vtx[0:%s]" % str(hi), t=vector, r=True)

    for obj in surfObjs:
        hi = len(obj.getCVs()) - 1
        pm.xform(obj.name() + ".controlPoints[0:%s]" % str(hi), t=vector, r=True)

    for obj in cvObjs:
        hi = obj.numCVs() - 1
        pm.xform(obj.name() + ".cv[0:%s]" % str(hi), t=vector, r=True)


def getShapePos(*nodes, **kwargs):
    """
    @return: dictionary of {shapePyNode: [pointPositionList],...}
    """
    ws = kwargs.get('ws', False)
    if ws:
        space = 'world'
    else:
        space = 'preTransform'

    vertObjs, crvObjs, surfObjs = filterShapes(*nodes)
    result = {}

    for obj in vertObjs:        
        assert isinstance(obj, pm.nodetypes.Mesh)
        result[obj] = obj.getPoints(space=space)

    for obj in crvObjs:
        assert (isinstance(obj, pm.nodetypes.NurbsCurve))
        result[obj] = []
        for i in range(obj.numCVs()):
            result[obj].append(pm.xform(obj.cv[i], q=True, ws=ws, t=True))
        #this might have a bug?
        #result[obj] = obj.getCVs(space='world')
        #result[obj].append(.getPosition(space='world'))
    for obj in surfObjs:
        assert(isinstance(obj, pm.nodetypes.NurbsSurface))
        result[obj] = []
        for u in range(obj.numCVsInU()):
            for v in range(obj.numCVsInV()):
                result[obj].append(pm.xform(obj.cv[u][v], q=True, ws=ws, t=True))
    return result

def getShapePosList(*nodes, **kwargs):
    d = getShapePos(*nodes, **kwargs)
    return d.values()

def setShapePos(shapeDict, ws=False):
    if ws:
        space = 'world'
    else:
        space = 'preTransform'

    for node, pointList in shapeDict.items():
        if (isinstance(node, pm.nodetypes.NurbsCurve)):
            #this also seems to have a bug
            for i, point in enumerate(pointList):
                pm.xform(node.cv[i], ws=ws, t=point)

        elif isinstance(node, pm.nodetypes.NurbsSurface):
            i = 0
            for u in range(node.numCVsInU()):
                for v in range(node.numCVsInV()):
                    pm.xform(node.cv[u][v], ws=ws, t=pointList[i])
                    i += 1

        elif isinstance(node, pm.nodetypes.Mesh):
            node.setPoints(pointList, space=space)

def setShapePosList(shapePosList, nodeList):
    if len(shapePosList) != len(nodeList):
        raise Exception("pos list doesn't match node list")
    d = {}
    for i, pos in enumerate(shapePosList):
        d[nodeList[i]] = pos

    return setShapePos(d)

def separateShapes(node):
    """
    for each shape node under a transform, duplicate the transform
    and delete other shapes
    """     
    shapes = node.listRelatives(type='geometryShape')
    result = []
    for i in range(len(shapes)):
        dup = pm.duplicate(node)[0]
        subShapes = dup.listRelatives(type='geometryShape')
        for j in range(len(shapes)):
            if j != i:
                pm.delete(subShapes[j])
        result.append(dup)
    return result

def strokePath(node, radius=.1):
    """
    Create a nurbs surface from a curve control
    """
    curveNodes = separateShapes(node)
    for curveNode in curveNodes:
        shape = curveNode.listRelatives(type='nurbsCurve')[0]
        t = pm.pointOnCurve(shape, p=0, nt=1)
        pos = pm.pointOnCurve(shape, p=0)        
        cir = pm.circle(r=radius)[0]
        pm.xform(cir, t=pos, ws=1)
        
        #align the circule along the curve
        l = pm.spaceLocator()
        pm.xform(l, t=[pos[0]+t[0], pos[1]+t[1], pos[2]+t[2]], ws=1)
        pm.delete(pm.aimConstraint(l, cir, aimVector=[0,0,1]))
        pm.delete(l)

        newxf = pm.extrude(cir, curveNode, rn=False, po=0, et=2, ucp=1,
                            fpt=1, upn=1, scale=1, rsp=1, ch=1)[0]
        pm.delete(cir)
        pm.delete(curveNode.listRelatives(type='nurbsCurve'))
        parentShape(curveNode, newxf)
    if len(curveNodes) > 1:
        for i in range(1, len(curveNodes)):
            parentShape(curveNodes[0], curveNodes[i])
    return curveNodes[0]
     
def parentShape(parent, child, deleteChildXform=True):
    """
    Parent the shape nodes of the children to the transform of the parent.  
    Return all shapes of the new parent
    """
    #snap a temp
    shapes = [shape for shape in child.listRelatives(children=True) if isinstance(shape, pm.nodetypes.GeometryShape)]
    tmp = pm.createNode('transform', n='TMP')
    snap(child, tmp, scale=True)
    for shape in shapes:
        pm.parent(shape, tmp, r=True, s=True)
    
    pm.parent(tmp, parent)
    pm.makeIdentity(tmp, apply=True, t=1, r=1, s=1, n=0)
    pm.parent(tmp, w=1)
    
    for shape in shapes:
        pm.parent(shape, parent, r=True, s=True)
    pm.delete(tmp)
    if deleteChildXform:
        pm.delete(child)
    return parent

def parentShapes(parent, children, deleteChildXforms=True):
    """Parent the shape nodes of the children to the transform of the parent.  Return the parent"""
    for child in children:
        if child.exists():
            parentShape(parent, child, deleteChildXform=deleteChildXforms)
    return parent

def mirrorCrv(shapeXf, shapeMirrorXf):
    """
    Get the position of each CV for each shape node in shapeXf and place in a position mirrored across
	the X-axis.
    """
    oShapes = [shape for shape in shapeXf.listRelatives(children=True) if isinstance(shape, pm.nodetypes.NurbsCurve)]
    mShapes = [shape for shape in shapeMirrorXf.listRelatives(children=True) if isinstance(shape, pm.nodetypes.NurbsCurve)]
    #The shapes should have been duplicated, so the names of the shapes under the xForms should be similar
    oShapes.sort()
    mShapes.sort()
    if len(oShapes) != len(mShapes):
        raise Exception("Different number of shape nodes under the provided transforms")
    #check for matching CV counts before starting to mirror
    for i in range(len(oShapes)):
        if oShapes[i].numCVs() != mShapes[i].numCVs():
            raise Exception("CV counts must mach for each shape node under the transforms")
    for i in range(len(oShapes)):
        nCVs = oShapes[i].numCVs()
        p = []
        for j in range(0, nCVs):
            p = pm.xform(oShapes[i].cv[j], q=1, a=1, translation=1, ws=1)
            pm.xform(mShapes[i].cv[j], a=1, translation=((0 - p[0]), p[1], p[2]), ws=1)

def scaleCrv(ctl, amt):
    """Scale a control by resizing it's CVs.  This does not affect the
	transform"""
    shapes = [shape for shape in ctl.listRelatives(children=True) if isinstance(shape, pm.nodetypes.NurbsCurve)]
    for shape in shapes:
        pm.xform(shape.cv, scale=[amt[0], amt[1], amt[2]])

def centerCrv(ctl, obj1, obj2, amt=.5):
    """Move a control's shape between two other objects (typically joints).
    Control is moved relative to it's starting point, and is moved along
    the vector from object 1 to object 2."""
    ctl = pm.PyNode(ctl)
    obj1 = pm.PyNode(obj1)
    obj2 = pm.PyNode(obj2)
    numCvs = ctl.numCVs()
    newPosVector = (pm.datatypes.Vector((pm.xform(obj2, q=1, t=1, ws=1)) - pm.datatypes.Vector(pm.xform(obj1, q=1, t=1, ws=1))) * amt)
    pm.move(ctl.cv[0:numCvs - 1], newPosVector, r=True, ws=True)

def changeCrvColors(ctlList, colorNum):
    for ctl in ctlList:
        ctl = pm.PyNode(ctl)
        shapes = [shape for shape in ctl.listRelatives(children=True) if isinstance(shape, pm.nodetypes.NurbsCurve)]
        for shape in shapes:
            shape.overrideEnabled.set(1)
            shape.overrideColor.set(colorNum)

#def createLineBetweenObjs(ctl, jnt, extrasGrp, extrasVisGrp, ctlsGrp):
    #"""Create a 1-degree CV curve that connects obj1 to obj2 for display purposes"""
    #nms = ctl.name().split("_")
    #nm = "_".join(nms[:-1])
    #crv = pm.curve(p=[(0, 0, 0), (1, 0, 0)], k=[0, 1], d=1)
    #crv.rename("%sLine_crv" % nm)

    #cl1 = pm.cluster(crv.cv[0], name="%sLineA_clu" % nm)[1]
    #cl2 = pm.cluster(crv.cv[1], name="%sLineB_clu" % nm)[1]

    #pm.pointConstraint(jnt, cl1)
    #pm.pointConstraint(ctl, cl2)

    #cl1.setParent(extrasGrp)
    #cl2.setParent(extrasGrp)
    #crv.setParent(extrasVisGrp)
    #crv.overrideEnabled.set(1)
    #crv.overrideDisplayType.set(2)
    #return crv


def duplicateHierarchy(nodes, toReplace=None, replaceWith=None):
    """Duplicate the pymel objects in the list, and return them as a hierarchy in the order of the list.
    If the objects are joints, make sure that the scale of the previous joint is connected to the inverse scale
    of the next joint."""
    #create PyNodes
    for i in range(len(nodes)):
        nodes[i] = pm.PyNode(nodes[i])

    newList = []
    for i, node in enumerate(nodes):
        newList.append(pm.duplicate(node, parentOnly=True)[0])
    for i, node in enumerate(newList):
        if i == 0:
            continue
        pm.parent(node, newList[i - 1])

    if toReplace and replaceWith:
        for i, item in enumerate(newList):
            #rename it based on the original nodes, since the new ones will have numbers
            item.rename(re.sub(toReplace, replaceWith, nodes[i].name()))

    #parent to the world; if already a child of world, getParent() returns empty string
    if newList[0].getParent():
        newList[0].setParent(world=True)

    fixInverseScale(newList)
    return newList

def parentNodesFromTree(tree):
    """
    Given a node tree from getNodeTree, ensure that nodes in the tree are parented
    as described by the tree
    """
    for parent_, childList in tree.items():
        for child in childList:
            if child.getParent() != parent_:
                child.setParent(parent_)

def unparentNodesFromTree(tree):
    for parent_, childList in tree.items():
        for child in childList:
            if child.getParent() != None:
                child.setParent(world=True)


def snap(master, slave, point=True, orient=True, scale=False, ignoreOrient=False):
    """snap the slave to the position and orientation of the master's rotate pivot
    @param master: the driver
    @param slave: the node being moved
    @param point=True: snap position
    @param orient=True: snap rotations
    @param scale=True: match scale
    @param ignoreOrient: if the master is a joint, add the inverse of its orientation to the
      slave's rotations"""
    
    if point:
        pm.delete(pm.pointConstraint(master, slave, mo=False))
    if orient:
        pm.delete(pm.orientConstraint(master, slave, mo=False))
    if scale:
        slave.setScale(master.getScale())

    if ignoreOrient:
        if isinstance(master, pm.nt.Joint):
            addlRot = master.jo.get()
            slave.rx.set(slave.rx.get() + -1*(addlRot[0]))
            slave.ry.set(slave.ry.get() + -1*(addlRot[1]))
            slave.rz.set(slave.rz.get() + -1*(addlRot[2]))
            
def snapMany(master, slaveList, point=True, orient=True, scale=False):
    """snap a list of slvaes to a master's rotate pivot"""
    if type(slaveList) != type([]) or type(slaveList) != type(()):
        raise BeingsError("snapMany accepts a list of objects")
    for slave in slaveList:
        snap(master, slave, point=point, orient=orient, scale=scale)


#===============================================================================
# Joint Utils
#===============================================================================


g_vectorMap = {'posX': [1, 0, 0],
               'posY': [0, 1, 0],
               'posZ': [0, 0, 1],
               'negX': [-1, 0, 0],
               'negY': [0, -1, 0],
               'negZ': [0, 0, -1]}

def makeDuplicateJointTree(topJoint, toReplace=None, replaceWith=None, freeze=True):
    """
    make a duplicate of the hierarhcy starting at topJoint, delete any non-joint
    nodes, and ensure joints are properly connected.
    
    Return a dictionary of {parentJoint:[branchJnt1, branchJnt2...]} for all branches
    in the tree.  The topmost node branch's key is None
    """
    topJoint = pm.PyNode(topJoint)
    result = []
    dups = pm.duplicate(topJoint, rc=True)
    #parent to world
    if dups[0].getParent():
        dups[0].setParent(world=True)

    for node in dups[0].listRelatives(ad=True):
        if not isinstance(node, pm.nodetypes.Joint):
            pm.delete(node)
        else:
            if toReplace and replaceWith:
                replaceInName(node, toReplace, replaceWith)
            if freeze:
                pm.makeIdentity(node, apply=True, r=True, s=True, t=True, n=True)
            result.append(node)
    #ensure joints are connected
    fixInverseScale(result)
    #the top node isn't in the result list yet
    result.append(dups[0])
    #usually it's in reverse order
    result.reverse()
    return result


def fixInverseScale(jointList):
    """
    For all the joints in the list, ensure that their parent's scale is
    connected to the child's inverseScale attribute
    """
    for jnt in jointList:
        if not isinstance(jnt, pm.nodetypes.Joint):
            continue
        parent = jnt.getParent()
        if isinstance(parent, pm.nodetypes.Joint):
            #check if there's a connection
            if len(jnt.inverseScale.inputs()) != 1 or jnt.inverseScale.inputs(plugs=True)[0] != parent.scale:
                parent.scale >> jnt.inverseScale
                _logger.debug("connected %s's scale to %s's inverse scale" % (parent.name(), jnt.name()))


def getJointDict(jointList):
    """
    Get a dictionary of joint attributes from which a joint can be constructed
    """
    result = {}
    for jnt in jointList:
        jnt = pm.nodetypes.Joint(jnt)
        jname = str(jnt.name())

        #get its attributes
        parent = jnt.getParent()
        if parent:
            parent = str(parent.name())

        result[jname] = {}
        result[jname]['parent'] = parent

        result[jname]['attrs'] = {}
        result[jname]['attrs']['translate'] = list(jnt.translate.get())
        result[jname]['attrs']['rotate'] = list(jnt.rotate.get())
        result[jname]['attrs']['scale'] = list(jnt.scale.get())
        result[jname]['attrs']['rotateAxis'] = list(jnt.rotateAxis.get())
        result[jname]['attrs']['rotateOrder'] = jnt.rotateOrder.get()
        result[jname]['attrs']['stiffness'] = list(jnt.stiffness.get())
        result[jname]['attrs']['preferredAngle'] = list(jnt.preferredAngle.get())
        result[jname]['attrs']['jointOrient'] = list(jnt.jointOrient.get())
        result[jname]['worldMatrix'] = pm.xform(jnt, q=True, matrix=True, ws=True)

    return result

def createJointsFromDict(jointDict, deleteExisting=False):
    """
    Create joints based on values stored in a dictionary.  Joints cannot already
    exist, as parenting is based on name
    """
    #check to see if the joints already exist
    for jnt in jointDict.keys():
        if pm.objExists(jnt):
            if deleteExisting == True:
                pm.delete(jnt)
            else:
                raise BeingsError('%s already exists. Joints must not already exist')
    result = []
    jntParents = []
    for jntName, catDict in jointDict.items():
        pm.select(cl=True)
        jnt = pm.joint(name=jntName)
        result.append(jnt)
        if catDict['parent'] is not None:
            jntParents.append((jntName, catDict['parent']))
    #first set up the parenting
    noParentJnt = None
    for jnt, parent in jntParents:
        jnt = pm.nodetypes.Joint(jnt)
        try:
            jnt.connect(parent, pm=True)
        #if we can't parent, set it to the world
        except pm.MayaNodeError:
            noParentJnt = jnt
            if jnt.getParent():
                pm.parent(jnt, world=True)

    #now set up the attrs
    for jntName, catDict in jointDict.items():
        jnt = pm.nodetypes.Joint(jntName)
        #attrs in the 'attrs' dict should be named what the PyNode function is    
        for attr, attrVal in catDict['attrs'].items():
            attr = getattr(jnt, attr)
            attrFunc = getattr(attr, 'set')
            attrFunc(attrVal)
    #if there was a joint that couldn't be parented, set it's world matrix
    if noParentJnt:
        _logger.debug("Couldn't find parent for %s...setting to world matrix" % noParentJnt.name())
        m = jointDict[noParentJnt.name()]['worldMatrix']
        pm.xform(noParentJnt, matrix=m, worldSpace=True)

    #fix any inverse scale issues
    fixInverseScale([pm.nodetypes.Joint(jnt) for jnt in jointDict.keys()])
    return result

def dupJntDct(dct, oldNamePart, newNamePart):
    '''
    Duplicate a joint dict.  Rename the joints
    '''
    result = {}
    parents = {}
    for tok, jnt in dct.items():
        origName = jnt.nodeName()
        newName = re.sub(oldNamePart, newNamePart, origName)        
        result[tok] = pm.duplicate(jnt, parentOnly=1, n=newName)[0]
        parent = jnt.getParent()
        for tok2, par in dct.items():
            if par == parent:
                parents[tok] = tok2
    for childTok, parentTok in parents.items():
        result[childTok].setParent(result[parentTok])
    fixInverseScale(result.values())
    return result

def makeJntChain(char, widgetName, side, namePosList):
    '''
    Make a joint chain.  Positions are given in world space
    @param namePosList: [(jointName, (x,y,z))...]
    @param forceUniqueNames=True:  ensure names are unique
    '''
    result = []
    nextIterator = 'a'
    pm.select(cl=1)
#    if forceUniqueNames:
#        namePre = "%s_%s_%s_jnt_" % (char, side, widgetName)
#        lastJnts = [j.name().split('|')[-1].strip(namePre) for j in pm.ls(namePre + "*")]
#        lastJnts = [itr for itr in lastJnts if isValidIterator(itr)]
#        lastJnts.sort
#        if lastJnts:
#            nextIterator = getNextIterator(lastJnts[-1])
    for jntname, pos in namePosList:
        result.append(pm.joint(
          name="%s_%s_%s_%s_%s" % (char, side, widgetName, jntname), p=pos))

    pm.select(cl=1)
    return result

def orientJnt(joint, aimVec=[0, 1, 0], upVec=[1, 0, 0], worldUpVec=[1,0,0], curAimAxis=None):
    #if either joint or loc not provided, query from selection
    joint = pm.PyNode(joint)
    try:
        aimTgt = [x for x in joint.listRelatives(children=True) if isinstance(x, pm.nodetypes.Joint)][0]
    except IndexError:
        par = joint.getParent()
        if par:
            pm.delete(pm.orientConstraint(par, joint, mo=False))
            pm.makeIdentity(joint, apply=True)
        else:
            pm.joint(joint, e=1, oj="none", zso=True)
        return

    pm.parent(aimTgt, world=True)

    #zero orients
    joint.jointOrientX.set(0)
    joint.jointOrientY.set(0)
    joint.jointOrientZ.set(0)

    #aim at next jnt using up loc
    aimCst = pm.aimConstraint (aimTgt, joint, offset=[0, 0, 0], aimVector=aimVec, upVector=upVec, worldUpType="vector",
                               worldUpVector=worldUpVec)

    pm.delete(aimCst)
    #get rotations
    rots = joint.rotate.get()
    #zero rotations
    joint.rotate.set([0, 0, 0])
    #set orients
    joint.jointOrientX.set(rots[0])
    joint.jointOrientY.set(rots[1])
    joint.jointOrientZ.set(rots[2])
    #reparent child joint
    pm.parent (aimTgt, joint)
    pm.select(joint)

def orientToPlane(midJnt, topJnt, btmJnt, aimVector, upVector, flipAim=False, flipUp=False):
    #get the aim vector
    worldUpVec = getXProductFromNodes(midJnt, topJnt, btmJnt)
    orientJnt(midJnt, worldUpVec, aimVector, upVector)

def getXProductFromNodes(midObj, topObj, btmObj):
    """
    get a cross product based upon the position of the first three objects in objList
    Returns the cross product of two vectors: midObj to topObj and midObj to btmObj
    """

    #get the vectors
    midPos = pm.xform(midObj, q=True, worldSpace=True, translation=True)
    topPos = pm.xform(topObj, q=True, worldSpace=True, translation=True)
    btmPos = pm.xform(btmObj, q=True, worldSpace=True, translation=True)

    topVector = [topPos[0] - midPos[0], topPos[1] - midPos[1], topPos[2] - midPos[2]]
    btmVector = [btmPos[0] - midPos[0], btmPos[1] - midPos[1], btmPos[2] - midPos[2]]

    #create a temporary vectorProduct node
    vp = pm.createNode("vectorProduct")
    #set to cross product
    vp.operation.set(2)
    vp.input1.set(btmVector)
    vp.input2.set(topVector)

    #store the cross product
    cp = vp.output.get()

    #delete the vector node
    pm.delete(vp)
    return cp


def getNodeAxisVector(node, axis):
    """
    Return a 3-element list of world-space vectors corresponding with the axes 
    of joint.  Vectors are returned as [aimVec, upVec, weakVec]    
    """
    node = pm.PyNode(node)
    x = pm.datatypes.Vector(node.getMatrix(worldSpace=True)[0][:3])
    y = pm.datatypes.Vector(node.getMatrix(worldSpace=True)[1][:3])
    z = pm.datatypes.Vector(node.getMatrix(worldSpace=True)[2][:3])

    localVars = locals()

    if 'neg' in axis:
        vector = localVars[axis[-1].lower()] * -1
    else:
        vector = localVars[axis[-1].lower()]

    return vector

def setNodeAxisVectors(node, oldA1="posY", oldA2="posX", newA1="posY", newA2="posX", orient=True):

    node = pm.PyNode(node)
    #these are world space vectors

    oldV1 = getNodeAxisVector(node, oldA1)
    oldV2 = getNodeAxisVector(node, oldA2)
    _logger.debug("%s vector: %s; %s vector: %s" % (oldA1, str(oldV1), oldA2, str(oldV2)))
    newV1 = g_vectorMap[newA1]
    newV2 = g_vectorMap[newA2]


    posL = pm.spaceLocator()
    aimL = pm.spaceLocator()
    upL = pm.spaceLocator()
    aimL.setParent(posL)
    upL.setParent(posL)
    pm.delete(pm.pointConstraint(node, posL, mo=False))

    aimL.translate.set(oldV1)
    upL.translate.set(oldV2)
    pm.delete(pm.aimConstraint(aimL, node, aimVector=newV1, upVector=newV2, worldUpType='object', worldUpObject=upL))
    pm.delete(posL)

    if orient:
        node.jox.set(node.jox.get() + node.rotateX.get())
        node.joy.set(node.joy.get() + node.rotateY.get())
        node.joz.set(node.joz.get() + node.rotateZ.get())
        node.rotate.set([0, 0, 0])


def splitJnts(parentJnt, num):
    """
    Split the parent joint with a numer of child joints
    Use the joint's connect() method to ensure that the inverse scale attrs
    are correctly linked.  Return a list of new joints in order of hierarchy
    """

    parentJnt = pm.PyNode(parentJnt)
    result = []
    #get the first child of the parent
    childJnt = parentJnt.listRelatives(type="joint", children=True)[0]
    pPos = pm.xform(parentJnt, q=1, t=1, ws=1)
    cPos = pm.xform(childJnt, q=1, t=1, ws=1)

    #get a vector of the amount each joint needs to move (in world space)
    perJntVec = [(cPos[0] - pPos[0]) / (num + 1), (cPos[1] - pPos[1]) / (num + 1), (cPos[2] - pPos[2]) / (num + 1)]

    lastJnt = parentJnt
    for i in range(num):
        #duplicate the parent to get a new joint
        newJnt = pm.duplicate(parentJnt)[0]
        #delete its children
        newJntChildren = newJnt.listRelatives(children=True)
        for child in newJntChildren:
            pm.delete(child)
        #parent it to the world if it's not already
        if newJnt.getParent():
            newJnt.setParent(world=True)

        #get the new position in world space of the new joint
        newJntPos = [pPos[0] + (perJntVec[0] * (i + 1)), pPos[1] + (perJntVec[1] * (i + 1)), pPos[2] + (perJntVec[2] * (i + 1))]
        pm.xform(newJnt, t=newJntPos, ws=1)

        #parent it to the last joint created
        newJnt.connect(lastJnt, pm=True)
        #parent the child joint to the new one
        if childJnt.getParent():
            childJnt.setParent(world=True)
        childJnt.connect(newJnt, pm=True)
        lastJnt = newJnt
        result.append(newJnt)
    return result
