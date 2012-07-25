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

def _modHandleData(xform, **kwargs):

    nodeData = eval(pm.getAttr('%s.%s' % (xform, INFO_ATTR)))
    return _argHandleData(handleData=nodeData, **kwargs)

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

def getInfo(control):
    return eval(pm.getAttr('%s.%s' % (control, INFO_ATTR)))

def setInfo(control, info):
    control = str(control)
    if not MC.attributeQuery(INFO_ATTR, n=control, ex=1):
        MC.addAttr(control, ln=INFO_ATTR, dt='string')
    if type(info) == dict:
        info = repr(info)
    MC.setAttr('%s.%s' % (control, INFO_ATTR), info, type='string')

def isControl(name): pass
def setControlProperties(name, **kwargs): pass
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

        MC.createNode(xformType, name=name, parent=None)

    #delete any shapes that exist
    for shape in xform.listRelatives(type='geometryShape'):
        pm.delete(shape)

    tmpXform = pm.createNode('transform', n='TMP')

    #create an attribute to store handle info

    if not xform.hasAttr(INFO_ATTR):
        xform.addAttr(INFO_ATTR, dt='string')
        handleData = _argHandleData(**kwargs)
    else:
        handleData = _modHandleData(xform, **kwargs)

    pm.setAttr('%s.%s' % (xform, INFO_ATTR), repr(handleData))

    #get the shape function
    shapeFunc = getattr(sys.modules[__name__],
                        'makeShape_%s' % (handleData['shape']))

    #create the shape according to the handleData
    with utils.NodeTracker() as nt:
        shapeFunc()

        shapes = [n for n in nt.getObjects(asPyNodes=True) if \
                  isinstance(n, pm.nt.GeometryShape) and n.exists()]
        xforms = [n for n in nt.getObjects(asPyNodes=True) if \
                  isinstance(n, pm.nt.Transform) and n.exists()]

        _logger.debug('Shapes: %s' % shapes)
        _logger.debug('Xforms: %s' % xforms)

    for i, shapeNode in enumerate(shapes):
        shapeNode.rename("%sShape" % (xform.name()))

    #snap the tmp shape to the xform
    utils.parentShapes(tmpXform, xforms)

    bbScale(tmpXform)
    utils.snap(xform, tmpXform, scale=True)

    #apply transformations
    pm.xform(tmpXform, ro=handleData['rot'], r=1)
    pm.xform(tmpXform, t=handleData['pos'], r=1, os=1)
    tmpXform.s.set(handleData['scale'])

    if handleData.get('type') == 'surface':
        tmp = utils.strokePath(tmpXform, radius=.1)
        pm.delete(tmpXform)
        tmpXform = tmp

    utils.parentShape(xform, tmpXform)
    if handleData.get('type') != 'surface':
        _setColor(xform, handleData['color'])
    return xform

def bbCenter(shape, freeze=True):
    """
    Center the shape's bounding box
    """
    bb = shape.getBoundingBox()
    mvX = (bb[1][0] + bb[0][0]) / -2.0
    mvY = (bb[1][1] + bb[0][1]) / -2.0
    mvZ = (bb[1][2] + bb[0][2]) / -2.0
    utils.moveShapePos(shape, vector=[mvX, mvY, mvZ])
    if freeze:
        pm.makeIdentity(shape, apply=True, r=0, s=0, t=1, n=0)

def bbScale(shape, freeze=True):
    """
    Scale the obj to a bounding box with a scale of 1
    """
    bb = shape.getBoundingBox()
    #get the longest side:
    sides = [bb[1][0] - bb[0][0],
             bb[1][1] - bb[0][1],
             bb[1][2] - bb[0][2]]

    sclAmt = 2.0 / max(sides)
    pm.scale(shape, [sclAmt, sclAmt, sclAmt], r=True)
    if freeze:
        pm.makeIdentity(shape, apply=True, r=0, s=1, t=0, n=0)

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




#####################################################
## curve shapes
####################################################

def makeShape_cube():

    """A Cube Curve"""
    crv = pm.curve(d=1, p=[(-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5),
                           (-0.5, -0.5, 0.5), (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5),
                           (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (0.5, -0.5, -0.5), (-0.5, -0.5, -0.5),
                           (-0.5, 0.5, -0.5)],
                            k=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])


def makeShape_sphere():

    c1 = pm.circle(nr=[1, 0, 0], sw=360, r=1, d=3, s=12)[0]
    c2 = pm.circle(nr=[0, 1, 0], sw=360, r=1, d=3, s=12)[0]
    c3 = pm.circle(nr=[0, 0, 1], sw=360, r=1, d=3, s=12)[0]


def makeShape_fatCross():

    pm.curve(d=1,
            p=[(1, 0, -1), (2, 0, -1), (2, 0, 1), (1, 0, 1), (1, 0, 2), (-1, 0, 2), (-1, 0, 1),
               (-2, 0, 1), (-2, 0, -1), (-1, 0, -1), (-1, 0, -2), (1, 0, -2), (1, 0, -1)],
               k=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

def makeShape_diamond():
    pm.curve(d=1,
            p=[(0, 0, -2.5), (0, 0, 2.5), (-2.5, 0, 0), (0, 2.5, 0), (2.5, 0, 0), (0, -2.5, 0), (0, 0, -2.5),
              (2.5, 0, 0), (0, 0, 2.5), (0, 2.5, 0), (0, 0, -2.5), (-2.5, 0, 0), (0, -2.5, 0), (0, 0, 2.5), ],
              k=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],)


def makeShape_doublePin():
    crv = pm.curve(p=[(0, 1.375001, 0), (-0.250001, 1.625001, 0), (0, 1.875, 0), (0.25, 1.625001, 0),
                      (0, 1.375001, 0), (0, -1.374999, 0), (-0.25, -1.625, 0), (0, -1.875, 0), (0.250001, -1.625, 0), (0, -1.374999, 0)],
                   k=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], d=1)
    crv.rx.set(90)
    return crv

def makeShape_lightbulb():
    """A lightbulb curve"""

    crv = pm.curve(p=[(-0.139471, -0.798108, 0), (-0.139471, -0.798108, 0), (-0.139471, -0.798108, 0), (-0.299681, -0.672294, 0),
                      (-0.299681, -0.672294, 0), (-0.299681, -0.672294, 0), (-0.121956, -0.578864, 0), (-0.121956, -0.578864, 0), (-0.121956, -0.578864, 0),
                      (-0.285304, -0.51952, 0), (-0.285304, -0.51952, 0), (-0.0744873, -0.442806, 0), (-0.0744873, -0.442806, 0), (-0.287769, -0.373086, 0),
                      (-0.287769, -0.373086, 0), (-0.100386, -0.296549, 0), (-0.100386, -0.296549, 0), (-0.264344, -0.205725, 0), (-0.264344, -0.205725, 0),
                      (-0.262544, -0.0993145, 0), (-0.262544, -0.0993145, 0), (-0.167051, -0.0613459, 0), (-0.167051, -0.0613459, 0),
                      (-0.167051, -0.0613459, 0), (-0.166024, 0.0163458, 0), (-0.157394, 0.232092, 0), (-0.367902, 0.680843, 0), (-0.96336, 1.224522, 0),
                      (-1.006509, 1.992577, 0), (-0.316123, 2.613925, 0), (0.561786, 2.548479, 0), (1.094888, 2.001207, 0), (1.051638, 1.166965, 0),
                      (0.436419, 0.66543, 0), (0.13283, 0.232092, 0), (0.15009, 0.0163458, 0), (0.15073, -0.046628, 0), (0.15073, -0.046628, 0),
                      (0.270326, -0.0955798, 0), (0.270326, -0.0955798, 0), (0.267815, -0.208156, 0), (0.267815, -0.208156, 0), (0.0884224, -0.291145, 0),
                      (0.0884224, -0.291145, 0), (0.292477, -0.366091, 0), (0.292477, -0.366091, 0), (0.0946189, -0.439723, 0), (0.0946189, -0.439723, 0),
                      (0.306664, -0.508968, 0), (0.306664, -0.508968, 0), (0.112488, -0.57513, 0), (0.112488, -0.57513, 0), (0.323789, -0.674644, 0),
                      (0.323789, -0.674644, 0), (0.152097, -0.794645, 0), (0.152097, -0.794645, 0), (0.152097, -0.794645, 0), (0.106716, -0.907397, 0),
                      (0.0103741, -1.003739, 0), (-0.0919896, -0.907397, 0), (-0.139471, -0.798108, 0), (-0.139471, -0.798108, 0)],
                   k=[0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
                      32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 59, 59], d=3)
    crv.rx.set(-90)
    return crv

def makeShape_hand():


    crv = pm.curve(p=[(0, 0.2, 0.3), (0, 0, 0.2), (0, 0, -0.2), (0, 0.2, -0.3), (0, 0.498495, -0.496524),
                      (0, 0.580389, -0.361639), (0, 0.36361, -0.207485), (0, 0.599659, -0.173764),
                      (0, 1.023583, -0.168946), (0, 1.139199, 0.028564), (0, 0.927237, 0.370594), (0, 0.5, 0.3),
                      (0, 0.2, 0.3)], k=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], d=1)
    return crv

def makeShape_arrow():

    crv = pm.curve(p=[(-0.671879, 1.840622, 1), (-0.671879, 1.840622, 3), (-0.671879, 1.840622, 3),
                      (-1.582662, 2.55714, 1.178396), (-2.371522, 2.815571, 0), (-2.371522, 2.815571, 0),
                      (-1.560737, 2.546095, -1.129296), (-0.671879, 1.840622, -3), (-0.671879, 1.840622, -3),
                      (-0.671879, 1.840622, -1), (-0.671879, 1.840622, -1), (0, 0, -1),
                      (-0.671879, -1.840622, -1), (-0.671879, -1.840622, -1), (-0.671879, -1.840622, -3),
                      (-0.671879, -1.840622, -3), (-1.495543, -2.511834, -1.301146), (-2.371522, -2.815571, 0),
                      (-2.371522, -2.815571, 0), (-1.474011, -2.500042, 1.399345), (-0.671879, -1.840622, 3),
                      (-0.671879, -1.840622, 3), (-0.671879, -1.840622, 1), (-0.671879, -1.840622, 1), (0, 0, 1),
                      (-0.671879, 1.840622, 1)],
                   k=[0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 23, 23], d=3)
    crv.rx.set(90)
    crv.rz.set(-90)
    return crv

def makeShape_text(text="text", font="Arial_Bold"):

    """Make a cuve from text.

    kwargs:
    text:  the text of the curve ("text")
    font:  the font of the text  ("Arial_Bold")
    """
    try:
        txtPrnt = pm.PyNode(pm.textCurves(text=text, font=font, ch=0)[0])
    #on my linux system, there are only super-basic fonts installed.
    except RuntimeError:
        txtPrnt = pm.PyNode(pm.textCurves(text=text, font="Courier", ch=0)[0])
    txtParts = []
    for txtGrp in txtPrnt.getChildren():
        for txt in txtGrp.getChildren():
            txtParts.append(txt)
            txtParts[-1].setParent(world=True)

    pm.delete(txtPrnt)
    txt = utils.parentShapes(txtParts[0], txtParts[1:])
    txt.rx.set(-90)
    return txt


def makeShape_square():
    crv = pm.curve(p=[(1, 0, 1), (-1, 0, 1), (-1, 0, -1), (1, 0, -1), (1, 0, 1)], k=[0, 1, 2, 3, 4], d=1)
    return crv

def makeShape_circle():
    return pm.circle(nr=[0, 1, 0], sw=360, d=3, s=12)[0]
def makeShape_triangle():
    return MM.eval('curve -d 1 -p 0 0 1 -p -0.866 0 -0.5 -p 0.866 0 -.5 -p 0 0 1  -k 0 -k 1 -k 2 -k 3 ;')

def makeShape_cross():
    crv = pm.PyNode(MM.eval('curve -d 1 -p -1 0 -5 -p 1 0 -5 -p 1 0 -1 -p 5 0 -1 -p 5 0 1 -p 1 0 1 -p 1 0 5 -p -1 0 5 -p -1 0 1 -p -5 0 1 -p -5 0 -1 -p -1 0 -1 -p -1 0 -5 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 ;'))

def makeShape_cross3d():
    crv = pm.PyNode(MM.eval('curve -d 1 -p -1 0 -5 -p 1 0 -5 -p 1 0 -1 -p 5 0 -1 -p 5 0 1 -p 1 0 1 -p 1 0 5 -p -1 0 5 -p -1 0 1 -p -5 0 1 -p -5 0 -1 -p -1 0 -1 -p -1 0 -5 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 ;'))
    crv.s.set([0.2,0.2,0.2])
    dup = pm.duplicate(crv)[0]
    dup.rx.set(90)
    dup = pm.duplicate(crv)[0]
    dup.rx.set(90)
    dup.ry.set(90)

def makeShape_jack():
    makeShape_doublePin()
    makeShape_doublePin().ry.set(90)
    makeShape_doublePin().rx.set(0)

def makeShape_layoutGlobals():
    pm.circle(normal=[0,1,0], r=2)
    MM.eval('curve -d 3 -p -1.169488 0 0.463526 -p -0.958738 0 0.971248 -p -0.421459 0 1.196944 -p 0.271129 0 1.255888 -p 0.994735 0 1.004275 -p 1.168226 0 0.417207 -k 0 -k 0 -k 0 -k 1 -k 2 -k 3 -k 3 -k 3 ;')
    crv = MM.eval('curve -d 3 -p 0.81419 0 -1.322437 -p 1.084855 0 -1.105855 -p 1.19143 0 -0.932901 -p 1.321428 0 -0.734364 -k 0 -k 0 -k 0 -k 1 -k 1 -k 1 ;')
    pm.duplicate(crv)[0].sx.set(-1)
    crv = pm.circle(normal=[0,1,0], r=.25, cx=-.77, cz=-.66)[0]
    pm.duplicate(crv)[0].sx.set(-1)


#############################################
## surface shapes
#############################################

def makeShape_orbit_srf():

    torus, tShp = pm.torus(heightRatio=0.05)
    cone1, c1Shp = pm.cone(radius=0.2, axis=[0, 0, 1])
    MM.eval('nurbsPrimitiveCap 1 1 0')
    cone2, c2Shp = pm.cone(radius=0.2, axis=[0, 0, 1])
    MM.eval('nurbsPrimitiveCap 1 1 0')
    cone1.ty.set(1)
    cone2.ty.set(-1)
    cone2.ry.set(180)
    for item in [cone1, cone2, torus]:
        pm.delete(item, ch=True)
    for shp in [tShp, c1Shp, c2Shp]:
        pass
        #pm.disconnectAttr(
    utils.parentShapes(torus, [cone1, cone2])
    torus.rz.set(90)


def makeShape_sphere_srf():

    return pm.sphere()[0]

def makeShape_cube_srf():
    c = pm.nurbsCube()[0]
    cb = pm.group(em=True, world=True)
    utils.parentShapes(cb, c.listRelatives(children=True, pa=True))
    pm.delete(c)
    return cb


def makeShape_arrow_srf(length=2, coneRadius=1, tailRadius=.5):
    cone = pm.cone(ax=[0, 1, 0], r=coneRadius)[0]
    MM.eval('nurbsPrimitiveCap 1 1 0')
    cone.ty.set(length + 1)
    cylinder = pm.cylinder(ax=[0, 1, 0], r=tailRadius, hr=float(length) / float(tailRadius))[0]
    MM.eval('nurbsPrimitiveCap 3 1 1')
    cylinder.ty.set(float(length) / 2)


all_shapes = {}
for fName, f in sys.modules[__name__].__dict__.items():
    if fName.startswith('shape_'):
        tmp, sName, sType = fName.split('_')
        all_shapes[sName.lower() + sType.capitalize()] = f


def getAllShapes():
    """
    Return a dictionary of {'shapeName': ShapeFunc}
    """
    return all_shapes

def layoutGlobalsNode():
    """Create a layout globals node"""
    tmp = pm.ls('being_control')
    if tmp:
        return tmp[0]

    ctl = makeControl(shape='layoutGlobals', xformType='transform', name='being_control', color='salmon')

    for attr in ctl.listAttr(keyable=1):
        try:
            attr.setLocked(True)
            attr.setKeyable(False)
        except:
            pass
    ctl.addAttr('layoutControlVis', at='bool', k=0, dv=1)
    ctl.layoutControlVis.set(cb=1)
    ctl.addAttr('rigControlVis', at='bool', k=0, dv=1)
    ctl.rigControlVis.set(cb=1)
    return ctl
