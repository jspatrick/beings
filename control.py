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

import logging, sys, copy, json, os
import pymel.core as pm
import maya.mel as MM
import maya.cmds as MC

import utils
reload(utils)
import nodeTag

logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

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

def getShapeNodes(xform):
    """
    Return a list of shapes
    """

    nodes = MC.listRelatives(xform, shapes=1, pa=1)
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

def isControl(xform):
    if nodeTag.hasTag(xform, CONTROL_TAG_NAME):
        return True

def makeControl(name, xformType=None, **kwargs):
    """
    Create a control object
    @param name: the control name
    @param xformType: if creating a new xform, use this node type.  Defaults
    to transform
    @keyword t: offset the position of the handle shape.
    @keyword r:: offset the rotation of the handle shape.

    @note: offsets are applied in the control xform's local space
    @raise RuntimeError: if the control exists, and xformType is supplied but does
    not match the current node's xform type
    """

    #see if the object exists, and create it if not
    if MC.objExists(name):
        if xformType and xformType != MC.objectType(name):
            raise RuntimeError('control exists and is not of type %s' % xformType)

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
    MC.xform(tmpXform, t=handleData['t'], r=1, os=1)
    MC.xform(tmpXform, ro=handleData['r'], r=1)
    MC.xform(tmpXform, scale=(handleData['s']))

    utils.parentShape(xform, tmpXform)
    if handleData.get('type') != 'surface':
        _setColor(xform, handleData['color'])

    #set the handle info
    _logger.debug("handle data: %r" % handleData)
    setInfo(xform, handleData)

    return xform


def getEditor(ctl):
    editor = '%s_editor' % ctl
    if MC.objExists(editor):
        return editor
    return None


def setEditable(ctl, state):
    """
    Add a new xform to a control
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

        utils.parentShape(editor, ctl, deleteChildXform=False)

    else:
        setInfo(ctl, info)
        utils.parentShape(ctl, editor, deleteChildXform=True)
    return True

STORABLE_TAG_NAME = 'recordableXform'


_defaultXformKwargs = {'matrix': [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
                       'rotateOrder': 0,
                       'parent': None,
                       'worldSpace': False,
                       'jointOrient': (0,0,0),
                       'radius': .25,
                       'nodeType': 'transform',
                       'categories': (),
                       'controlArgs': None}


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
    @keyword createNodeOnly: only create the node; do not appy a matrix, parent,
    etc
    @keyword skipParenting: do not parent

    @keyword worldSpace: apply matrix in worldSpace
    @keyword matrix: apply this matrix to the node
    @keyword parent: parent the node under this xform"""
    for k, v in _defaultXformKwargs.items():
        kwargs[k] = kwargs.get(k, v)

    if MC.objExists(xform):
        if MC.nodeType(xform) != kwargs['nodeType']:
            _logger.warning("Cannot change type of existing node '%s'" % xform)
    else:
        if kwargs['nodeType'] not in ['transform', 'joint']:
            raise RuntimeError('invalid node type "%s"' % str(kwargs['nodeType']))

        xform = MC.createNode(kwargs['nodeType'], name=xform)

    if kwargs.get('createNodeOnly', False):
        return xform

    parent = kwargs.get('parent', None)
    skipParenting = kwargs.get('skipParenting', None)

    if skipParenting:
        if not kwargs['worldSpace'] and parent:
            _logger.debug("Skipping parenting - local matrix may apply incorrectly")

    elif parent and MC.objExists(parent):
        if parent in (MC.listRelatives(xform, parent=1) or []):
            _logger.debug("Skipping parenting - already parented")
        else:
            MC.parent(xform, parent)
            if kwargs['nodeType'] == 'joint':
                utils.fixInverseScale([xform])



    if kwargs['nodeType'] == 'joint':
        MC.setAttr('%s.jointOrient' % xform, *kwargs['jointOrient'], type='double3')
        MC.setAttr('%s.radius' % xform, kwargs['radius'])

    MC.setAttr('%s.rotateOrder' % xform, kwargs['rotateOrder'])
    MC.xform(xform,
             m=kwargs['matrix'],
             ws=kwargs['worldSpace'])


    if kwargs['controlArgs']:
        _logger.debug("controlArgs: %r" %  kwargs['controlArgs'])
        makeControl(xform, **kwargs['controlArgs'])

    setStorableXformAttrs(xform, **kwargs)
    return xform

def isStorableXform(xform):
    if nodeTag.hasTag(xform, STORABLE_TAG_NAME):
        return True
    return False

def getStorableXformInfo(xform):
    if not nodeTag.hasTag(xform, STORABLE_TAG_NAME):
        raise RuntimeError("%s is not a storable node" % xform)

    recordableTag = nodeTag.getTag(xform, STORABLE_TAG_NAME)
    result = copy.copy(_defaultXformKwargs)
    result.update(recordableTag)

    result['nodeType'] = MC.objectType(xform)

    worldSpace = result['worldSpace']
    result['matrix'] = MC.xform(xform, q=1, m=1, ws=worldSpace)

    result['rotateOrder'] = MC.getAttr('%s.rotateOrder' % xform)

    if result['nodeType'] == 'joint':
        result['radius'] = MC.getAttr('%s.radius' % (xform))
        result['jointOrient']  = MC.getAttr('%s.jointOrient' % xform)[0]

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
    """
    result = {}
    for node in getStorableXforms(inNodeList=inNodeList, categories=categories):
        result[node] = getStorableXformInfo(node)
    return result

def makeStorableXformsFromData(xformData):
    """
    Rebuild xforms from the data gotten from getStorableXformRebuildData
    """
    #make all the nodes first so they can be parented
    for name, data in xformData.iteritems():
        makeStorableXform(name, createNodeOnly=True, **data)

    for name, data in xformData.iteritems():
        makeStorableXform(name, **data)


def centeredCtl(startJoint, endJoint, ctl, centerDown='posY'):
    makeEditable(ctl)
    zero = utils.insertNodeAbove(ctl)
    makeStorableXform(zero)

    o = utils.Orientation()
    o.setAxis('aim', centerDown)

    pm.pointConstraint(startJoint, endJoint, zero)
    pm.aimConstraint(endJoint, zero,
                     aim=o.getAxis('aim'),
                     upVector=o.getAxis('up'),
                     wu=o.getAxis('up'), worldUpType='objectRotation',
                     worldUpObject=startJoint)

    #set up network to measure the distance

    mdn = pm.createNode('multiplyDivide', n='%s_centeredctl_mdn' % ctl)
    dd = pm.distanceDimension(startPoint=[0,0,0], endPoint=[5,5,5])
    startLoc = dd.startPoint.listConnections()[0]
    endLoc = dd.endPoint.listConnections()[0]
    startLoc.v.set(0)
    endLoc.v.set(0)
    pm.pointConstraint(startJoint, startLoc)
    pm.pointConstraint(endJoint, endLoc)
    dd.distance.connect(mdn.input1X)
    dd.getParent().v.set(0)
    #find the amount we need to scale by. Ctls are built to a scale of 1
    #unit by default.  We need to scale by half the distance * multiplier to scale ctl
    #back to 1
    scale = getInfo(ctl)['s']
    scale = scale[utils.indexFromVector(o.getAxis('aim'))]
    scale = (1.0/scale)/2.0
    mdn.input2X.set(scale)

    scaleAttr = o.getAttr(zero, 'aim', type='scale')
    mdn.outputX.connect(scaleAttr)


def _buildCtlsFromData(ctlData, prefix='', flushScale=True, flushLocalXforms=False):
    """
    Rebuild controls in world space
    @param prefix=None: apply this prefix to node names of controls
    """
    ctlData = copy.deepcopy(ctlData)
    result = {}

    for ctlName, data in ctlData.items():

        #gather data
        origNodeName = '%s%s' % (prefix, data.pop('nodeName'))
        nodeType = data.pop('nodeType')
        worldMatrix = data.pop('worldMatrix')
        localMatrix = data.pop('localMatrix')
        parentMatrix = data.pop('parentMatrix')

        #set the name of the new ctl node
        i = 1
        nodeName = origNodeName
        while pm.objExists(nodeName):
            nodeName = '%s%i' % (origNodeName, i)
            i += 1
        if nodeName != origNodeName:
            _logger.warning("Warning - %s exists.  Setting name to %s" % \
                            (origNodeName, nodeName))

        ctl = makeControl(xformType = nodeType, name=nodeName, **data)
        pm.xform(ctl, m=worldMatrix, ws=True)

        #flush the scale down to the shape level
        if flushScale:
            xfScale = ctl.scale.get()
            shapeScale = eval(ctl.beingsControlInfo.get())['scale']
            for i in range(3):
                shapeScale[i] = shapeScale[i] * xfScale[i]
            ctl.scale.set([1,1,1])
            makeControl(xform=ctl, scale=shapeScale)


        if flushLocalXforms:
            tmp = pm.createNode('transform', n='SNAP_TMP')
            pm.xform(tmp, m=parentMatrix, ws=True)
            snapKeepShape(tmp, ctl)
            pm.delete(tmp)
        result[ctlName] = ctl

    return result


def setupFkCtls(bndJnts, oldFkCtls, fkToks, namer):
    """Set up fk controls from bndJnts.

    This will delete the original controls that were passed
    in and rebuild the control shapes on a duplicate of the bind joints
    @return: dict of {tok:ctl}
    """
    if len(bndJnts) != len(oldFkCtls) or len(bndJnts) != len(fkToks):
        _logger.warning("bind joint length must match rig ctls")

    newFkCtls = utils.duplicateHierarchy(bndJnts, toReplace='_bnd_', replaceWith='_fk_')
    for i in range(len(newFkCtls)):
        newCtl = newFkCtls[i]
        oldCtl = oldFkCtls[i]
        info = getInfo(oldCtl)
        setInfo(newCtl, getInfo(oldCtl))
        utils.parentShape(newCtl, oldCtl)
        newCtl.rename(namer(fkToks[i], r='fk'))
        if newCtl.overrideDisplayType.get():
            newCtl.overrideDisplayType.set(0)

    with utils.SilencePymelLogger():
        for ctl in oldFkCtls:
            if ctl.exists():
                pm.delete(ctl)

    return newFkCtls

