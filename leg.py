'''
import throttle.control as C
reload(C)
import throttle.leg as L
import pymel.core as pm
reload(L)
pm.newFile(force=1)
ll = L.LegLayout()
ll.build()
'''
import logging, re, copy, weakref
import json
import pymel.core as pm
import throttle.control as control
import throttle.utils as utils
import throttle.nodetracking as nodetracking

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def _getStateDct(node):    
     return {'localMatrix': pm.xform(node, q=1, m=1),
             'worldMatrix': pm.xform(node, q=1, m=1, ws=1)}

class Differ(object):
    '''
    Apply transform tweaks
    '''
    def __init__(self):
        self.__nodes = set([])
        self.__initialState = {}
        
    def addNodes(self, nodes):
        for node in nodes:
            self._nameCheck(node)
            self.__nodes.add(node)
        
    def _nameCheck(self, node):
        '''All pathless node names should be unique'''
        nodeNames = [n.nodeName() for n in self.__nodes]
        if node.nodeName() in nodeNames:
            _logger.warning('Node named %s already exists!' % node.nodeName())

    
    def setInitialState(self):
        '''
        Set the initial state for all nodes
        '''
        self.__initialState = {}
        for node in self.__nodes:
            self.__initialState[node.nodeName()] = _getStateDct(node)
            
    def getDiffs(self):
        '''
        Get diffs for all nodes
        '''
        if not self.__initialState:
            raise utils.ThrottleError("Initial state was never set")
        allDiffs = {}
        for node in self.__nodes:
            diff = {}
            initialState = self.__initialState[node.nodeName()]
            state = _getStateDct(node)
            for k in initialState.keys():
                if initialState[k] != state[k]:
                    diff[k] = state[k]
            if diff:
                allDiffs[node.nodeName()] = diff
        return allDiffs
    
    def applyDiffs(self, diffDct):
        '''
        Apply diffs for nodes
        '''
        pass
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
                       'd': 'description',
                       'x': 'suffix',
                    'e': 'extras'}

    def __init__(self, characterName, **toks):
        self.__namedTokens = {'character': characterName,
                              'characterNum': '',
                              'resolution': '',
                              'side': '',
                              'part': '',
                              'description': '',
                              'extras': '',
                              'suffix': ''}
        
        self._pattern = "$c$n_$r_$s_$p_$d_$e_$x"
        if toks:
            self.setTokens(**toks)
        
    def _fullToken(self, token):
        if token in self.tokenSymbols.values():
            return token
        elif token in self.tokenSymbols.keys():
            return self.tokenSymbols[token]
        else:
            raise Exception("Invalid token '%s'" % token)
    
    def _shortToken(self, token):
        if token in self.tokenSymbols.keys():
            return token
        elif token in self.tokenSymbols.values():
            for k, v in self.tokenSymbols.items():
                if self.tokenSymbols[k] == token:
                    return k
        else:
            raise Exception("Invalid token '%s'" % token)
        
    def setTokens(self, **kwargs):
        for token, name in kwargs.items():
            name = str(name)
            key = self._fullToken(token)
            if key == 'side':
                if name not in ['lf', 'rt', 'cn']:
                    raise Exception ("invalid side '%s'" % name)
            self.__namedTokens[key] = name
        
    def getToken(self, token):
        fullToken = self._fullToken(token)
        return self.__namedTokens[fullToken]
    
    def name(self, **kwargs):
        nameParts = copy.copy(self.__namedTokens)
        for tok, val in kwargs.items():
            fullTok = self._fullToken(tok)
            nameParts[fullTok] = val
        name = self._pattern
        for shortTok, longTok in self.tokenSymbols.items():
            name = re.sub('\$%s' % shortTok, nameParts[longTok], name)
        name = '_'.join([tok for tok in name.split('_') if tok])
        return name

    def stripPrefix(self, name, errorOnFailure=False):
        '''Strip prefix from a name.'''
        prefix = '%s%s_' % (self.getToken('c'), self.getToken('n'))
        newName = ''
        parts = name.split(prefix)
        if (parts[0] == prefix):
            newName = newName.join(parts[1:])
        else:
            msg = 'Cannot strip %s from %s' % (prefix, name)
            if errorOnFailure:
                raise utils.ThrottleError(msg)
            else:
                _logger.warning(msg)
                newName = name
        return newName
        
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
                    raise utils.ThrottleError(msg)
                else:
                    _logger.warning(msg)
                    return
            else:
                return method(thisObj, *args, **kwargs)
        new.__name__  = method.__name__
        new.__doc__   = method.__doc__
        new.__dict__.update(method.__dict__)
        return new

def storeNodes(func):
    '''
    stores created nodes.  Should always decorate build functions.
    '''
    def new(self, *args, **kwargs):
        with nodetracking.NodeTracker() as nt:
            result = func(self, *args, **kwargs)
            self._nodes.extend(nt.getObjects())
            return result
    new.__name__ = func.__name__
    new.__doc__ = "<using storeCreateNodes>\n%s" % (func.__doc__ or "")
    new.__dict__.update(func.__dict__)
    return new

class LegLayout(object):
    
    layoutObjs = set([])    
    def __init__(self, num=1):
        self._namer = Namer('leg', n=num)

        for ref in self.layoutObjs:            
            obj = ref()
            if obj and obj._namer.getToken('n') == str(num):
                _logger.warning("Warning! %s has already been used" % str(num))
        
        self.__tweaks = []
        self._nodes = []
        self._status = 'unbuilt'
        self._bindJoints = []
        self._layoutControls = {}
        self._rigControls = {}
        self.storeRef(self)
        
    @classmethod
    def storeRef(cls, obj):
        '''Store weak reference to the object'''
        cls.layoutObjs.add(weakref.ref(obj))
        oldRefs = set([])
        for ref in cls.layoutObjs:
            if not ref():
                oldRefs.add(ref)
        cls.layoutObjs.difference_update(oldRefs)
        
    @BuildCheck('built')
    def getBindJoints(self, newPrefix, oriented=True):
        """
        Duplicate the bind joints.
        """
        
    def getNodes(self):
        nodes = []
        for node in self._nodes:
            if pm.objExists(node):
                nodes.append(node)
        self._nodes = nodes
        return nodes
    
    def state(self):
        """
        Return built or unbuilt
        """
        if self.getNodes():
            return "built"
        else:
            return "unbuilt"

    def registerControl(self, control, ctlType ='layout'):
        '''Register a control that should be cached'''
        ctlDct = getattr(self, '_%sControls' % ctlType)
        controlName = self._namer.stripPrefix(control.xformNode().name())
        if controlName in ctlDct.keys():
            _logger.warning("Warning!  %s already exists - overriding." % controlName)
        
    @BuildCheck('unbuilt')
    @storeNodes
    def build(self):
        """
        build the layout
        """
        namer = self._namer
        namer.setTokens(side='cn')
        
        toks = ['hip', 'knee', 'ankle', 'ball', 'toe', 'toetip']
        positions = [(0,5,0),
                     (0,2.75,1),
                     (0,.5,0),
                     (0,0,0.5),
                     (0,0,1),
                     (0,0,1.5)]

        legJoints = {}
        legCtls = {}
        pm.select(cl=1)
        for i, tok in enumerate(toks):
            legJoints[tok] = pm.joint(p=positions[i], n = namer.name(r='bnd'))            
            legCtls[tok] = control.Control(name = namer.name(x='ctl'), shape='sphere')
            self.registerControl(legCtls[tok])            
            legCtls[tok].setShape(scale=[0.3, 0.3, 0.3])
            utils.snap(legJoints[tok], legCtls[tok].xformNode(), orient=False)            
            pm.select(legJoints[tok])
        for tok in toks:
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])
            pm.parentConstraint(legCtls[tok].xformNode(), legJoints[tok])

        #create up-vec locs        
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['hip'], l,
                         aimVector=[0,1,0], upVector=[0,0,1],
                         worldUpType='object',
                         worldUpObject = legCtls['knee'])

        
    @BuildCheck('built')
    def delete(self):
        """
        Delete the layout
        """
        for node in self.getNodes():
            if pm.objExists(node):
                pm.delete(node)
        self._nodes = []
                
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
