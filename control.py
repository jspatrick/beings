"""
This whole damn module needs a re-write.  Controls don't need to be class-based, since the handle
data needs to be stored on the node anyways.


Control Properties
==================

  pos: [float, float, float]
  rot: [float, float, float]
  scale: [float, float, float]
  shape: string
  color: string
  scaleToChild: bool
    after creating the shape, scale all nodes from a point at the xform until one reaches
    the first child of that xform

Needs
=====
  - Record the attributes used to initially create the shape
  - Bake offsets from a control's transform to the control properties
  - Change the xform type between joint and transform
  
Implementation
==============
  command info is stored as a json string on an attribute on controls
  
"""

import logging, sys, copy, json
import pymel.core as pm
import maya.mel as mm
import maya.cmds as mc

import beings.utils as utils

logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

_handleData = {'scale': [1,1,1],
               'rot': [0,0,0],
               'pos': [0,0,0],
               'color': 'yellow',
               'shape': 'cube'}

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
    '''
    Return a default handle data dict, modified by any kwards matching keys in _handleData
    '''
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
            _logger.debug('skipping invalid arg "%s" % k') 
    return result

def _modHandleData(xform, **kwargs):
    nodeData = eval(pm.getAttr('%s.%s' % (xform, INFO_ATTR)))
    return _argHandleData(handleData=nodeData, **kwargs)
    
def _shapeNodes(xform):
    """
    Return a list of shapes
    """
    
    nodes = xform.listRelatives(shapes=1)
    return nodes
    # sortedNodes = {}
    # for node in nodes:
    #     i = int(utils.NodeTag(SHAPE_ORDER_TAG, node=node)['order'])
    #     sortedNodes[i] = node
    # sortedKeys = sortedNodes.keys()
    # sortedKeys.sort()
    # return [sortedNodes[i] for i in sortedKeys]

def _setColor(xform, color):
    if color not in COLOR_MAP:
        _logger.warning("invalid color '%s'" % color)
        return
    
    for shape in _shapeNodes(xform):
        shape.overrideEnabled.set(1)
        shape.overrideColor.set(COLOR_MAP[color])

INFO_ATTR = 'beingsControlInfo'
def setControl(xform=None, xformType='transform', name=None, force=False, **kwargs):
    '''
    Create a control object
    @param xform=None:  use this xform instead of creating a new one
    @param xformType='joint': if creating a new xform, use this node type
    @param name=None:  name of the new node
    @param force=False:  if the node is already a control, force it to rebuild with
        default kwargs.  Otherwise, the current shapes info is used to build, and
        kwargs will override the current attrs
    '''
    if not xform:
        if not name:
            #get a generic name; make sure it's unique
            _logger.warning("Creating control with generic name!")
            i=1
            name = 'beings_control%i' % i
            while len(pm.ls(name)):
                i+=1
                name = 'beings_control%i' % i
                
        xform = pm.createNode(xformType, n=name)
    else:
        xformType = pm.nodeType(xform)
        xform = pm.PyNode(xform)
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
        shapes = [n for n in nt.getObjects() if \
                  isinstance(n, pm.nt.GeometryShape) and n.exists()]
        xforms = [n for n in nt.getObjects() if \
                  isinstance(n, pm.nt.Transform) and n.exists()]
        _logger.debug('Shapes: %s' % shapes)
        _logger.debug('Xforms: %s' % xforms)
        
    for i, shapeNode in enumerate(shapes):
        shapeNode.rename("%sShape" % (xform.name()))

    #snap the tmp shape to the xform
    utils.parentShapes(tmpXform, xforms)
    bbScale(tmpXform)
    utils.snap(xform, tmpXform)

    #apply transformations
    pm.xform(tmpXform, ro=handleData['rot'], r=1)
    pm.xform(tmpXform, t=handleData['pos'], r=1, os=1)
    tmpXform.s.set(handleData['scale'])
        
    utils.parentShape(xform, tmpXform)        
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
            
def scaleDownBone(xf, child=None):
    """
    Move and scale a shape so that it starts at the xform pivot and
    ends at the tip.
    """
    children = xf.listRelatives(type='transform')
    
    if child is not None:
        child = pm.PyNode(child)
    else:
        try:
            child = children[0]
        except IndexError:
            _logger.error('no children found to scale to, returning')
            return
    
    if len(children) < 1:
        _logger.warning('multiple children found - scaling to %s' % children[0])
    worldVector = pm.dt.Vector(pm.xform(child, t=1, ws=1, q=1)) - \
                  pm.dt.Vector(pm.xform(xf, t=1, ws=1, q=1))
    wm = xf.worldMatrix.get()
    localVector = wm * worldVector

    #make sure that the scale of the local vector is in world space, since we're moving
    #a node outside of the hierarchy
    if not pm.pluginInfo('decomposeMatrix', q=1, loaded=1):
        pm.loadPlugin('decomposeMatrix')
    dcm = pm.createNode('decomposeMatrix')
    xf.worldMatrix.connect(dcm.inputMatrix)
    pm.select(dcm)
    scale = dcm.outputScale.get()
    localVector = localVector / scale
    pm.delete(dcm)

    #get scale amount
    scale = localVector/pm.dt.Vector(2,2,2)
    scale = [abs(scale.x), abs(scale.y), abs(scale.z)]

    #for axes that aren't the maximum, use the original scale values.
    #usually we're scaling a cube right down it's axis, so the results
    #are predictable.  Otherwise they might get weird, so warn
    maxScale = max(scale)
    handleData = eval(pm.getAttr('%s.%s' % (xf, INFO_ATTR)))
    origScale = handleData['scale']
    finalScale = []
    for i, val in enumerate(scale):
        if maxScale != val:
            if scale[i] > 0.01:
                _logger.warning("warning - performing a skewing scale.")
            finalScale.append(origScale[i])
        else:
            finalScale.append(val)
            
    pos = localVector/pm.dt.Vector(2,2,2)
    pos = [pos.x, pos.y, pos.z]

    #modify shapes
    setControl(xf, pos=pos, scale=finalScale)
    return {'pos': pos, 'scale': finalScale}
    
        
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

def makeShape_jack():
    shape_doublePin()
    shape_doublePin().ry.set(90)
    shape_doublePin().rx.set(90)
    
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
    return mm.eval('curve -d 1 -p 0 0 1 -p -0.866 0 -0.5 -p 0.866 0 -.5 -p 0 0 1  -k 0 -k 1 -k 2 -k 3 ;')

def makeShape_cross():
    crv = pm.PyNode(mm.eval('curve -d 1 -p -1 0 -5 -p 1 0 -5 -p 1 0 -1 -p 5 0 -1 -p 5 0 1 -p 1 0 1 -p 1 0 5 -p -1 0 5 -p -1 0 1 -p -5 0 1 -p -5 0 -1 -p -1 0 -1 -p -1 0 -5 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 ;'))
    
def makeShape_cross3d():
    crv = pm.PyNode(mm.eval('curve -d 1 -p -1 0 -5 -p 1 0 -5 -p 1 0 -1 -p 5 0 -1 -p 5 0 1 -p 1 0 1 -p 1 0 5 -p -1 0 5 -p -1 0 1 -p -5 0 1 -p -5 0 -1 -p -1 0 -1 -p -1 0 -5 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 ;'))
    crv.s.set([0.2,0.2,0.2])
    dup = pm.duplicate(crv)[0]
    dup.rx.set(90)
    dup = pm.duplicate(crv)[0]
    dup.rx.set(90)
    dup.ry.set(90)
    
def makeShape_jack():
    shape_doublePin()
    shape_doublePin().ry.set(90)
    shape_doublePin().rx.set(0)

def makeShape_layoutGlobals():
    pm.circle(normal=[0,1,0], r=2)
    mm.eval('curve -d 3 -p -1.169488 0 0.463526 -p -0.958738 0 0.971248 -p -0.421459 0 1.196944 -p 0.271129 0 1.255888 -p 0.994735 0 1.004275 -p 1.168226 0 0.417207 -k 0 -k 0 -k 0 -k 1 -k 2 -k 3 -k 3 -k 3 ;')
    crv = mm.eval('curve -d 3 -p 0.81419 0 -1.322437 -p 1.084855 0 -1.105855 -p 1.19143 0 -0.932901 -p 1.321428 0 -0.734364 -k 0 -k 0 -k 0 -k 1 -k 1 -k 1 ;')
    pm.duplicate(crv)[0].sx.set(-1)
    crv = pm.circle(normal=[0,1,0], r=.25, cx=-.77, cz=-.66)[0]
    pm.duplicate(crv)[0].sx.set(-1)

            
#############################################
## surface shapes
#############################################

def makeShape_orbit_srf():

    torus, tShp = pm.torus(heightRatio=0.05)
    cone1, c1Shp = pm.cone(radius=0.2, axis=[0, 0, 1])
    mm.eval('nurbsPrimitiveCap 1 1 0')
    cone2, c2Shp = pm.cone(radius=0.2, axis=[0, 0, 1])
    mm.eval('nurbsPrimitiveCap 1 1 0')
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
    mm.eval('nurbsPrimitiveCap 1 1 0')
    cone.ty.set(length + 1)
    cylinder = pm.cylinder(ax=[0, 1, 0], r=tailRadius, hr=float(length) / float(tailRadius))[0]
    mm.eval('nurbsPrimitiveCap 3 1 1')
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
    '''Create a layout globals node'''
    tmp = pm.ls('being_control')
    if tmp:
        return tmp[0]
    
    ctl = Control(shape='layoutGlobals', xformType='transform', name='being_control', color='salmon')
    node = ctl.xformNode()
    for attr in node.listAttr(keyable=1):
        try:
            attr.setLocked(True)
            attr.setKeyable(False)
        except:
            pass
    node.addAttr('layoutControlVis', at='bool', k=0, dv=1)    
    node.layoutControlVis.set(cb=1)
    node.addAttr('rigControlVis', at='bool', k=0, dv=0)
    node.rigControlVis.set(cb=1)
    return node
    
    
