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

    def __init__(self, **toks):
        self.__namedTokens = {'character': '',
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

    #TODO:  get prefix toks from pattern
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

class OptionError(utils.ThrottleError): pass
class OptionCollection(object):
    def __init__(self):
        '''
        A collection of options
        '''
        
        self.__options = {}
        self.__presets = {}
        self.__rules = {}
        self.__optPresets = {}
    
    def addOpt(self, optName, defaultVal, optType=str, **kwargs):
        self.__options[optName] = optType(defaultVal)
        self.__rules[optName] = {'optType': optType}
        presets = kwargs.get('presets')
        if presets:
            self.setPresets(optName, *presets)
        
    def _checkName(self, optName):
        if optName not in self.__options:
            raise utils.ThrottleError("Invalid option %s") % optName
    
    def setPresets(self, optName, *args, **kwargs):
        self._checkName(optName)
        replace = kwargs.get('replace', False)        
        if replace:
            self.__presets[optName] = set(args)
        else:
            presets = self.__presets.get(optName, set([]))
            presets = presets.union(args)
            self.__presets[optName] = presets
            
    def getPresets(self, optName):
        self._checkName(optName)
        return sorted(list(self.__presets[optName]))
    
    def getOpt(self, optName):
        self._checkName(optName)
        return self.__options[optName]
    
    def setOpt(self, optName, val):
        self._checkName(optName)
        self.__options[optName] = val
        
    def getAllOpts(self):
        return copy.deepcopy(self.__options)
    def setAllOpts(self, optDct):
        for optName, optVal in optDct.items():
            self.setOpt(optName, optVal)
            
class LegLayout(object):
    layoutObjs = set([])
    def __init__(self, part='leg', useNextAvailablePart=True, **kwargs):
        self._namer = Namer(part=part)

        #Get a unique part name.  This ensures all node names are unique
        #when multiple widgets are built.
        if useNextAvailablePart:
            usedNums = []
            for obj in self.getObjects():
                otherPart = obj.options.getOpt('part')
                try:
                    num = int(otherPart.split(part)[1])                
                except IndexError, ValueError:
                    continue
                usedNums.append(num)
            if usedNums:
                part ='%s%i' % (part, (sorted(usedNums)[-1] + 1))
            else:
                part = '%s1' % part
        
        #set up options    
        self.options = OptionCollection()
        self.options.addOpt('part', part)
        self.options.addOpt('side', 'cn', presets=['cn', 'lf', 'rt'])
        self.options.addOpt('char', 'defaultchar')
        self._nodes = []
        self._bindJoints = {}
        self._layoutControls = {}
        self._rigControls = {}
        self.differ = Differ()
        self._cachedDiffs = {}
        #todo: validate options
        for k, v in kwargs.items():
            try:
                self.options.setOpt(k, v)
            except OptionError:
                pass
                
        #keep reference to this object so we can get unique names        
        self.storeRef(self)
    
    def name(self):
        return self._namer.getToken('c') + self._namer.getToken('n')

    @classmethod
    def getObjects(cls):
        ''' get all referenced objects'''
        result = []
        for ref in cls.layoutObjs:
            obj = ref()
            if obj:
                result.append(obj)
            else:
                cls.layoutObjs.remove(ref)
        return result
        
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
    def duplicateBindJoints(self, oriented=True):
        """
        Duplicate the bind joints.  Give a new prefix
        """
        #use tmp prefix when duplicating so nodes aren't renamed by Maya
        prefix = 'TMP'
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

        #reparent joints
        topJnts = []
        for newJnt, newParentName in newJnts:
            if not newParentName:
                topJnts.append(newJnt)
                continue
            newParentNode = pm.PyNode(newParentName)
            pm.connectJoint(newJnt, newParentNode, pm=True)

        #rename the joints to use the charName and side options
        for jnt in topJnts:
            chain = jnt.listRelatives(ad=1)
            chain.append(jnt)
            chain.reverse()
            utils.fixInverseScale(chain)
            for jnt in chain:
                #newName = re.sub('^%s_' % prefix, '%s_' % self.name(), jnt.nodeName())
                newName = re.sub('^%s_' % prefix, '%s_' % self._options['charName'], jnt.nodeName())
                newName = re.sub('_cn_', '_%s_' % self.getSide(), newName)
                jnt.rename(newName)
        self._orientBindJoints(result)
        return result

    def _orientBindJoints(self, jntDct):
        '''Orient bind joints.  jntDct is {layoutBindJntName: newBindJntPynode}'''
        worldUpVec = utils.getXProductFromNodes(jntDct['knee'], jntDct['hip'], jntDct['ankle'])
        for jnt in jntDct.values():
            utils.freeze(jnt)
        for tok in ['hip', 'knee']:
            utils.orientJnt(jntDct[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=worldUpVec)
        for tok in ['ankle', 'ball', 'toe', 'toetip']:
            utils.orientJnt(jntDct[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])

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
            for ctl in self._layoutControls.values():
                if ctl.xformNode().exists():
                    return "built"
            return "rigged"
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
        self._namer.setTokens(side='cn')
        self._bindJoints = {}
        self._layoutControls = {}
        self._rigControls = {}
        with utils.NodeTracker() as nt:
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
            legCtls[tok].xformNode().r.setLocked(True)

        ankleCtl = legCtls['ankle']
        for tok in ['ball', 'toe', 'toetip']:
            ctl = legCtls[tok]
            ctl.xformNode().setParent(ankleCtl.xformNode())
            ctl.xformNode().tx.setLocked(True)
        #create up-vec locs
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['hip'], l,
                         aimVector=[0,1,0], upVector=[0,0,1],
                         worldUpType='object',
                         worldUpObject = legCtls['knee'])

    @BuildCheck('built', 'rigged')
    def delete(self, cache=True):
        """
        Delete the layout
        """
        if cache:
            if self.state() == 'rigged':
                _logger.debug('deleting a rig - skipping caching')
            else:
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


    def buildRig(self):
        """build the rig"""
        if self.state() != "built":
            self.build()
        pm.refresh()
        jntDct = self.duplicateBindJoints()
        self.delete()
        result = {}
        with utils.NodeTracker() as nt:
            origName = self._namer.getToken('c')
            origNum = self._namer.getToken('n')
            try:
                self._namer.setTokens(c=self._options['charName'], n='', side=self._options['side'])
                grps = {}
                grps['top'] = pm.createNode('transform', n='%s_rig' % self.name())
                for tok in ['dnt', 'ik', 'fk']:
                    grps[tok] = pm.createNode('transform', n='%s_%s_grp' % (self.name(), tok))
                    grps[tok].setParent(grps['top'])
                result.update(self._makeRig(jntDct, grps))
            finally:
                self._nodes = nt.getObjects()
                self._namer.setTokens(c=origName, n=origNum, side='cn')
                
        return result
    
    def setSide(self, side):
        self._options['side'] = side
    def getSide(self):
        return self._options['side']

    def _makeRig(self, bndJnts, grps):
        bndJnts['hip'].setParent(grps['top'])
        o = utils.Orientation()
        if self.getSide() == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts.values())
            
        fkJnts = utils.dupJntDct(bndJnts, '_bnd_', '_fk_')
        fkCtls = {}
        for tok, jnt in fkJnts.items():
            if tok == 'toetip':
                continue
            ctl = control.Control(jnt, shape='cube', scaleToChild=True, scale=[.25, .25, .25],
                                  color='yellow')
            fkCtls[tok] = ctl
        pm.delete(fkJnts['toetip'])
        fkJnts.pop('toetip')        
        self._namer.setTokens(r='ik')
        ikJnts = utils.dupJntDct(bndJnts, '_bnd_', '_ik_')
        ikCtl = control.Control(name=self._namer.name(), shape='sphere', color='lite blue').xformNode()
        utils.snap(bndJnts['ankle'], ikCtl, orient=False)
        ikHandle, ikEff = pm.ikHandle(sj=ikJnts['hip'], ee=ikJnts['ankle'], solver='ikRPsolver',
                                      n=self._namer.name(s='ikh'))
        ikHandle.setParent(ikCtl)
        ikCtl.addAttr('fkIk', min=0, max=1, dv=1, k=1)
        fkIkRev = pm.createNode('reverse', n=self._namer.name(d='fkik', s='rev'))
        ikCtl.fkIk.connect(fkIkRev.inputX)
        for j in fkJnts.values():
            fkIkRev.outputX.connect(j.v)
        return locals()
        #setup blend
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
