"""
import throttle.control as C
reload(C)
import throttle.leg as L
import pymel.core as pm
import throttle.utils
reload(L)
pm.newFile(force=1)
ll = L.LegLayout()
ll.build()
ctl = C.Control.fromNode(pm.PyNode('leg1_cn_ctl2'))
d = L.Differ()
d.addObjs([ctl])
d.setInitialState()
ctl.xformNode().tx.set(1)
diffs = d.getDiffs()
pm.newFile(force=1)
ll = L.LegLayout()
ll.build()
ll.delete()
d.applyDiffs(diffs)
"""

import logging, re, copy, weakref
import json
import pymel.core as pm
import throttle.control as control
import throttle.utils as utils
import throttle.nodetracking as nodetracking

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def _getStateDct(obj):
    """ Get a dict representing the state of the node """
    result = {}
    if isinstance (obj, control.Control):
        result.update(obj.getHandleInfo())
        obj = obj.xformNode()
    result['localMatrix'] = pm.xform(obj, q=1, m=1)
    result['worldMatrix'] = pm.xform(obj, q=1, m=1, ws=1)
    return result

class Differ(object):
    """
    Get and set control differences
    """
    def __init__(self):
        self.__controls = {}
        self.__initialState = {}

    def addObjs(self, objDct, diffSpaceType='local'):
        """
        Add Control objects to the differ.
        @param objDct:  a dict of {objectKey: object}
        @param diffSpaceType="local": get diffs in this space (local or world)
        """
        for key, obj in objDct.items():
            if not isinstance(obj, control.Control):
                _logger.warning("%r is not a control; skipping" % obj)
                continue
            if self._nameCheck(obj):
                self.__controls[key] = (obj, diffSpaceType)
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


    def getDiffs(self):
        """
        Get diffs for all nodes
        """
        if not self.__initialState:
            raise utils.ThrottleError("Initial state was never set")
        allDiffs = {}
        for k, ctlPair in self.__controls.items():
            control = ctlPair[0]
            space = ctlPair[1]
            diff = {}
            initialState = self.__initialState[k]
            state = _getStateDct(control)
            for ik in initialState.keys():
                if space == 'world' and ik == 'localMatrix':
                    continue
                elif space == 'local' and ik == 'worldMatrix':
                    continue
                if initialState[ik] != state[ik]:
                    diff[ik] = state[ik]
            if diff:
                allDiffs[k] = diff
        return allDiffs

    def applyDiffs(self, diffDct):
        """
        Apply diffs for nodes.
        """
        diffDct = copy.deepcopy(diffDct)
        if isinstance(diffDct, basestring):
            diffDct = json.loads(diffDct, object_hook=utils.decodeDict)

        for ctlKey, diffs in diffDct.items():
            try:
                ctl = self.__controls[ctlKey][0]
            except ValueError:
                _logger.warning("%s does not exist, skipping" % ctlKey)
                continue

            node = ctl.xformNode()
            #apply and discard the matricies from the diff dict
            matrix = diffs.get('worldMatrix', None)
            if matrix:
                pm.xform(node, m=matrix, ws=1)
                diffs.pop('worldMatrix')

            matrix = diffs.get('localMatrix', None)
            if matrix:
                pm.xform(node, m=matrix)
                diffs.pop('localMatrix')

            #remaining kwargs are shapes, so apply them
            if diffs:
                ctl.setShape(**diffs)

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
    """
    Store name information, and help name nodes.
    Nodes are named based on a token pattern.  Nodes should always be named via
    this namer, so that it can be replaced with a different namer if a different
    pattern is desired
    """
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

    def getToken(self, token):
        fullToken = self._fullToken(token)
        return self.__namedTokens[fullToken]

    def setTokens(self, **kwargs):
        for token, name in kwargs.items():
            name = str(name)
            key = self._fullToken(token)
            if key == 'side':
                if name not in ['lf', 'rt', 'cn']:
                    raise Exception ("invalid side '%s'" % name)
            self.__namedTokens[key] = name

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

    def stripPrefix(self, name, errorOnFailure=False, replaceWith=''):
        """Strip prefix from a name."""
        prefix = '%s%s_' % (self.getToken('c'), self.getToken('n'))
        newName = ''
        parts = name.split(prefix)
        if (parts[0] == ''):
            newName = newName.join(parts[1:])
        else:
            msg = 'Cannot strip %s from %s; parts[0] == %s' % (prefix, name, parts[0])
            if errorOnFailure:
                raise utils.ThrottleError(msg)
            else:
                _logger.warning(msg)
                newName = name
        if replaceWith:
            newName = '%s_%s' % (replaceWith, newName)
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


class LegLayout(object):
    layoutObjs = set([])
    def __init__(self, num=1):
        self._namer = Namer('leg', n=num)

        for ref in self.layoutObjs:
            obj = ref()
            if obj and obj._namer.getToken('n') == str(num):
                _logger.warning("Warning! %s has already been used" % str(num))

        self._nodes = []
        self._bindJoints = {}
        self._layoutControls = {}
        self._rigControls = {}
        self.storeRef(self)
        self.differ = Differ()
        self._cachedDiffs = {}

    def name(self):
        return self._namer.getToken('c') + self._namer.getToken('n')

    @classmethod
    def storeRef(cls, obj):
        """Store weak reference to the object"""
        cls.layoutObjs.add(weakref.ref(obj))
        oldRefs = set([])
        for ref in cls.layoutObjs:
            if not ref():
                oldRefs.add(ref)
        cls.layoutObjs.difference_update(oldRefs)

    @BuildCheck('built')
    def duplicateBindJoints(self, prefix, oriented=True):
        """
        Duplicate the bind joints.  Give a new prefix
        """
        if prefix == self.name():
            raise utils.ThrottleError("Prefix must be different than the rig name")
        
        #duplicate all joints, parent them to the world
        result = {}
        newJnts = []
        for tok, jnts in self._bindJoints.items():
            jnt = jnts[0]
            parent = jnts[1]
            newName = self._namer.stripPrefix(jnt, replaceWith=prefix, errorOnFailure=True)
            newJnt = pm.duplicate(jnt, name=newName, po=True)[0]
            newJnt.setParent(world=True)
            #get the name of the duplicated parent
            if parent:
                newParentName  = self._namer.stripPrefix(parent, replaceWith=prefix, errorOnFailure=True)
            else:
                newParentName = None
            result[tok] = newJnt
            newJnts.append((newJnt, newParentName))
            
        #find parents for joints and store pre-parented world matrices
        topJnts = []
        #wsXforms = {}
        for newJnt, newParentName in newJnts:
            #wsXforms[newJnt] = pm.xform(newJnt, m=1, ws=1, q=1)
            if not newParentName:
                topJnts.append(newJnt)
                continue
            newParentNode = pm.PyNode(newParentName)            
            pm.connectJoint(newJnt, newParentNode, pm=True)

        #make sure parenting didn't alter the world matrix
        for jnt in topJnts:
            chain = jnt.listRelatives(ad=1)
            chain.append(jnt)
            chain.reverse()
            # for node in chain:
            #     pm.xform(node, m=wsXforms[node], ws=1)
            utils.fixInverseScale(chain)
            
        return result
    def _orientBindJoints(self, jntDct):
        '''Orient bind joints.  jntDct is {layoutBindJntName: newBindJntPynode}'''

        
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
        
    def registerBindJoint(self, name, jnt, jntParent=None):
        '''Register bind joints to be duplicated'''
        if name in self._bindJoints.keys():
            _logger.warning("%s is already a key in bind joints dict" % name)
        def checkName(jnt): 
            if isinstance(jnt, pm.PyNode):
                jntName = jnt.name()
            else:
                jntName = jnt
            if not jntName.startswith(self.name()):
                raise utils.ThrottleError("Joint name must start with the rig prefix('%s')" % self.name())
            if '|' in jntName or not pm.objExists(jntName):
                raise utils.ThrottleError('One and only one object may exist called %s' % jntName)
            return jntName
        jnt = checkName(jnt.name())
        if jntParent:
            jntParent = checkName(jntParent.name())
        self._bindJoints[name] = (jnt, jntParent)
        
    def registerControl(self, control, ctlType ='layout'):
        """Register a control that should be cached"""
        ctlDct = getattr(self, '_%sControls' % ctlType)
        controlName = self._namer.stripPrefix(control.xformNode().name())
        if controlName in ctlDct.keys():
            _logger.warning("Warning!  %s already exists - overriding." % controlName)
        else:
            ctlDct[controlName] = control

    @BuildCheck('unbuilt')
    def build(self, useCachedDiffs=True):
        self._bindJoints = {}
        self._layoutControls = {}
        self._rigControls = {}
        with nodetracking.NodeTracker() as nt:
            try:
                self._setupRig()
            finally:
                self._nodes = nt.getObjects()
        self.differ.addObjs(self._layoutControls)
        self.differ.addObjs(self._rigControls)
        self.differ.setInitialState()
        if useCachedDiffs:
            self.differ.applyDiffs(self._cachedDiffs)
            
    def _setupRig(self):
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
            legJoints[tok] = pm.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            legCtls[tok] = control.Control(name = namer.name(x='ctl', d=tok), shape='sphere')
            self.registerControl(legCtls[tok])
            legCtls[tok].setShape(scale=[0.3, 0.3, 0.3])
            utils.snap(legJoints[tok], legCtls[tok].xformNode(), orient=False)
            pm.select(legJoints[tok])
        for i, tok in enumerate(toks):
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])
            pm.parentConstraint(legCtls[tok].xformNode(), legJoints[tok])
            parent = None
            if i > 0:
                parent = legJoints[toks[i-1]]
            self.registerBindJoint(tok, legJoints[tok], parent)
            
        #create up-vec locs
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['hip'], l,
                         aimVector=[0,1,0], upVector=[0,0,1],
                         worldUpType='object',
                         worldUpObject = legCtls['knee'])
        
    @BuildCheck('built')
    def delete(self, cache=True):
        """
        Delete the layout
        """
        if cache:
            self.cacheDiffs()
        for node in self.getNodes():
            if pm.objExists(node):
                pm.delete(node)
        self._nodes = []

    @BuildCheck('built')
    def cacheDiffs(self):
        """
        Store tweaks internally
        """
        self._cachedDiffs = self.differ.getDiffs()

    def getDiffs(self, cached=False):
        """
        get the object's tweaks, if built
        @param cached=False: return tweaks cached in memory
        """
        if cached:
            return self._cachedDiffs
        elif self.state() == 'built':
            return self.differ.getDiffs()
        else:
            raise utils.ThrottleError("If not built, must get cached tweaks")

    @BuildCheck('built')
    def applyDiffs(self, diffDict):
        """
        Apply tweaks
        """
        self.differ.applyDiffs(diffDict)

class LegRig(object):
    def __init__(self, layout):
        self.layout = layout
        
    def build(self, charName, side='cn'):
        """
        Build the rig, using the information in the layout
        """
        self._makeRig()
        
    def _makeRig(self):
        if self.layout.state() != 'built':
            self.layout.build()
        bindJntDct = self.__layout.duplicateBindJoints(prefix='tmp')        
    
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
