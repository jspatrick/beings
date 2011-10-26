'''
Try a different approach.
'''
import logging

import pymel.core as pm
import RigIt.shapes
from RigIt.nodetracking import NodeTracker
import RigIt.utils as utils
import RigIt.nodetagging as nodetagging
_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class Diff(object):
    '''
    A difference from a default layout
    '''
    def __init__(self):
        self.__tweakData = {}
        
    def apply(self, layout):
        """
        Apply this tweak to a layout
        """
        #if it can't be applied, just warn

class ControlXformDiff(Diff):
    '''
    Apply transform tweaks
    '''
    def __init__(self):
        pass

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

class Control(object):
    '''
    A rig control - a shape created under a transform or joint
    '''
    @classmethod
    def controlFromNode(cls, node):
        '''Create a shape on a node'''
        
    def __init__(self, xformType='joint', name='control', shape='cube', shapeType='crv'):
        self._xform = pm.createNode(xformType, n=name)
        self.setShape(shape, shapeType=shapeType)
        
    def setShape(self, shape, shapeType='crv'):
        shapeFunc = getattr(RigIt.shapes, 'shape_%s_%s' % (shape, shapeType))
        for shape in self._xform.listRelatives(type='geometryShape'):
            pm.delete(shape)
        tmpXform = pm.createNode('transform', n='TMP')
        nodes = []
        with NodeTracker() as nt:
            shapeFunc()
            shapes = [n for n in nt.getObjects() if isinstance(n, pm.nt.GeometryShape)]
            for i, shapeNode in enumerate(shapes):
                shapeNode.rename("%sShape" % (self._xform.name()))
                tag = nodetagging.DctNodeTag(shapeNode, SHAPE_ORDER_TAG)
                tag['order'] = i
        utils.parentShapes(tmpXform, nodes)
        utils.snap(self._xform, tmpXform)
        utils.parentShape(self._xform, tmpXform)                
        #create the transform
        #create the shape under a group
        #snap the group to the transform
        #parent shape nodes in group to transform
        #delete transform
    def shapeNodes(self):
        """
        Return a list of shapes in the order they were created
        """
        nodes = self._xform.listRelatives(shapes=1)
        sortedNodes = {}
        for node in nodes:
            i = int(nodetagging.DctNodeTag(node, SHAPE_ORDER_TAG)['order'])
            sortedNodes[i] = node
        sortedKeys = sortedNodes.keys()
        sortedKeys.sort()
        return [sortedNodes[i] for i in sortedKeys]

        
    def setColor(self, color):
        if color not in COLOR_MAP:
            logger.warning("invalid color '%s'" % color)
            return

        self._color = color
        if self.state() == self.BUILT:
            for shape in self.shapeNodes():
                shape.overrideEnabled.set(1)
                shape.overrideColor.set(COLOR_MAP[self._color])
        
        
        
class Namer(object):
    '''
    Store name information, and help name nodes.    
    Nodes are named based on a token pattern.  Nodes should always be named via
    this namer, so that it can be replaced with a different namer if a different
    pattern is desired
    '''
    tokenSymbols = {'c': 'character',
                               'n': 'characterNum',
                               'r': 'resolution',
                               's': 'side',
                               'p': 'part',
                               't': 'tokens',
                               'x': 'suffix'}
    
    def __init__(self, characterName):
        self.__namedTokens = {'character': characterName,
                              'characterNum': '',
                         'resolution': '',
                         'side': '',
                         'part': ''}
        
        self._pattern = "$c$n_$r_$s_$p_$t_$x"
    
    def __fullToken(self, token):
        if token in self.tokenSymbols.values():
            return token
        elif token in self.tokenSymbols.keys():
            return self.tokenSymbols[token]
        else:
            raise Exception("Invalid token '%s'" % token)
        
    def setToken(self, token, name):
        key = self.__fullToken(token)
        if key == 'side':
            if name not in ['lf', 'rt', 'cn']:
                raise Exception ("invalid side '%s'" % name)
        self.__namedTokens[key] = name
                
    def name(self, *args):
        argsTok = args.join('_')
        

class RigItError(Exception): pass
class BuildCheck(object):
    """
    warn and gracefully exit if the object is not in the
    right state to use the decorated method
    """
    def __init__(self, *acceptableStates, **kwargs):
        self.__raiseException = kwargs.get('raiseException', False)
        self.__acceptableStates = acceptableStates
        
    def __call__(self, method):
        """
        Decorate the method, checking that it's in an acceptable state
        """
        def new(thisObj, *args, **kwargs):
            if thisObj.state()not in self.__acceptableStates:
                msg = "Not in one of these states: %s" \
                    % ", ".join(self.__acceptableStates)
                if self.__raiseException:
                    raise RigItError(msg)
                else:
                    _logger.warning(msg)
                    return
            else:
                return method(thisObj, *args, **kwargs)
        new.__name__  = method.__name__
        new.__doc__   = method.__doc__
        new.__dict__.update(method.__dict__)
        return new

class LegLayout(object):
    
    def __init__(self):
        self.__namer = Namer('leg')
        self.__tweaks = []
        self.__nodes = []
        
    @BuildCheck('built')
    def duplicateJoints(self, newPrefix):
        """
        Duplicate the bind joints.
        """
        
    def state(self):
        """
        Return built or unbuilt
        """
        return "unbuilt"
    
    @BuildCheck('unbuilt')
    def build(self):
        """
        build the layout
        """
        legJoints = {}
        
        legJoints['hip'] = pm.joint(p =[0, 5, 0])
        legJoints['knee'] = pm.joint(p =[0, 3.5, 1])
        legJoints['ankle'] = pm.joint(p =[0, 1, 0])
        legJoints['ball'] = pm.joint(p =[0, 0, 0.5])
        legJoints['toe'] = pm.joint(p =[0, 0, 1])
        legJoints['toeTip'] = pm.joint(p =[0, 0, 1.5])

        
    @BuildCheck('built')
    def delete(self):
        """
        Delete the layout
        """
    
    @BuildCheck('built')
    def cacheTweaks(self):
        """
        Store tweaks internally
        """
        
    def getTweaks(self, cached=False):
        """
        get the object's tweaks, if built
        @param cached=False: return tweaks cached in memory
        """
        pass
    
    @BuildCheck('built')
    def applyTweaks(self, tweaks):
        """
        Apply tweaks
        """
        pass

class LegRig(object):
    def __init__(self, layout):
        self.__layout = layout
        
    def build(self, charName, side='cn'):
        """
        Build the rig, using the information in the layout
        """
        pass
    
    def _getTopFkChildren(self):
        """
        Get the nodes that should be directly parented under another rig's node
        """
        pass
    
    def _getTopIkChildren(self):
        """
        Get the nodes that should be parented under the character's 'master' control
        """
        pass
    
    def _getDNTNodes(self):
        """
        Get the nodes that should be parented under the DNT
        """
    def parentTo(self, otherRig, node):
        """
        parent this rig to otherRig under node
        """
        pass
