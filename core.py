"""
import pymel.core as pm
import throttle.control as C
import throttle.leg as L
import throttle.utils as U
reload(U)
reload(C)
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
import beings.control as control
import beings.utils as utils
import maya.OpenMaya as OM
import utils.NodeTagging as NT
import maya.cmds as MC
from PyQt4.QtCore import *
from PyQt4.QtGui import *
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

    def addObjs(self, objDct, space='local'):
        """
        Add Control objects to the differ.
        @param objDct:  a dict of {objectKey: object}
        @param space="local": get diffs in this space (local, world, or both)
        """
        for key, obj in objDct.items():
            if not isinstance(obj, control.Control):
                _logger.warning("%r is not a control; skipping" % obj)
                continue
            if self._nameCheck(obj):
                self.__controls[key] = (obj, space)
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
            raise utils.BeingsError("Initial state was never set")
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

    def applyDiffs(self, diffDct, skipWorldXforms=False, skipLocalXforms=False):
        """
        Apply diffs for nodes.
        @param diffDict:  a dictionary of [diffKey: diffs], gotten from getDiffs
        @param skipWorldXforms=False: Don't apply diffs to objects added in world space

        Notes
        -----
        Generally, when we are setting up a layout rig, we want to add all controls
        to the differ, but rig controls are added as worldspace diffs.  When we
        rebuild the layout rig, 
        
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
                if not skipWorldXforms:
                    pm.xform(node, m=matrix, ws=1)
                diffs.pop('worldMatrix')

            matrix = diffs.get('localMatrix', None)
            if matrix:
                if not skipLocalXforms:
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
                raise utils.BeingsError(msg)
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
                    raise utils.BeingsError(msg)
                else:
                    _logger.warning(msg)
                    return
            else:
                return method(thisObj, *args, **kwargs)
        new.__name__  = method.__name__
        new.__doc__   = method.__doc__
        new.__dict__.update(method.__dict__)
        return new


class Widget(utils.Types.WidgetTreeItem):
    
    layoutObjs = set([])
    VALID_NODE_CATEGORIES = ['master', 'dnt', 'cog', 'ik', 'fk']
    
    #Tree item reimplementations
    def getData(self, col):
        if col == 4: return self.name(id=True)
        else:
            return super(Widget, self).getData(col)
        
    def __init__(self, part='widget', useNextAvailablePart=True, **kwargs):

        #Get a unique part name.  This ensures all node names are unique
        #when multiple widgets are built.
        
        
        self.ref = self
        self.numColumns = 5
        
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
                
        super(Widget, self).__init__(part)
        assert(self.options)
        self._partID = part
        self._nodes = [] #stores all nodes        
        self._bindJoints = {} #stores registered bind joints
        self._layoutControls = {}
        self._rigControls = {}
        self._differs = {'rig': Differ(), 'layout': Differ()}
        self._cachedDiffs = {'rig': {}, 'layout': {}}
        self._nodeCategories = {}
        self._parentNodes = {}
        for categoy in self.VALID_NODE_CATEGORIES:
            self._nodeCategories[categoy] = []

        
        #keep reference to this object so we can get unique names        
        self.storeRef(self)
        
    @classmethod
    def getObjects(cls):
        ''' get all referenced objects'''
        result = []
        toRemove = []
        for ref in cls.layoutObjs:
            obj = ref()
            if obj:
                result.append(obj)                
            else:
                toRemove.append(ref)
        for rmv in toRemove:
            cls.layoutObjs.remove(rmv)
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
    
    def name(self, id=False):
        """ Return a name of the object.
        partID should always be unique.  This can be used as a key
        in dictionaries referring to multiple instances"""
        if id:
            return self._partID
        part = self.options.getOpt('part')
        side = self.options.getOpt('side')
        return '%s_%s' % (part, side)

    def __repr__(self):
        return "%s(part='%s', useNextAvailablePart=False)" % \
               (self.__class__.__name__, self.name(id=True))

    def __str__(self):
        return "%s(part= '%s', useNextAvailablePart=False)" % \
               (self.__class__.__name__, self.name(id=True))

    @BuildCheck('built')
    def duplicateBindJoints(self, oriented=True):
        """
        Duplicate the bind joints.  Give a new prefix
        """
        #check that all parents are also joints in the dict
        parentToks = {} # map of the orinal parent joint to the dup joint tok
        dupJnts = [j[0] for j in self._bindJoints.values()]
        for dupJnt, parentJnt in self._bindJoints.values():
            
            if not parentJnt:
                parentToks[dupJnt] = None
                continue
            found=False
            for tok, jntPair in self._bindJoints.items():
                if parentJnt == jntPair[0]:
                    parentToks[parentJnt] = tok
                    found=True
                    break
            if not found:
                raise utils.BeingsError("joint parent %s is not a registered joint" % parentJnt.name())
            
        result = {}
        for key, jntPair in self._bindJoints.items():
            jnt = jntPair[0]
            name = jnt.nodeName()
            result[key] = pm.duplicate(jnt, po=True)[0]
            result[key].setParent(world=True)
            result[key].rename(name) # try and name it back to the original name
        #do parenting
        for key, jntPair in self._bindJoints.items():
            parentJnt = jntPair[1]
            if not parentJnt:
                continue
            parentJointTok = parentToks[parentJnt]
            result[key].setParent(result[parentJointTok])
            
        #rename
        char = self.options.getOpt('char')
        side = self.options.getOpt('side')
        part = self.options.getOpt('part')        
        
        namer = Namer(c=char, s=side, p=part, r='bnd')
        for tok, jnt in result.items():
            jnt.rename(namer.name(d=tok))
        self._orientBindJoints(result)            
        return result

    def _orientBindJoints(self, jntDct):
        '''Orient bind joints.  jntDct is {layoutBindJntName: newBindJntPynode}'''
        pass

    def getNodes(self, category=None):
        nodes = []
        if category is not None:
            if category not in self._nodeCategories.keys():
                raise utils.BeingsError("Invalid category %s" % category)
            #return a copy of the list
            nodes = [n for n in self._nodeCategories[category]]
            if category == 'fk':
                otherCategoryNodes = set([])
                for grp in self._nodeCategories.values():
                    otherCategoryNodes.update(grp)
                
                for n in self.getNodes():
                    if isinstance(n, pm.nt.DagNode) and not n.getParent():
                        if n not in otherCategoryNodes:
                            _logger.warning("Directly parenting uncategoried top-level node '%s'" % n.name())
                            nodes.append(n)                                
            return nodes
        
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

    def registerBindJoint(self, name, jnt, parent=None):
        '''Register bind joints to be duplicated'''
        if name in self._bindJoints.keys():
            _logger.warning("%s is already a key in bind joints dict" % name)
        def checkName(jnt):
            if isinstance(jnt, pm.PyNode):
                jntName = jnt.name()
            else:
                jntName = jnt
            if '|' in jntName or not pm.objExists(jntName):
                raise utils.BeingsError('One and only one object may exist called %s' % jntName)
            return pm.PyNode(jnt)
        jnt = checkName(jnt)
        if parent:
            parent = checkName(parent)
        self._bindJoints[name] = (jnt, parent)

    def registerControl(self, name, ctl, ctlType ='layout'):
        """Register a control that should be cached"""        
        ctlDct = getattr(self, '_%sControls' % ctlType)
        controlName = name
        if controlName in ctlDct.keys():
            _logger.warning("Warning!  %s already exists - overriding." % controlName)
        else:
            ctlDct[controlName] = ctl
        #add to display layer
        globalNode = control.layoutGlobalsNode()
        if ctlType == 'layout':
            for shape in ctl.shapeNodes():                
                globalNode.layoutControlVis.connect(shape.overrideVisibility)
        elif ctlType == 'rig':
            for shape in ctl.shapeNodes():                
                globalNode.rigControlVis.connect(shape.overrideVisibility)

    @BuildCheck('unbuilt')
    def buildLayout(self, useCachedDiffs=True, altDiffs=None):
        
        side = self.options.getOpt('side')
        part = self.options.getOpt('part')
        namer = Namer()
        namer.setTokens(side=side, part=part)

        self._bindJoints = {}
        self._layoutControls = {}
        self._rigControls = {}
        with utils.NodeTracker() as nt:
            try:
                self._makeLayout(namer)
            finally:
                self._nodes = nt.getObjects()
                
        #set up the differ
        self._differs['layout'].addObjs(self._layoutControls)
        self._differs['rig'].addObjs(self._rigControls, space='both')
        for diffType, differ in self._differs.items():
            differ.setInitialState()
            if altDiffs:
                self.applyDiffs(altDiffs)
            elif useCachedDiffs:
                self.applyDiffs(self._cachedDiffs)
            
    def _makeLayout(self, namer):
        """
        build the layout
        """
        raise NotImplementedError
    
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
        #silence the pymel logger or it's pretty noisy about missing nodes
        pmLogger = logging.getLogger('pymel.core.nodetypes')
        propagate = pmLogger.propagate
        pmLogger.propagate = 0
        for node in self.getNodes():
            if pm.objExists(node):
                pm.delete(node)
        pmLogger.propagate = propagate
        self._nodes = []

    @BuildCheck('built')
    def cacheDiffs(self):
        """
        Store tweaks internally
        """
        self._cachedDiffs['rig'] = self._differs['rig'].getDiffs()
        self._cachedDiffs['layout'] = self._differs['layout'].getDiffs()

    def getDiffs(self, cached=False):
        """
        get the object's tweaks, if built
        @param cached=False: return tweaks cached in memory
        """        
        if self.state() == 'built':
            if cached:
                return self._cachedDiffs
            else:
                result = {}
                result['rig'] = self._differs['rig'].getDiffs()
                result['layout'] = self._differs['layout'].getDiffs()
                return result
        else:
            return self._cachedDiffs

    @BuildCheck('built')
    def applyDiffs(self, diffDict):
        """
        Apply tweaks
        """
        rigDiffs = diffDict['rig']
        layoutDiffs = diffDict['layout']
        self._differs['rig'].applyDiffs(rigDiffs, skipWorldXforms=True)
        self._differs['layout'].applyDiffs(layoutDiffs)

    
    def setNodeCateogry(self, node, category):
        '''
        Add a node to a category.  This is used by the parenting
        system to determine where to place a node in the hierarchy
        of the character
        '''
        if category not in self._nodeCategories.keys():
            raise utils.BeingsError("invalid category %s" % category)
        self._nodeCategories[category].append(node)

        
    @BuildCheck('built', 'unbuilt')
    def buildRig(self, altDiffs=None):
        """build the rig
        @param altDiffs=None: Use the provided diff dict instead of the internal diffs"""
        if self.state() != "built":
            self.buildLayout(altDiffs=altDiffs)
        else:
            if altDiffs:
                self.delete()
                self.buildLayout(altDiffs=altDiffs)
            else:
                self.cacheDiffs()
        pm.refresh()
        
        namer = Namer()
        namer.setTokens(c=self.options.getOpt('char'),
                        n='',
                        side=self.options.getOpt('side'),
                        part=self.options.getOpt('part'))
        bndJntNodes = []
        with utils.NodeTracker() as nt:
            jntDct = self.duplicateBindJoints()
            bndJntNodes = nt.getObjects()
        
        self.delete()
        
        for tok, jnt in jntDct.items():
            jnt.rename(namer.name(d=tok, r='bnd'))
        with utils.NodeTracker() as nt:
            
            #re-create the rig controls
            diffs = altDiffs if altDiffs else self._cachedDiffs
            rigCtls = {}
            differ = Differ()
            differ.addObjs(self._rigControls)
            for ctlName, ctlObj in self._rigControls.items():
                name = namer.name(d=ctlName, r='ctl')
                ctlObj.build(name=name)
            differ.applyDiffs(diffs['rig'], skipLocalXforms=True)            

            result = self._makeRig(namer, jntDct, copy.copy(self._rigControls))
            
            nodes = nt.getObjects()
            nodes.extend(bndJntNodes)
            self._nodes = nodes
                
        for key, node in self._parentNodes.items():
            if node == None:
                _logger.warning("The '%s' parentNodeName was not assigned a a node" % key)
        return result
    
    def _makeRig(self, namer, bndJnts, rigCtls):
        raise NotImplementedError

        
class BasicLeg(Widget):
    def __init__(self, part='basicleg', **kwargs):
        super(BasicLeg, self).__init__(part=part, **kwargs)
        #add parentable Nodes
        self.addParentPart('bnd_hip')
        self.addParentPart('bnd_knee')
        self.addParentPart('bnd_ankle')
        
    def _orientBindJoints(self, jntDct):
        '''Orient bind joints.  jntDct is {layoutBindJntName: newBindJntPynode}'''
        worldUpVec = utils.getXProductFromNodes(jntDct['knee'], jntDct['hip'], jntDct['ankle'])
        for jnt in jntDct.values():
            utils.freeze(jnt)
        for tok in ['hip', 'knee']:
            utils.orientJnt(jntDct[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=worldUpVec)
        for tok in ['ankle', 'ball', 'toe', 'toetip']:
            utils.orientJnt(jntDct[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])
            
    def _makeLayout(self, namer):
        """
        build the layout
        """

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
            self.registerControl(tok, legCtls[tok])
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

        #make rig controls
        ankleIkCtl = control.Control(name=namer.name(d='ankle', r='ik'), shape='sphere', color='blue')
        self.registerControl('ankleIK', ankleIkCtl, ctlType='rig')
        
        #create up-vec locs
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['hip'], l,
                         aimVector=[0,1,0], upVector=[0,0,1],
                         worldUpType='object',
                         worldUpObject = legCtls['knee'])


    def _makeRig(self, namer, bndJnts, rigCtls):
        #add the parenting nodes - this is a required step
        for tok in ['hip', 'knee', 'ankle']:
            self.setParentNode('bnd_%s' % tok, bndJnts[tok])
        
        o = utils.Orientation()
        side = self.options.getOpt('side')
        if side == 'rt':
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
        namer.setTokens(r='ik')
        ikJnts = utils.dupJntDct(bndJnts, '_bnd_', '_ik_')
        ikCtl = control.Control(name=namer.name(), shape='sphere', color='lite blue').xformNode()
        self.setNodeCateogry(ikCtl, 'ik')
        utils.snap(bndJnts['ankle'], ikCtl, orient=False)
        ikHandle, ikEff = pm.ikHandle(sj=ikJnts['hip'], ee=ikJnts['ankle'], solver='ikRPsolver',
                                      n=namer.name(s='ikh'))
        ikHandle.setParent(ikCtl)
        ikCtl.addAttr('fkIk', min=0, max=1, dv=1, k=1)        
        fkIkRev = pm.createNode('reverse', n=namer.name(d='fkik', s='rev'))
        ikCtl.fkIk.connect(fkIkRev.inputX)
        for j in fkJnts.values():
            fkIkRev.outputX.connect(j.v)

class CenterOfGravity(Widget):
    def __init__(self, part='cog', **kwargs):
        super(CenterOfGravity, self).__init__(part=part, **kwargs)
        self.options.setPresets('side', 'cn')
        self.addParentPart('cog_bnd')
        self.addParentPart('cog_ctl')
        self.addParentPart('master_ctl')
        self.addParentPart('body_ctl')
        self.addParentPart('pivot_ctl')
        
    def _makeLayout(self, namer):
        #make the
        masterLayoutCtl = control.Control(shape='circle', color='red', scale=[4.5, 4.5, 4.5],
                                          name=namer.name(d='master_layout', s='ctl'), xformType='transform')
        self.registerControl('master', masterLayoutCtl)
        cogLayoutCtl = control.Control(shape='circle', color='yellow', scale=[4, 4, 4],
                                      name=namer.name(d='cog_layout', s='ctl'), xformType='transform')
        cogLayoutCtl.xformNode().ty.set(5)
        self.registerControl('cog', cogLayoutCtl)  
        cogLayoutCtl.xformNode().setParent(masterLayoutCtl.xformNode())  

        cogJnt = pm.createNode('joint', name=namer.name(d='cog', r='bnd'))
        masterJnt = pm.createNode('joint', name=namer.name(d='master', r='bnd'))
        cogJnt.setParent(masterJnt)
        
        utils.snap(cogJnt, cogLayoutCtl.xformNode())
        pm.parentConstraint(cogLayoutCtl.xformNode(), cogJnt)                
        pm.parentConstraint(masterLayoutCtl.xformNode(), masterJnt)
        
        self.registerBindJoint('master', masterJnt)
        self.registerBindJoint('cog', cogJnt, parent=masterJnt)
        
        masterCtl = control.Control(shape='circle', color='lite blue', xformType='transform',
                                    scale=[4,4,4], name = namer.name(r='ctl', d='cog'))
        masterCtl.xformNode().setParent(masterLayoutCtl.xformNode())
        
        bodyCtl = control.Control(shape='triangle', color='green', xformType='transform',
                                  scale=[3.5, 3.5, 3.5], name=namer.name(r='ctl', d='body'))
        bodyCtl.xformNode().setParent(cogLayoutCtl.xformNode())
                                    
        pivotCtl = control.Control(shape='jack', color='yellow', xformType='transform', scale=[2,2,2],
                                   name=namer.name(r='ctl', d='body_pivot'))
        pivotCtl.xformNode().setParent(cogLayoutCtl.xformNode())
                                    
        cogCtl = control.Control(shape='triangle', color='green', xformType='transform', scale=[2,2,2],
                                 name=namer.name(r='ctl', d='cog'))
        cogCtl.xformNode().setParent(cogLayoutCtl.xformNode())
        
        self.registerControl('master', masterCtl, ctlType='rig')
        self.registerControl('body', bodyCtl, ctlType='rig')
        self.registerControl('pivot', pivotCtl, ctlType='rig')
        self.registerControl('cog', cogCtl, ctlType='rig')
        
    def _makeRig(self, namer, bndJnts, rigCtls):
        #set up the positions of the controls
        
        ctlToks = rigCtls.keys()

        bndJnts['cog'].setParent(None)
        pm.delete(bndJnts['master'])
        for tok in ['body', 'pivot', 'cog']:
            #snap the nodes to the cog but keep the shape positions
            rigCtls[tok].snap(bndJnts['cog'])
            
        #we no longer need the control objects.  replace them with the xform nodes    
        for tok, ctl in rigCtls.items():
            rigCtls[tok] = ctl.xformNode()
        
        rigCtls['body'].setParent(rigCtls['master'])
        rigCtls['pivot'].setParent(rigCtls['body'])
        rigCtls['cog'].setParent(rigCtls['pivot'])
        utils.insertNodeAbove(rigCtls['body'])
        
        #create the inverted pivot
        name = namer.name(d='pivot_inverse')
        pivInv = utils.insertNodeAbove(rigCtls['cog'], name=name)        
        mdn = pm.createNode('multiplyDivide', n=namer.name(d='piv_inverse', s='mdn'))
        mdn.input2.set([-1,-1,-1])
        rigCtls['pivot'].t.connect(mdn.input1)
        mdn.output.connect(pivInv.t)        
        
        #constrain the cog jnt to the cog ctl
        bndJnts['cog'].setParent(rigCtls['master'])
        pm.pointConstraint(rigCtls['cog'], bndJnts['cog'])
        pm.orientConstraint(rigCtls['cog'], bndJnts['cog'])

        #add master attrs
        rigCtls['master'].addAttr('uniformScale', min=0.001, dv=1, k=1)
        for channel in ['sx', 'sy', 'sz']:
            rigCtls['master'].uniformScale.connect(getattr(rigCtls['master'], channel))
            
        #assign the nodes:
        for tok in ctlToks:
            self.setParentNode('%s_ctl' % tok, rigCtls[tok])
        self.setParentNode('cog_bnd', bndJnts['cog'])

        #tag controls
        for ctl in rigCtls.values():
            NT.tagControl(ctl, uk=['tx', 'ty', 'tz', 'rx', 'ry', 'rz'])
        NT.tagControl(rigCtls['master'], uk=['uniformScale'])
        #setup info for parenting
        self.setNodeCateogry(rigCtls['master'], 'fk')
        

class Rig(utils.Types.TreeModel):
    '''
    A character tracks widgets, organizes the build, etc
    import pymel.core as pm
    import beings.control as C
    import beings.leg as L
    import beings.utils as U
    reload(U)
    reload(C)
    reload(L)
    pm.newFile(force=1)

    ll = L.LegLayout()
    ll2 = L.LegLayout(side='rt')

    rig = L.Rig('mycharacter')
    rig.addWidget(ll)
    rig.addWidget(ll2)
    rig.setParent(ll, ll2, 'bnd_hip')
    rig.buildRig()

    '''
    #a dummy object used as the 'root' of the rig
        
    def __init__(self, charName, rigType='core', buildStyle='standard'):
        super(Rig, self).__init__()

        self._charNodes = {}
        self._rigType = 'core'
        self._coreNodes = {}
        
        self.options = utils.Types.OptionCollection()
        self.options.addOpt('char', 'defaultcharname')
        self.options.setOpt('char', charName)
        self.options.addOpt('rigType', 'core')
        self.options.setOpt('rigType', rigType)
        self.options.addOpt('buildStyle', 'standard')
        self.options.setOpt('buildStyle', buildStyle)
        
        self.cog = CenterOfGravity()
        self.cog.options.setOpt('char', self.options.getOpt('char'))        
        self.addWidget(self.cog)
    
    def addWidget(self, widget, parent=None, parentNode=None):        
        if parent is None:
            parent = self.root
            parentNode = ""
        parent.insertChild(widget, parentNode)
        widget.options.setOpt('char', self.options.getOpt('char'))        
        
    def buildLayout(self):
        for wdg in self.root.childWidgets():
            if wdg.state() == 'rigged':
                wdg.delete()
            wdg.buildLayout()
            
    def buildRig(self, lock=False):
        self._buildMainHierarhcy()
        for wdg in self.root.childWidgets():            
            wdg.buildRig()

        self._doParenting()
        if lock:
            NT.lockHierarchy(self._coreNodes['top'])
            
    def _getChildWidgets(self, parent=None):
        '''Get widgets that are children of parent.'''
        result = []
        for wdgName, parentTup in self._parents.items():
            if parentTup[0] == parent:
                result.append(wdgName)
        return result
    
    def _doParenting(self):
        '''
        Parent rigs to each other
        '''
        for child in self.root.childWidgets(recursive=True):
            parent = child.parent
            if parent == self.root:
                for node in child.getNodes('fk'):
                    node.setParent(self._coreNodes['top'])
                for node in child.getNodes('ik'):
                    node.setParent(self._coreNodes['top'])
                
            else:
                for node in child.getNodes('dnt'):
                    node.setParent(self._coreNodes['dnt'])
                for node in child.getNodes('ik'):
                    node.setParent(self.cog.getParentNode('master_ctl'))
                
                row = parent.rowOfChild(child)
                parentPart = parent.childAtRow(row, returnIndex=child.CHILD_PART_INDEX)
                parentNode = parent.getParentNode(parentPart)
                for node in child.getNodes('fk'):
                    node.setParent(parentNode)
                
    def _buildMainHierarhcy(self):
        '''
        build the main group structure
        '''
        rigType = '_%s' % self.options.getOpt('rigType')
        char = self.options.getOpt('char')
        top = pm.createNode('transform', name='%s%s_rig' % (char, rigType))
        self._coreNodes['top'] = top
        dnt = pm.createNode('transform', name='%s%s_dnt' % (char, rigType))
        dnt.setParent(top)
        self._coreNodes['dnt'] = dnt
        model = pm.createNode('transform', name='%s%s_model' % (char, rigType))
        model.setParent(dnt)
        self._coreNodes['model'] = model

_testInst = None
def treeTest():
    class TreeTest(QTreeView):
        def __init__(self, parent=None):
            super(TreeTest, self).__init__(parent)
            self.rig = Rig('mychar')
            self.setModel(self.rig)
            leg = BasicLeg()
            leg2 = BasicLeg()
            self.rig.addWidget(leg, self.rig.cog, 'cog_bnd')
            self.rig.addWidget(leg2, self.rig.cog, 'cog_bnd')            
            self.rig.reset()
            self.setAnimated(True)
            
    global _testInst
    _testInst = TreeTest()
    _testInst.show()

