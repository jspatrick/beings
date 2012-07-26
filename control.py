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
import maya.mel as MM
import maya.cmds as MC

import utils
reload(utils)
logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

_handleData = {'scale': [1,1,1],
               'rot': [0,0,0],
               'pos': [0,0,0],
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

# def _modHandleData(xform, **kwargs):

#     nodeData = eval(pm.getAttr('%s.%s' % (xform, INFO_ATTR)))
#     return _argHandleData(handleData=nodeData, **kwargs)

def _getLibDir():
    return os.path.join(os.path.dirname(__file__), 'control_lib')

def _getControlPath(controlName):
    return os.path.join(_getLibDir(),
                        '%s.ma' % controlName)
def listControls():
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

INFO_ATTR = 'beingsControlInfo'

def getInfo(control, includeEdits=True):
    info =  eval(MC.getAttr('%s.%s' % (control, INFO_ATTR)))
    editor = getEditor(control)
    if includeEdits and editor:
        info['pos'] = list(MC.getAttr('%s.t' % editor)[0])
        info['rot'] = list(MC.getAttr('%s.r' % editor)[0])
        info['scale'] = list(MC.getAttr('%s.s' % editor)[0])
    return info

def setInfo(control, info):
    control = str(control)
    if not MC.attributeQuery(INFO_ATTR, n=control, ex=1):
        MC.addAttr(control, ln=INFO_ATTR, dt='string')
    if isinstance(info, dict):
        info = repr(info)
    MC.setAttr('%s.%s' % (control, INFO_ATTR), info, type='string')

def makeControl(name, xformType=None, **kwargs):
    """
    Create a control object
    @param name: the control name
    @param xformType: if creating a new xform, use this node type.  Defaults
    to transform
    @keyword pos: offset the position of the handle shape.
    @keyword rot: offset the rotation of the handle shape.

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
    MC.xform(tmpXform, t=handleData['pos'], r=1, os=1)
    MC.xform(tmpXform, ro=handleData['rot'], r=1)
    MC.xform(tmpXform, scale=(handleData['scale']))

    utils.parentShape(xform, tmpXform)
    if handleData.get('type') != 'surface':
        _setColor(xform, handleData['color'])

    #set the handle info
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
        MC.setAttr('%s.t' % editor, *info['pos'], type='double3')
        MC.setAttr('%s.r' % editor, *info['rot'], type='double3')
        MC.setAttr('%s.s' % editor, *info['scale'], type='double3')

        utils.parentShape(editor, ctl, deleteChildXform=False)

    else:
        setInfo(ctl, info)
        utils.parentShape(ctl, editor, deleteChildXform=True)
    return True


def snapKeepShape(target, ctl, scaleTo1=True, **kwargs):
    """Snap the xform but retain the shape
    @param scaleTo1=True - scale the xform to 1 before snapping"""
    shapes = getShapeNodes(ctl)
    tmpXform = pm.createNode('transform', n='TMP')
    utils.parentShape(tmpXform, ctl, deleteChildXform=False)
    if scaleTo1:
        ctl.scale.set([1,1,1])
    utils.snap(target, ctl, **kwargs)
    utils.parentShape(ctl, tmpXform)


def centeredCtl(startJoint, endJoint, ctl, centerDown='posY'):
    zero = utils.insertNodeAbove(ctl)
    o = utils.Orientation()
    o.setAxis('aim', centerDown)

    pm.pointConstraint(startJoint, endJoint, zero)
    pm.aimConstraint(endJoint, zero,
                     aim=o.getAxis('aim'),
                     upVector=o.getAxis('up'),
                     wu=o.getAxis('up'), worldUpType='objectRotation',
                     worldUpObject=startJoint)
    pm.pointConstraint(startJoint, endJoint, zero)

    #set up network to measure the distance

    mdn = pm.createNode('multiplyDivide')
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
    scale = getInfo(ctl)['scale']
    scale = scale[utils.indexFromVector(o.getAxis('aim'))]
    scale = (1.0/scale)/2.0
    mdn.input2X.set(scale)

    scaleAttr = o.getAttr(zero, 'aim', type='scale')
    mdn.outputX.connect(scaleAttr)


def _getStateDct(node):
    """ Get a dict representing the state of the node """
    node = pm.PyNode(node)
    result = {}
    if node.hasAttr( INFO_ATTR):
        ctlDct = eval(pm.getAttr('%s.%s' % (node, INFO_ATTR)))
        result.update(ctlDct)

    result['localMatrix'] = pm.xform(node, q=1, m=1)
    result['worldMatrix'] = pm.xform(node, q=1, m=1, ws=1)
    result['parentMatrix'] = utils.toList(node.parentMatrix.get())
    return result


def getRebuildData(ctlDct):
    """
    Get data to rebuild all controls in the differ in worldSpace
    @param ctlDct: dict of {ctlName: ctlNode}
    """
    result = {}
    for ctlName, ctl in ctlDct.items():
        result[ctlName] = _getStateDct(ctl)
        result[ctlName]['nodeName'] = ctl.nodeName()
        result[ctlName]['nodeType'] = pm.objectType(ctl)
    return result


def buildCtlsFromData(ctlData, prefix='', flushScale=True, flushLocalXforms=False):
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


class Differ(object):
    """
    Get and set control differences
    """    
    def __init__(self):
        self.__controls = {}
        self.__initialState = {}
        self.__wasSetup = False

    def getObjs(self):
        result = {}
        for ctlName, ctlTup in self.__controls.items():
            result[ctlName] = ctlTup[0]
        return result

    def getRebuildData(self):
        """
        Get data to completely rebuild controls
        """

        result = {}
        for ctlName, ctl in self.getObjs().items():
            result[ctlName] = _getStateDct(ctl)
            result[ctlName]['nodeName'] = ctl.nodeName()
            result[ctlName]['nodeType'] = pm.objectType(ctl)

        return result


    def addObj(self, name, ctl, ignore=[], skip=[]):
        return self.addObjs({name:ctl}, ignore=ignore, skip=skip)

    def addObjs(self, objDct, ignore=[], skip=[]):
        """
        Add Control objects to the differ.
        @param objDct:  a dict of {objectKey: object}
        @param ignore=[]: when diffs are retrieved, if the only diffs
            are from items in this list, the diff will not be added to the
            returned dict.  They are not excluded, however, if other diffs
            are also found
        @param skip=[]:  when diffs are retrieved, ignore any differences found
            in the list
        """
        for key, obj in objDct.items():
            if not obj.hasAttr(INFO_ATTR):
                _logger.warning("%s is not a control; skipping" % obj)
                continue
            if self._nameCheck(obj):
                self.__controls[key] = (obj, ignore, skip)
            else:
                _logger.warning("%s is already a key in the differ; skipping" % key)

    def _nameCheck(self, key):
        """Short names for the xform nodes in controls"""
        if key in  self.__controls.keys():
            _logger.warning('%s is already a control in the differ' % key)
            return False
        else:
            return True

    def setInitialState(self):
        """
        Set the initial state for all nodes
        """
        self.__initialState = {}
        for k, ctl in self.__controls.items():
            self.__initialState[k] = _getStateDct(ctl[0])
        self.__wasSetup=True

    def getDiffs(self):
        """
        Get diffs for all nodes
        """
        if not self.__wasSetup:
            raise utils.BeingsError("Initial state was never set")
        allDiffs = {}
        for k, ctlTup in self.__controls.items():
            control = ctlTup[0]
            ignoreList = ctlTup[1]
            skipList = ctlTup[2]
            diff = {}
            initialState = self.__initialState[k]
            state = _getStateDct(control)
            for ik in initialState.keys():
                if ik in skipList:
                    continue
                if initialState[ik] != state[ik]:
                    diff[ik] = state[ik]
                if diff and not (set(diff.keys()).issubset(ignoreList)):
                    allDiffs[k] = diff
        return allDiffs

    def applyDiffs(self, diffDct, xformSpace='local'):
        """
        Apply diffs for nodes.
        @param diffDict:  a dictionary of [diffKey: diffs], gotten from getDiffs
        @param xformSpace='local': Apply diffs from this space

        Notes
        -----
        """
        diffDct = copy.deepcopy(diffDct)
        if isinstance(diffDct, basestring):
            diffDct = eval(diffDct)

        for ctlKey, diffs in diffDct.items():
            try:
                ctl = self.__controls[ctlKey][0]
            except ValueError:
                _logger.warning("%s does not exist, skipping" % ctlKey)
                continue

            #apply and discard the matricies from the diff dict
            worldmatrix = diffs.pop('worldMatrix', None)
            localmatrix = diffs.pop('localMatrix', None)
            parentMatrix = diffs.pop('parentMatrix', None)
            #remaining kwargs are shapes, so apply them
            if diffs:
                makeControl(ctl, **diffs)

            if worldmatrix and xformSpace == 'world':
                pm.xform(ctl, m=worldmatrix, ws=1)

            if localmatrix and xformSpace == 'local':
                pm.xform(ctl, m=localmatrix)
