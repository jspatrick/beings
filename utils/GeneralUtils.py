'''
This module contains general utilities.  If a function is used in other 
utilities, it should be defined here.
'''
import logging, inspect, sys, re, string
import pymel.core as pm
from Exceptions import * #@UnusedWildImport

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


##################################################
## Name Utils
##################################################

"""
The naming convention of all nodes should be strictly enforced by calling these
naming utils on names provided by users.
The naming convention for all nodes in a character should be as follows:

character_side_resolution_part_description_alphaincrementor

All names should be lowercase.  The only place where uppercase is acceptable is
in automatically-renamed shape nodes, as maya tends to force a 'Shape' suffix.
Numbers should be avoided, as numbered objects typically signify duplicates.
The only place where numbers are acceptable is if they are appended to character,
as this is a way to differentiate between multiple duplicate characters in a scene.

charater: the current character ('ironman')

resolution:  this is somewhat arbitrary, and is dependent upon the data being named.
geometry should generally be 'hi', 'md', 'lo', 'px' (proxy), etc.  Some nodes may
omit this - for example, a multiplyDivide node.  However, joints can also use 
this to differentiate between different layers.  Examples might be:
'ik': joints for ik controls
'fk': joints for fk controls
'bs': 'bind skeleton' joints.  This is the main hierarchy that's bound to the geo.
'ut': 'utility' joints

part_description: a description of the node, separated by underscores, of arbitrary
                    length.'
                    length is arbitrary ('upper_arm')

The main difference between this naming convention and the previous 4-token, 
mixed-case system I previously used is that it sacrifices ease of parsing for
readability.  A major reason for avoiding the parse-ability of nodes by name
is that it is unreliable, as object names in maya are volitle.  It also
decreases the temptation to write code that operates based on node names. Instead,
a more robust tagging and connection system will be used to keep track of nodes.
"""

def getNameGroups(obj):
    """
    return groups if the node is 'well named', else return empty list.
    
    This should match the following:
    mycharacter_cn_hi_arm_
    mycharacter_arm_ik_stretch_mdn_a
    
    """
    obj = str(obj)
    pattern = r"""
    ([a-z])_    #match character name
    (rt|lf|cn)_        #match side
    (([a-z]+_)+)       #match resolution, description, etc
    ([a-z]+)           #match the last token
    (Shape)?$          #some nodes might have 'Shape' at the end
    """
    nameRE = re.compile(pattern, re.VERBOSE)
    match = nameRE.match(obj)
    if match:
        return match.groups()
    else:
        return []

def isValidCharName(charName):
    """
    @return: True/False
    """
    if re.match(r'^[a-z]+[0-9]*$', charName):
        return True
    return False

def isValidWidgetName(widgetName):
    """
    @return: True/False
    """
    if re.match(r'^[a-z]+[a-z_]*[a-z]+$' , widgetName):
        return True
    return False

def isValidSide(widgetSide):
    """
    @return True/False
    """
    if widgetSide == "lf" or widgetSide == "rt" or widgetSide == "cn":
        return True
    return False

def isValidIterator(iterator):
    """
    @return True/False
    """
    #for now, we'll say that an iterator shouldn't be more than 2-characters in length
    #since we probably won't ever need 600 of a certain node
    if re.match(r'^[a-z]{1,2}$', iterator):
        return True
    return False

def replaceInName(node, oldPart, newPart):
    """replace the oldPart from an object's name with newPart.  OldPart is
    a regular expression.

    @return: a PyNode of the object"""
    obj = pm.PyNode(node)
    newName = re.sub(oldPart, newPart, obj.name())
    obj.rename(newName)
    return obj

def replaceInNames(nodeList, oldPart, newPart):
    """replace the oldPart from the name of a list of objects with newPart.
    @return: A String of the new object name"""
    result = []
    for node in nodeList:
        result.append(replaceInName(node, oldPart, newPart))
    return result

def getNextIterator(iterator):
    """
    get the next letter iterator after iterator.  For example:
    >>>getNextIterator('a')
    >>>'b'
    >>>getNexIterator('ab')
    >>>'ac'
    @return: string
    """
    if not isValidIterator(iterator):
        raise ThrottleError("%s is not a valid iterator" % iterator)
    i = string.lowercase.index(iterator[-1])
    if i == 25:
        return iterator + "a"
    else:
        return iterator[:-1] + string.lowercase[i + 1]

def getPreviousIterator(iterator):
    """
    get the previous letter iterator before iterator.  For example:
    >>>getPreviousIterator('a')
    >>>''
    >>>getPreviousIterator('ab')
    >>>'aa'
    @return: string
    """
    if not isValidIterator(iterator):
        raise ThrottleError("%s is not a valid iterator" % iterator)

    i = string.lowercase.index(iterator[-1])
    if i == 0 and len(iterator) == 1:
        return ""

    elif i == 0 and len (iterator) >= 1:
        return iterator[:-2]

    else:
        return iterator[:-1] + string.lowercase[i - 1]

def getNextName(node):
    """
    Get the next available version of a node name, based on what's
    currently in the scene.
    no objects with this name in the scene
    >>> getNextName('bob_lf_arm_jnt')
    >>> 'bob_lf_arm_jnt_a'
    >>> getNextName('bob_lf_leg_jnt')
    >>> 'bob_lf_leg_jnt_c'
    >>> getNextName('bob_lf_spine_jnt_c')
    """

    if isinstance(node, pm.PyNode):
        node = node.name()

    #go throgh a series of steps to determine whether the last node is an iterator
    nodeParts = node.split("_")
    #if it's a, go ahead and return b
    if nodeParts[-1] == 'a':
        nodeParts[-1] = 'b'
        return "_".join(nodeParts)

    #if it's something other than a, see if a previous version is in the scene.
    if isValidIterator(nodeParts[-1]):
        prev = getPreviousIterator(nodeParts[-1])
        if pm.objExists("_".join(nodeParts[:-2].append(prev))):
            nodeParts[-1] = getNextIterator(nodeParts[1])
            return "_".join(nodeParts)

    #if this isn't true, assume that we don't actually have an iterator
    #we need to append an iterator and keep upping it until a version doesn't exist
    nodeParts.append('a')
    while pm.objExists("_".join(nodeParts)):
        nodeParts[-1] = getNextIterator(nodeParts[-1])

    return "_".join(nodeParts)

#===============================================================================
# misc utils
#===============================================================================
#def isChildOf(child, parent):
#    return true if child is an immediate or distant child of parent 

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

def nodeLock(obj, hierarchy=False, unlock=False):
    """
    Lock or unlock a node or node hierarch.  This does not lock 
    the individual attributes, just the node.
    @return: a List of nodes operated upon
    """
    pass

def makeUnkeyableAttr(obj, attr):
    """Create an unkeyable attribute on a node.  This is useful for separating
    attributes"""
    obj = pm.PyNode(obj)
    attr = str(attr)
    obj.addAttr(attr, keyable=False, at="bool")
    newAttr = pm.PyNode("%s.%s" % (obj.name(), attr))
    newAttr.showInChannelBox(True)
    return newAttr


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

def parentShape(parent, child, deleteChildXform=True):
    """
    Parent the shape nodes of the children to the transform of the parent.  
    Return all shapes of the new parent
    """
    #freeze the child under the parent then unparent
    pm.parent(child, parent)
    pm.makeIdentity(child, apply=True, t=1, r=1, s=1, n=0)
    pm.parent(child, w=1)
    shapes = [shape for shape in child.listRelatives(children=True) if isinstance(shape, pm.nodetypes.GeometryShape)]
    for shape in shapes:
        pm.parent(shape, parent, r=True, s=True)
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

#======================================================================
# hierarchy utilities
#======================================================================

def getHierarhcyChildren(start, end, ignoreGeoShapes=False):
    """
    Traverse the hierarchy from top(start) to bottom(end) and return a dictionary of
    {parent: (parentChild1, parentChild2), ...}
    
    If ignoreGeoShapes is true, mesh shape nodes will not be included in the dict
    
    If end is not a child of start, raise an exception
    """
    start = pm.PyNode(start)
    end = pm.PyNode(end)

    #ensure end is actually a descendednt of start
    allCh = start.listRelatives(ad=True)
    if end not in allCh:
        raise ThrottleError("%s is not a descendent of %s" % (end, start))

    #now we're good to go.  Start walking up the tree from the bottom
    result = {}
    lastNode = end
    while lastNode != start:
        lastNode = lastNode.getParent()
        if ignoreGeoShapes:
            result[lastNode] = [c for c in lastNode.getChildren()
                                if not isinstance(c, pm.nodetypes.GeometryShape)]
            continue
        result[lastNode] = lastNode.getChildren()

    return result

def isSingleBranch(start, end, ignoreGeoShapes=True):
    """
    Validate that the hierarchy is a single branch from top to bottom - i.e., that all
    parents in the hierarchy contain a single child.
    
    If ignoreShapes is true, shape nodes that are children of transforms will not cause
    the function to fail
    
    Return True or False
    """

    h = getHierarhcyChildren(start, end, ignoreGeoShapes=ignoreGeoShapes)

    for nodeList in h.values():
        if len(nodeList) > 1:
            return False
    return True

def getNodeBranch(start, end, errorIfNotSingle=True, ignoreGeoShapes=True):
    """
    Return a list of nodes from top to bottom that represents the hierarchy of
    the branch.
    """
    #run the isSingleBranch function to test that end descends from start
    isSingleTest = isSingleBranch(start, end, ignoreGeoShapes)
    if errorIfNotSingle:
        if not isSingleTest:
            msg = "The hierarchy from %s to %s is not a single branch."
            "\n" % (str(start), str(end))
            "Geometry shape nodes %s being evaluated as part of the"
            "hierarchy" % ignoreGeoShapes and "*are not*" or "*are*"

            raise ThrottleError(msg)
    start = pm.PyNode(start)
    end = pm.PyNode(end)

    result = [end]
    last = end
    while last != start:
        last = last.getParent()
        result.append(last)

    return result

def getNodeTree(topNode, nodeType=None):
    """
    Get a node treed
    if nodeType is provided, ignore intermediate nodes of other types
    
    Return a dictionary of a node branch.  The topNode branch has a key of topNode;
    other nodes have a key of their branch parent.
    """

    topNode = pm.PyNode(topNode)
    result = {}
    if nodeType:
        children = topNode.listRelatives(children=True, type=nodeType)
    else:
        children = topNode.listRelatives(children=True)

    #if we have a node with children, add it to the dictionary
    if children:
        result[topNode] = children

    #if there aren't any children, this will get skipped
    for child in children:
        #recurse
        nodeTree = getNodeTree(child, nodeType=nodeType)
        result.update(nodeTree)

    return result

def makeDuplicatesAndHierarchy(nodes, toReplace=None, replaceWith=None):
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
            item.rename(replaceInName(nodes[i].name(), toReplace, replaceWith))

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

def snap(master, slave, point=True, orient=True, scale=False):
    """snap the slave to the position and orientation of the master's rotate pivot"""
    if point:
        slave.setTranslation(master.getTranslation(ws=1), space='world')
    if orient:
        slave.setRotation(master.getRotation(ws=1), space='world')
    if scale:
        slave.setScale(master.getScale())

def snapMany(master, slaveList, point=True, orient=True, scale=False):
    """snap a list of slvaes to a master's rotate pivot"""
    if type(slaveList) != type([]) or type(slaveList) != type(()):
        raise ThrottleError("snapMany accepts a list of objects")
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
                logger.info("connected %s's scale to %s's inverse scale" % (parent.name(), jnt.name()))


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
                raise ThrottleError('%s already exists. Joints must not already exist')
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
        logger.debug("Couldn't find parent for %s...setting to world matrix" % noParentJnt.name())
        m = jointDict[noParentJnt.name()]['worldMatrix']
        pm.xform(noParentJnt, matrix=m, worldSpace=True)

    #fix any inverse scale issues
    fixInverseScale([pm.nodetypes.Joint(jnt) for jnt in jointDict.keys()])
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

def orientJnt(joint, worldUpVec, aimVector=[0, 1, 0], upVector=[0, 0, 1], curAimAxis=None):
    #if either joint or loc not provided, query from selection
    joint = pm.PyNode(joint)
    try:
        aimTgt = [x for x in joint.listRelatives(children=True) if isinstance(x, pm.nodetypes.Joint)][0]
        jointChild = True
    except IndexError:
        #no child joint
        jointChild = False
        if curAimAxis == None:
            msg = "Warning - orienting childless joint %s, and no current aim axis provided." % joint
            msg += "\n...orienting to 'None'"
            logger.warning(msg)
            pm.joint(joint, e=1, oj="none", zso=True)
            return

        else:
            newAimVec = g_vectorMap[curAimAxis]
            aimTgt = pm.spaceLocator()
            #put the target locator in a position along the aim vector of the joint
            aimTgt.setParent(joint)
            aimTgt.setTranslation(newAimVec)
            aimTgt.setParent (world=True)

    pm.parent(aimTgt, world=True)

    #zero orients
    joint.jointOrientX.set(0)
    joint.jointOrientY.set(0)
    joint.jointOrientZ.set(0)

    #aim at next jnt using up loc
    aimCst = pm.aimConstraint (aimTgt, joint, offset=[0, 0, 0], aimVector=aimVector, upVector=upVector, worldUpType="vector",
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
    if not jointChild:
        pm.delete(aimTgt)
    else:
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
    logger.debug("%s vector: %s; %s vector: %s" % (oldA1, str(oldV1), oldA2, str(oldV2)))
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

def modifyOrientation(joint, curAim, curUp, newAim, newUp):
    """
    given a current set of joint aim, up, and weak axes and a new set of these axes, 
    modify the joint's orientation.
    """
    #TODO: This needs to be modified to not just re-orient joints, but to re-orient
    #a single joint by aiming it down it's current aim axis
    worldUpV = g_vectorMap[curUp]
    aimV = g_vectorMap[newAim]
    upV = g_vectorMap[newUp]

    orientJnt(joint, worldUpV, aimV, upV)

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
