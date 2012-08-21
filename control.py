"""
Control Properties
==================

  pos: [float, float, float]
  rot: [float, float, float]
  scale: [float, float, float]
  shape: string
  color: string

Needs
=====
  - Record the attributes used to initially create the shape
  - Bake offsets from a control's transform to the control properties

import beings.control as C
fncs = [x for x in dir(C) if x.startswith('makeShape_')]
for f in fncs:
    import maya.cmds as MC
    MC.file(new=1, f=1)
    getattr(C, f)()
    f = re.sub('^makeShape_', '', f)
    p = os.path.join(os.path.dirname(C.__file__), 'control_lib/%s.ma' % f)
    MC.file(rename=p)
    MC.file(save=1)
"""

import logging, sys, copy, json, os, re
import pymel.core as pm
import maya.mel as MM
import maya.cmds as MC
import maya.OpenMaya as OM

import utils
reload(utils)
import nodeTag

_logger = logging.getLogger(__name__)


_handleData = {'s': [1,1,1],
               'r': [0,0,0],
               't': [0,0,0],
               'color': 'yellow',
               'shape': 'cube',
               'type': 'curve'}

COLOR_MAP = {'null':0,
           'black':1,
           'dark grey':2,
           'lite grey':3,
           'crimson':4,
           'dark blue':5,
           'blue':6,
           'dark green':7,
           'navy':8,
           'fuscia':9,
           'brown':10,
           'dark brown':11,
           'dark red':12,
           'red':13,
           'green':14,
           'blue2':15,
           'white':16,
           'yellow':17,
           'lite blue':18,
           'sea green':19,
           'salmon':20,
           'tan':21,
           'yellow2':22,
           'green2':23,
           'brown2':24,
           'puke':25,
           'green3':26,
           'green4':27,
           'aqua':28,
           'blue3':29,
           'purple':30,
           'fuscia2':31}

SHAPE_ORDER_TAG = 'shapeOrder'


def _argHandleData(**kwargs):
    """
    Return a default handle data dict, modified by any kwards matching keys in _handleData
    """
    result = kwargs.get('handleData', None)
    if result is None:
        result = copy.deepcopy(_handleData)
    else:
        kwargs.pop('handleData')
    for k, newData in kwargs.items():
        defaultData = result.get(k, None)
        if defaultData:
            if not utils.isSiblingInstance(newData, defaultData):
                raise utils.BeingsError("Data type of '%s' arg != original handle data type" % k)
            if utils.isIterable(defaultData) and (len(defaultData) != len(newData)):
                raise utils.BeingsError("Data length of '%s' arg != original handle data type" % k)
            else:
                result[k] = newData
        else:
            _logger.debug('skipping invalid handle arg "%s"' % k)
    return result


def _getLibDir():
    return os.path.join(os.path.dirname(__file__), 'control_lib')

def _getControlPath(controlName):
    return os.path.join(_getLibDir(),
                        '%s.ma' % controlName)
def getAvailableShapes():
    return [os.path.splitext(x)[0] for x in os.listdir(_getLibDir())]

def _importShape(controlName):
    """Import the control file.  Parent all shapes under a new
    xform 'TMP_CTL'.  return the name of the temp xform"""
    path = _getControlPath(controlName)
    if not os.path.exists(path):
        raise RuntimeError("invalid control '%s'" % controlName)

    with utils.NodeTracker() as nt:

        MC.file(path, i=1)
        objects = set(nt.getObjects())

        shapes = [n for n in objects if \
                  MC.objectType(n, isAType='geometryShape')]
        xforms = [n for n in objects if \
                  MC.objectType(n, isAType='transform')]

        objects = set(nt.getObjects())

        MC.delete(shapes, ch=1)
        MC.delete(xforms, ch=1)

        objects.difference_update(shapes)
        objects.difference_update(xforms)

        _logger.debug('Shapes: %s' % shapes)
        _logger.debug('Xforms: %s' % xforms)
        _logger.debug('Others: %s' % objects)

        #delete anything else that was imported
        for obj in objects:
            if MC.objExists(obj):
                MC.delete(obj)

    tmpXform = MC.createNode('transform', n='TMP_CTL')
    utils.parentShapes(tmpXform, xforms)
    return tmpXform

def getShapeNodes(ctl):
    """
    Return a list of shapes in the control
    """
    editor = getEditor(ctl)
    if editor:
        ctl = editor
    nodes = MC.listRelatives(ctl, shapes=1, pa=1)
    return [n for n in nodes if MC.objectType(n, isAType='geometryShape')]

def _setColor(xform, color):
    if color not in COLOR_MAP:
        _logger.warning("invalid color '%s'" % color)
        return

    result = []
    for shape in (MC.listRelatives(xform, pa=1, type='geometryShape') or []):

        MC.setAttr('%s.overrideEnabled' % shape, 1)
        MC.setAttr('%s.overrideColor' % shape, COLOR_MAP[color])
        result.append(shape)

    return result

CONTROL_TAG_NAME = 'control'
def getInfo(control, includeEdits=True):
    info =  nodeTag.getTag(control, CONTROL_TAG_NAME)
    editor = getEditor(control)
    if includeEdits and editor:
        info['t'] = list(MC.getAttr('%s.t' % editor)[0])
        info['r'] = list(MC.getAttr('%s.r' % editor)[0])
        info['s'] = list(MC.getAttr('%s.s' % editor)[0])
    return info

def setInfo(control, info):
    control = str(control)
    nodeTag.setTag(control, CONTROL_TAG_NAME, info)


LOCKS_TAG_NAME = 'controlLocks'
_defaultLocks = {'lockedKeyable': [],
                   'unlockedUnkeyable': [],
                   'unlockedKeyable': []}

def setLockTag(ctl, **kwargs):
    """
    Add new lock information to the lock tag of a control.  Create the tag
    if it does not exist

    @keyword unlockedUnkeyable: channels that are unlcoked but not keyable
    @keyword uu: unlockedUnkeyable alias
    @keyword unlockedKeyable: channels that are unlcoked but not keyable
    @keyword uk: unlockedKeyable alias
    @keyword lockedKeyable: channels that are unlcoked but not keyable
    @keyword lk: lockedKeyable alias

    update locking information on controls.  This is used to toggle locking when rig nodes are
    locked
    """

    if not (isControl(ctl) or isEditor(ctl)):
        raise RuntimeError('%s is not a control or editor' % ctl)
    if nodeTag.hasTag(ctl, LOCKS_TAG_NAME):
        current = nodeTag.getTag(node, LOCKS_TAG_NAME)
    else:
        current = copy.deepcopy(_defaultLocks)

    for long_, short in [('unlockedUnkeyable', 'uu'),
                          ('unlockedKeyable', 'uk'),
                          ('lockedKeyable', 'lk')]:

        val = set(kwargs.get(long_, kwargs.get(short, [])))
        current[long_] = list(val.union(current[long_]))

    nodeTag.setTag(ctl, LOCKS_TAG_NAME, current)


def getLockTag(node):
    """
    Get the lock tag of a node.  If the node is not tagged,
    the default empty lock tag is returned
    @param node: the node to query
    @type node: str

    @return: lock tag dictionary
    @rtype: dict
    """
    if not nodeTag.hasTag(node, LOCKS_TAG_NAME):
        return copy.deepcopy(_defaultLocks)

    return nodeTag.getTag(node, LOCKS_TAG_NAME)

def _getLeafAttributes(node, attr, returnSelf=True):
    """
    Get a list of child attributes.  If the attribute itself is the
    leaf, return it in a list
    """
    children = MC.attributeQuery(attr, n=node, lc=1)
    if not children:
        if returnSelf:
            return [attr]
        else:
            return []
    for child in children:
        children.extend(_getLeafAttributes(node, child, returnSelf=False))
    return children


def setLocks(node):
    """
    Lock a node according to its lock tag.
    @param node: the node to lock
    """

    lockData = getLockTag(node)

    attrs = MC.listAttr(node, l=False, k=False, se=True)
    for attr in attrs:
        #don't lock compound attributes - just lock the 'leaf' children
        if not MC.attributeQuery(attr, n=node, ex=1):
            continue

        children = MC.attributeQuery(attr, n=node, nc=1)
        if children:
            continue
        try:
            MC.setAttr('%s.%s' % (node, attr), l=True, k=False, cb=False)
        except:
            _logger.debug("Cannot lock %s.%s" % (node, attr))


    for attr in lockData['unlockedUnkeyable']:
        for childAttr in _getLeafAttributes(node, attr):
            MC.setAttr('%s.%s' % (node, childAttr), l=False)

    for attr in lockData['lockedKeyable']:
        for childAttr in _getLeafAttributes(node, attr):
            MC.setAttr('%s.%s' % (node, childAttr), k=True)

    for attr in lockData['unlockedKeyable']:
        for childAttr in _getLeafAttributes(node, attr):
            MC.setAttr('%s.%s' % (node, childAttr), k=True, l=False)


def isControl(xform):
    if nodeTag.hasTag(xform, CONTROL_TAG_NAME):
        return True

def isEditor(xform):
    par = MC.listRelatives(xform, parent=1)
    if not par:
        return False
    if isControl(par[0]):

        if xform == '%s_editor' % par[0]:

            return True
    return False

def makeControl(name, xformType=None, **kwargs):
    """
    Create a control object
    @param name: the control name
    @param xformType: if creating a new xform, use this node type.  Defaults
    to transform
    @keyword t: offset the position of the handle shape.
    @keyword r: offset the rotation of the handle shape.
    @keyword s: offset the scale of the handle shape.
    @note: offsets are applied in the control xform's local space
    @raise RuntimeError: if the control exists, and xformType is supplied but does
    not match the current node's xform type
    """

    #see if the object exists, and create it if not
    editor = None
    if MC.objExists(name):
        if xformType and xformType != MC.objectType(name):
            raise RuntimeError('control exists and is not of type %s' % xformType)
        editor = getEditor(name)
        if editor:
            setEditable(name, False)
    else:
        if not xformType:
            xformType = 'transform'

        name = MC.createNode(xformType, name=name, parent=None)

    xform = name
    #delete any shapes that exist
    for shape in MC.listRelatives(xform, type='geometryShape', pa=1) or []:
        MC.delete(shape)


    #create an attribute to store handle info
    handleData = _argHandleData(**kwargs)

    #snap the tmp shape to the xform
    tmpXform = _importShape(handleData['shape'])

    utils.snap(xform, tmpXform, scale=True)

    #apply transformations
    MC.parent(tmpXform, xform)
    MC.setAttr('%s.t' % tmpXform, *handleData['t'], type='double3')
    MC.setAttr('%s.r' % tmpXform, *handleData['r'], type='double3')
    MC.setAttr('%s.s' % tmpXform, *handleData['s'], type='double3')
    MC.parent(tmpXform, world=True)

    utils.parentShape(xform, tmpXform)
    if handleData.get('type') != 'surface':
        _setColor(xform, handleData['color'])

    #set the handle info
    _logger.debug("handle data: %r" % handleData)
    setInfo(xform, handleData)

    if editor:
        setEditable(xform, True)

    return xform


def flushControlScaleToShape(control):
    """If a control's scale is not at identity, push scaling down to the shape
    and set the control's scale to [1,1,1]"""
    if not isControl(control):
        raise RuntimeError("%s is not a control" % control)

    currentScale = list(MC.getAttr('%s.s' % control)[0])
    if currentScale != [1,1,1]:

        editor = getEditor(control)
        if editor:
            editable=True
        else:
            editable=False
            setEditable(control, True)
            editor = getEditor(control)

        eScale = list(MC.getAttr('%s.s' % editor)[0])
        for i in range(3):
            eScale[i] = eScale[i] * currentScale[i]

        MC.setAttr('%s.s' % editor, *eScale, type='double3')
        MC.setAttr('%s.s' % control, 1,1,1, type='double3')

        if not editable:
            setEditable(control, False)


def getEditor(ctl):
    """If an editor for the control exists, return it.  Else, return None
    @param ctl: the control
    @type ctl: str

    @return: the control, or None
    @rtype: str or None
    """
    editor = '%s_editor' % ctl
    if MC.objExists(editor):
        return editor
    return None


def setEditable(ctl, state):
    """
    Add an intermediate xform node to a control.  The control's editable
    state can be toggled, and transformation differences to the 'editor' node
    will be flushed down to the shape level and recorded in the control data
    @param ctl: the control to make editable
    @type ctl: str
    @param state: True or False
    @type state: bool

    @return: True if state was changed, else False
    """
    editor = getEditor(ctl)
    if editor and state:
        return False
    elif not editor and not state:
        return False

    info  = getInfo(ctl)
    if state:
        editor = MC.createNode('transform', name='%s_editor' % ctl, parent=None)
        MC.parent(editor, ctl)
        MC.setAttr('%s.t' % editor, *info['t'], type='double3')
        MC.setAttr('%s.r' % editor, *info['r'], type='double3')
        MC.setAttr('%s.s' % editor, *info['s'], type='double3')
        MC.setAttr("%s.shear" % editor, 0,0,0, type='double3')
        utils.parentShape(editor, ctl, deleteChildXform=False)

    else:
        setInfo(ctl, info)
        utils.parentShape(ctl, editor, deleteChildXform=True)
    return True

STORABLE_TAG_NAME = 'recordableXform'


_xformKwargs = ['matrix',
                'rotateOrder',
                'parent',
                'worldSpace',
                'jointOrient',
                'radius',
                'nodeType',
                'categories',
                'controlArgs',
                'rotation']


def setStorableXformAttrs(xform, **kwargs):
    """
    Set the tag on the node.  Any kwargs passed will be set;
    others will be left at the current value if one exists, or set
    to the default value if non-existant

    @keyword categories: node categories
    @type categories: list of strings

    """
    tagD = {'categories': [],
            'worldSpace': False}

    if nodeTag.hasTag(xform, STORABLE_TAG_NAME):
        tagD = nodeTag.getTag(xform, STORABLE_TAG_NAME)

    categories = kwargs.get('categories', tagD['categories'])
    worldSpace = kwargs.get('worldSpace', tagD['worldSpace'])

    assert isinstance(categories, list) or isinstance(categories, tuple)


    d = {'worldSpace': bool(worldSpace),
         'categories': list(categories)}

    nodeTag.setTag(xform, STORABLE_TAG_NAME, d)


def addStorableXformCategory(xform, *categories):
    if not nodeTag.hasTag(xform, STORABLE_TAG_NAME):
        raise RuntimeError("%s is not a storable node" % xform)

    tagD = nodeTag.getTag(xform, STORABLE_TAG_NAME)
    tagD['categories'].extend(categories)
    tagD['categories'] = list(set(tagD['categories']))
    nodeTag.setTag(xform, STORABLE_TAG_NAME, tagD)
    return xform



def makeStorableXform(xform, **kwargs):
    """Make a storable xform
    @keyword nodeType: the type of node to create.  Defaults to transform
    @keyword worldSpace: apply matrix in worldSpace
    @keyword categories: apply these categories
    @keyword matrix: apply this matrix to the node
    @keyword parent: parent the node under this xform
    @keyword jointOrient: apply this joint orientation
    @keyword radius: apply this joint radius"""
    #get args - get defaults if not specified
    for key in kwargs:
        if key not in _xformKwargs:
            raise RuntimeError("%s is not a supported keyword" % key)

    #create or find the node
    if not kwargs.get('nodeType'):
        kwargs['nodeType'] = 'transform'

    if MC.objExists(xform):
        if MC.nodeType(xform) != kwargs['nodeType']:
            _logger.warning("Cannot change type of existing node '%s'" % xform)
    else:
        if kwargs['nodeType'] not in ['transform', 'joint']:
            raise RuntimeError('invalid node type "%s"' % str(kwargs['nodeType']))

        xform = MC.createNode(kwargs['nodeType'], name=xform)



    #apply rotate order
    if kwargs.get('rotateOrder', None) is not None:
        MC.setAttr('%s.rotateOrder' % xform, kwargs['rotateOrder'])

    #apply xform
    if kwargs.get('matrix', None) is not None:
        MC.xform(xform,
                 m=kwargs['matrix'],
                 ws=kwargs['worldSpace'])

    #parent the node.  None can be used to parent to the world, so grab something
    #that's not a valid node name in maya
    parent = kwargs.get('parent', '~noArg~')
    nodeType = MC.objectType(xform)

    if parent != '~noArg~' and parent is not None and MC.objExists(parent):
        parentNodeType =  MC.objectType(parent)
        if parent in (MC.listRelatives(xform, parent=1) or []):
            _logger.debug("Skipping parenting - already parented")
        else:
            #if the node is worldSpace, preserve world transforms;
            #else, preserve local transforms
            preOrient = None
            if nodeType == 'joint':
                preOrient = MC.getAttr('%s.jointOrient' % xform)[0]
                print preOrient


            if nodeType == 'joint' and parentNodeType == 'joint':
                #connectJoint cmd screws up scale, but keeps new xform from
                #being made
                if MC.listRelatives(xform, parent=1):
                    MC.parent(xform, world=1)
                tmp = MC.getAttr('%s.s' % xform)[0]
                MC.connectJoint(xform, parent, pm=1)
                #set the scale back
                MC.setAttr('%s.s' % xform, *tmp, type='double3')
            else:
                MC.parent(xform, parent, absolute=kwargs['worldSpace'])


            if nodeType == 'joint':
                #by default, transforms needed to preserve world space are put into joint's orient.  Put them
                #into rotation instead - it's more obvious and consistent with transform behavior
                MC.makeIdentity(xform, apply=1, r=1, t=0, s=0, n=0, jointOrient=0)
                jo = MC.getAttr('%s.jointOrient' % xform)[0]
                jo = [jo[0] - preOrient[0], jo[1] - preOrient[1], jo[2] - preOrient[2]]
                MC.setAttr('%s.jointOrient' % xform, *preOrient, type='double3')
                MC.setAttr('%s.r' % xform, *jo, type='double3')


    if nodeType == 'joint':
        #in the case of a world matrix, we need to explicitly store
        #euler rotation and orient values, since setting the matrix with the
        #xform command resets joint orientation to 0

        if kwargs.get('jointOrient', None):
            MC.setAttr('%s.jointOrient' % xform, *kwargs['jointOrient'], type='double3')

        if kwargs.get('rotation', None):
            MC.setAttr('%s.r' % xform, *kwargs['rotation'], type='double3')
        if kwargs.get('radius', None):
            MC.setAttr('%s.radius' % xform, kwargs['radius'])


    #build the control handle
    if kwargs.get('controlArgs', None):
        _logger.debug("controlArgs: %r" %  kwargs['controlArgs'])
        makeControl(xform, xformType=kwargs['nodeType'], **kwargs['controlArgs'])

    setStorableXformAttrs(xform, **kwargs)
    return xform


def isStorableXform(xform):
    """
    Is the node tagged as a storableXform node?
    """
    if nodeTag.hasTag(xform, STORABLE_TAG_NAME):
        return True
    return False

def getStorableXformInfo(xform):
    """
    Get information needed to record the state of a transform node to rebuild
    it, duplicate it, etc
    """

    if not nodeTag.hasTag(xform, STORABLE_TAG_NAME):
        raise RuntimeError("%s is not a storable node" % xform)

    recordableTag = nodeTag.getTag(xform, STORABLE_TAG_NAME)
    result = {}
    result.update(recordableTag)

    result['nodeType'] = MC.objectType(xform)

    worldSpace = result['worldSpace']
    result['matrix'] = MC.xform(xform, q=1, m=1, ws=worldSpace)

    result['rotateOrder'] = MC.getAttr('%s.rotateOrder' % xform)

    if result['nodeType'] == 'joint':
        result['radius'] = MC.getAttr('%s.radius' % (xform))
        result['jointOrient']  = MC.getAttr('%s.jointOrient' % xform)[0]
        result['rotation'] = MC.getAttr('%s.r' % xform)[0]

    par = MC.listRelatives(xform, parent=1, pa=1)
    if par:
        par = par[0]

    result['parent'] = par

    #get control info
    if isControl(xform):
        result['controlArgs'] = getInfo(xform)
        _logger.debug('controlArgsType: %s' % str(type(result['controlArgs'])))
    return result


def getStorableXforms(inNodeList=None, categories=None):
    """Return all nodes in the scene from the category"""
    result = nodeTag.getNodesWithTag(STORABLE_TAG_NAME)
    if inNodeList is not None:
        result = list(set(inNodeList).intersection(result))

    if categories:
        assert isinstance(categories, list)
        categories=set(categories)

        tmp = result
        result = []

        for node in tmp:
            nodeCategories = nodeTag.getTag(node, STORABLE_TAG_NAME)['categories']
            if set(nodeCategories).intersection(categories):
                result.append(node)

    return result

def getStorableXformRebuildData(inNodeList = None, categories=None):
    """
    Get a single dictionary that can be used to reconstruct nodes.  By
    default, this uses all storable xforms in the scene file

    @param inNodeList: narrow by storable xforms in this list
    @param inNodeList: list of strings
    @param categories: narrow by storable xforms with one of the categories
    @type categories: list of strings

    @return: ordered dict of nodes with data
    """
    result = {}
    for node in getStorableXforms(inNodeList=inNodeList, categories=categories):
        result[node] = getStorableXformInfo(node)
    return result

def substituteInData(xformData, *args):
    """
    find all instances of the find string and replace with the replaceWith string
    @param xformData: an xform data dictionary
    @param *args: tuples of (find, replace) regexes
    @return: new data dict

    >>> substituteInData(data, ("^defaultchar_", "newchar_"))
    """
    result = {}
    for k, v in xformData.iteritems():
        v = copy.deepcopy(v)
        for find, replace in args:
            k = re.sub(find, replace, k)
            if v['parent']:
                v['parent'] = re.sub(find, replace, v['parent'])
        result[k] = v
    return result

def _allParents(node):
    result = []
    parts = [x for x in MC.ls(node, l=1)[0].split('|') if x]
    for i in reversed(range(len(parts))):
        if i == 0:
            break
        result.append(MC.ls('|'.join(parts[:i]))[0])
    return result

def _sortNodesTopDown(nodeList):
    """
    sort the nodes in the list in order of highest in the hierarchy
    to lowest
    """
    nodeRanks = {}
    for node in nodeList:
        nodeRanks[node] = 0

    #the lowest nodes in the hierarchy have the largest ranks
    for node in nodeList:
        for parent in _allParents(node):
            if parent in nodeList:
                nodeRanks[node] += 1

    i = 0
    result = []

    numNodes = len(nodeRanks)
    numFound = 0
    while numNodes > numFound:
        for node, rank in nodeRanks.iteritems():
            if rank == i:
                result.append(node)
                numFound += 1
        i += 1


    return result

def makeStorableXformsFromData(xformData, sub=None, skipParenting=False):
    """
    Rebuild xforms from the data gotten from getStorableXformRebuildData
    @param xformData: data in the form {nodeName: infoDict}
    @type xformData: dict
    @param sub: a 2-item substitution pattern tuple, in the form (search, replacewith)
    @type sub: iterable of two strings

    @return a list of xforms created.
    """
    if sub:
        tmp = xformData
        xformData = {}
        for k, v in tmp.iteritems():
            k = re.sub(sub[0], sub[1], k)
            v = copy.deepcopy(v)
            v['parent'] = re.sub(sub[0], sub[1], v['parent'])
            xformData[k] = v

    xformDataCopy = copy.deepcopy(xformData)
    secondPassCopy = copy.deepcopy(xformData)
    #make all the nodes first so they can be parented
    for name, data in xformDataCopy.iteritems():
        data.pop('parent', None)
        data.pop('jointOrient', None)
        data.pop('rotation', None)
        makeStorableXform(name, **data)

    #apply matrices from top to bottom

    for node in _sortNodesTopDown(secondPassCopy.keys()):
        data = secondPassCopy[node]
        data.pop('matrix')
        makeStorableXform(node,  **data)

    return xformData.keys()


def centeredCtl(startJoint, endJoint, ctl, centerDown='posY'):
    """
    Setup a control to be 'centered' down a bone.
    @param startJoint: the joint the control should start at
    @param endJoint: the joint the control should end at
    @param ctl: the control node
    @param centerDown: the control axis to stretch to center the node
    """

    o = utils.Orientation()
    o.setAxis('aim', centerDown)

    pm.pointConstraint(startJoint, endJoint, ctl)
    pm.aimConstraint(endJoint, ctl,
                     aim=o.getAxis('aim'),
                     upVector=o.getAxis('up'),
                     wu=o.getAxis('up'), worldUpType='objectRotation',
                     worldUpObject=startJoint)

    #set up network to measure the distance

    mdn = MC.createNode('multiplyDivide', n='%s_centeredctl_mdn' % ctl)
    MC.select(cl=1)
    dd = MC.createNode('distanceBetween', n='%s_center_dd' % ctl)
    MC.connectAttr('%s.worldMatrix' % startJoint, "%s.im1" % dd)
    MC.connectAttr('%s.worldMatrix' % endJoint, "%s.im2" % dd)

    MC.connectAttr('%s.distance' % dd, '%s.input1X' % mdn)

    #find the amount we need to scale by. Ctls are built to a scale of 1
    #unit by default.  We need to scale by half the distance * multiplier to scale ctl
    #back to 1
    scale = getInfo(ctl)['s']
    scale = scale[utils.indexFromVector(o.getAxis('aim'))]
    scale = (1.0/scale)/2.0
    MC.setAttr("%s.input2X" % mdn, scale)

    scaleAttr = 'scale%s' % o.getAxis('aim', asString=True)[3]
    MC.connectAttr("%s.outputX" % mdn,
                   "%s.%s" % (ctl, scaleAttr))


def setupFkCtls(bndJnts, rigCtls, descriptions, namer):
    """Set up fk controls from bndJnts.

    This will delete the original controls passed in and
    rebuild the control shapes on a duplicate of the bind joints passed in
    Zero nodes will be placed above the controls, so the control matrices will
    equal identiy

    @param bndJnts: the joints to duplicate as fk controls
    @param rigCtls: the controls that will be deleted and have their shapes reparented
    @param descriptions: names for the new controls

    @param namer: a Namer object used to rename the new joints (const)

    @return: list of new joint controls
    """

    if len(bndJnts) != len(rigCtls):
        raise RuntimeError("bind joint length must match rig ctls")
    if len(bndJnts) != len(descriptions):
        raise RuntimeError("bind joint length must match rig descriptions")

    fkCtls = []
    rebuildData = getStorableXformRebuildData(inNodeList = bndJnts)

    substitutions = []
    for i in range(len(rigCtls)):
        #get the position offsets for the new control data
        setEditable(rigCtls[i], True)
        editor = getEditor(rigCtls[i])
        MC.parent(editor, world=1)
        utils.snap(bndJnts[i], rigCtls[i])
        MC.parent(editor, rigCtls[i])
        ctlInfo = getInfo(rigCtls[i])
        rebuildData[bndJnts[i]]['controlArgs'] = ctlInfo

        #get name substituions for the new joints
        newName = namer(descriptions[i], r='fk')
        substitutions.append((bndJnts[i], newName))

        fkCtls.append(newName)

    MC.delete(rigCtls)
    rebuildData = substituteInData(rebuildData, *substitutions)
    makeStorableXformsFromData(rebuildData)

    for ctl in fkCtls:

        att = utils.insertNodeAbove(ctl)
        for node in [ctl, att]:
            MC.setAttr('%s.drawStyle' % node, 2)
    return fkCtls
