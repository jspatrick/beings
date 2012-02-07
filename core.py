"""
The core widget and rig objects that custom widgets should inherit
"""
import logging, re, copy, os, sys, __builtin__
import pymel.core as pm
from PyQt4 import QtCore

import beings.control as control
import beings.utils as utils

import utils.NodeTagging as NT


_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO)


#set up logging

class BeingsFilter(logging.Filter):
    def __init__(self, name=''):
        logging.Filter.__init__(self, name=name)
    def filter(self, record):
        '''Add contextual info'''
        msg = '[function: %s: line: %i] : %s' % (record.funcName, record.lineno, record.msg)
        record.msg= msg
        return True
    
def _setupLogging():
    rootLogger = logging.getLogger()
    if rootLogger.getEffectiveLevel() == 0:
        rootLogger.setLevel(logging.INFO)
    _beingsRootLogger = logging.getLogger('beings')
    if _beingsRootLogger.getEffectiveLevel() == 0:
        _beingsRootLogger.setLevel(logging.INFO)

    for fltr in _beingsRootLogger.filters:
        _beingsRootLogger.removeFilter(fltr)    
    _beingsRootLogger.addFilter(BeingsFilter())
_setupLogging()

class WidgetRegistry(object):
    """Singleton that keeps data about widgets that are part of the system"""
    instance = None
    def __new__(cls, *args, **kwargs):
        if cls != type(cls.instance):
            cls.instance = super(WidgetRegistry, cls).__new__(cls, *args, **kwargs)
            cls.instance._widgets = {}
            cls.instance._descriptions = {}
        return cls.instance

    def register(self, class_, niceName=None, description=None):        
        if niceName is None:
            niceName = class_.__name__
        if description is None:
            description = 'No description provided'
        if niceName in self._widgets.keys() and \
               self._widgets[niceName] != class_:
            _logger.warning("%s is already registered" % niceName)
            return False

        else:
            _logger.info("Registering '%s'" % niceName)
            
        self._widgets[niceName] = class_
        self._descriptions[niceName] = class_
        
    def widgetName(self, instance):
        """Get the widget name from the instnace"""
        cls = instance.__class__
        for k, v in self._widgets.items():
            if v == cls:
                return k
    def widgetNames(self):
        return self._widgets.keys()
    def getInstance(self, widgetName):
        return self._widgets[widgetName]()
    def getDescription(self, widgetName):
        return self._descriptions[widgetName]    

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
        self._lockedToks = []
        if toks:
            self.setTokens(**toks)
            
    def lockToks(self, *toks):
        """Do not allow overriding tokens"""
        for tok in toks:
            self._lockedToks.append(self._fullToken(tok))
    def unlockToks(self, *toks):
        for tok in toks:
            tok = self._fullToken(tok)
            try:
                index = self._lockedToks.index(tok)
                self._lockedToks.pop(index)
            except ValueError:
                _logger.debug("%s is not locked" % tok)
                
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
        """Get a string name
        @param force=False:  force overrides on locked tokens"""
        #
        force = kwargs.pop('force', False)
        
        nameParts = copy.copy(self.__namedTokens)
        for tok, val in kwargs.items():
            fullTok = self._fullToken(tok)
            #check if locked
            if fullTok in self._lockedToks and not force:                
                _logger.warning("Token '%s' is locked, cannot override with '%s'" \
                                % (fullTok, val))
            else:
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

class OptionCollection(QtCore.QObject):
    def __init__(self, parent=None):
        '''
        A collection of options
        '''
        super(OptionCollection, self).__init__(parent)
        self.__options = {}
        self.__presets = {}
        self.__rules = {}
        self.__optPresets = {}
        self.__defaults = {}
    
    def addOpt(self, optName, defaultVal, optType=str, **kwargs):
        self.__options[optName] = optType(defaultVal)
        self.__defaults[optName] = optType(defaultVal)        
        self.__rules[optName] = {'optType': optType}        
        presets = kwargs.get('presets')
        if presets:
            self.setPresets(optName, *presets)
        if not kwargs.get('quiet'):
            self.emit(QtCore.SIGNAL('optionAdded'), optName)
        
    def _checkName(self, optName):
        if optName not in self.__options:
            raise utils.BeingsError("Invalid option %s") % optName
    
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
    
    def getValue(self, optName):
        self._checkName(optName)
        return self.__options[optName]
    
    def setValue(self, optName, val, quiet=False):
        self._checkName(optName)
        changed=False
        if val != self.__options[optName]:
            changed = True
        oldVal = self.__options[optName]
        
        if not quiet:            
            if changed:
                self.emit(QtCore.SIGNAL('optAboutToChange'), optName, oldVal, val)

        self.__options[optName] = val
        
        if not quiet:
            self.emit(QtCore.SIGNAL('optSet'), optName, val)
            if changed:
                self.emit(QtCore.SIGNAL('optChanged'), optName, oldVal, val)
            
    #TODO:  Get option data
    def getData(self):
        '''Return the values of all options not set to default values'''
        return copy.deepcopy(self.__options)
    
    def setFromData(self, data):
        '''
        Set options based on data gotten from getData
        '''
        for opt, val in data.items():
            self.setValue(opt, val)
            
    def getAllOpts(self):
        return copy.deepcopy(self.__options)
    def setAllOpts(self, optDct):
        for optName, optVal in optDct.items():
            self.setValue(optName, optVal)

    
class TreeItem(QtCore.QObject):
    """
    A tree item.

    Tree items must define their available plugs.  When children are added, they are added
    to a particular plug in the parent item.  Plugs must be configured on the TreeItem instances
    before children are added.
        
    The root tree item may have a null     plug ("").  As soon as the item is not a root, this null
    plug is removed.
    """
    def __init__(self, plugs=[]):
        super(TreeItem, self).__init__(parent=None)
        if not plugs:
            plugs = []    
        self.__parent = None        
        self.__plugs = set([str(p) for p in plugs])
        
        self.__children = []
        self.__childPlugs = []
                                
        
    def plugs(self): return list(self.__plugs)
    def addPlug(self, plugName): 
        self.__plugs.add(str(plugName))        
    def rmPlug(self, plugName): self.__plugs.difference_update(str(plugName))
    def parent(self): return self.__parent    
    def _setParent(self, parent):
        self.__parent = parent
        
    def children(self, recursive=False):
        result = []
        for child in self.__children:            
            if recursive:
                result.extend(child.children())
            result.append(child)
        return result
       
    def childIndex(self, child):
        return self.__children.index(child)
    
    def root(self):
        node = self
        while node.__parent is not None:
            node = node.__parent
        return node
    
    def addedChild(self, child):
        """Callback when a child is added"""
        self.root().emit(QtCore.SIGNAL('addedChildToHierarchy'), self, child)
        
    def removedChild(self, child):
        """Callback after a child is removed"""
        self.root().emit(QtCore.SIGNAL('removedChildFromHierarchy'), self, child)
     
    def addChild(self, child, plug=""):        
        if not self.__plugs:
            raise RuntimeError("must add plugs to the parent before adding a child")
        if not plug:
            _logger.debug("plug not specified, using first available")
            plug = self.plugs()[0]
        elif plug not in self.plugs():
            raise KeyError("Invalid plug '%s'" % plug)

        #don't allow the same instance in the tree twice
        root = self.root()
        ids = [id(w) for w in root.children(recursive=True)]
        ids.append(id(root))
        if id(child) in ids:
            raise RuntimeError("Cannot add the same instance twice")
        
        child._setParent(self)        
        self.__children.append(child)
        self.__childPlugs.append(plug)
        self.addedChild(child)
        
    def rmChild(self, child, reparentChildren=False):
        """
        Remove a child
        @param reparentChildren=True: if True, reparent child's children to the this obj.
        """
        
        if reparentChildren:
            grandChildren = child.children(recursive=False)
            plug = self.plugs()[0]
            
            for grandChild in grandChildren:
                child.rmChild(grandChild)
                self.addChild(grandChild, plug=plug)
    
        index = self.childIndex(child)
        self.__children.pop(index)
        self.__childPlugs.pop(index)
        child._setParent(None)
        self.removedChild(child)        
        return child
    
    def plugOfChild(self, child): return self.__childPlugs[self.childIndex(child)]
    def setChildPlug(self, child, plug):
        if plug not in self.plugs():
            _logger.warning("invalid plug '%s'" % plug)
            return False
        index = self.childIndex(child)
        self.__childPlugs[index] = plug
        
class Widget(TreeItem):
    '''
    A tree item that builds things in Maya.

    Builds happen top down, meaning that nodes at the root of the
    tree build themselves, then call children to build themselves.

    When children have finished building, they alert their parents
    via a childCompletedBuild method.  Parents can then query children
    on the nodes they have built, and parent these nodes into their
    hierarchies.

    
    '''
    BUILD_TYPES = ['layout', 'rig']
    VALID_NODE_CATEGORIES = ['master', 'dnt', 'cog', 'parent', 'ik']
    def __init__(self, part='widget', plugs=None):
        super(Widget, self).__init__(plugs=plugs)
        
        #set up options
        self.options = OptionCollection()
        self.__origPartName = part
        self.options.addOpt('part', part)
        self.options.addOpt('side', 'cn', presets=['cn', 'lf', 'rt'])
        self.options.addOpt('char', 'defaultchar')
        self.connect(self.options, QtCore.SIGNAL('optChanged'), self._optionChanged)
        self.connect(self.options, QtCore.SIGNAL('optAboutToChange'), 
                     self._optionAboutToChange)
        
        self._nodes = [] #stores all nodes
        self.__state = 'unbuilt'        
        self._bindJoints = {} #stores registered bind joints
        self._differs = {'rig': control.Differ(), 'layout': control.Differ()}
        self._cachedDiffs = {'rig': {}, 'layout': {}}
        
        #widgets have a couple places they store nodes when build.  These are
        #cleared when the widget is deleted
        #widgets need to register the actual node that belongs
        #to a plug.
        self.__plugNodes = {}
        #widgets may need to keep track of other special nodes.  This is a safe
        #place to keep them, as it's cleared when the rig is deleted  
        self._otherNodes = {}
        
        #when built, build nodes are added to categories if they need to be
        #operated upon by parents
        self._nodeCategories = {}
        self._nodeStatus = {}
        #nodes are added to catgories in a tuple of (node, 'unhandled')
        #or (node, 'handled') 
        for categoy in self.VALID_NODE_CATEGORIES:
            self._nodeCategories[categoy] = []
            
        #is the widget mirrored?
        self._mirroring = ''
    
    def removedChild(self, child):
        child._mirroring = ''
        super(Widget, self).removedChild(child)
        
    def addParentPart(self, part): self.addPlug(part)
    def setParentNode(self, part, node):
        if part not in self.plugs():
            raise RuntimeError("invalid plug '%s'" % part)
        self.__plugNodes[part] = node
        
    def plugNode(self, plug):
        return self.__plugNodes.get(plug, None)

    def addChild(self, child, plug=""):        
        result = super(Widget, self).addChild(child, plug=plug)
        try:
            assert isinstance(child, Widget)
            child.options.setValue('char', self.options.getValue('char'))
        except AssertionError:
            _logger.debug("Parening non-Widget to %r" % self)
        return result
    
    def _optionChanged(self, opt, oldVal, newVal):
        #if the char is changed on any node, it should be changed for all nodes in the hierarchy
        if opt == 'char':
            root = self.root()
            allNodes = root.children(recursive=True) + [root]
            for node in allNodes:
                if hasattr(node, "options"):
                    if node.options.getValue('char') != newVal:
                        node.options.setValue('char', newVal, quiet=True)
        
    def _optionAboutToChange(self, opt, oldVal, newVal):
        #if changing the part or side invalidates mirroring, set it         
        if opt == 'part' or opt == 'side':
            if self._mirroring: 
                other = self._getMirrorableWidget()
                if other:
                    other._mirroring = ''
                self._mirroring = ''
            
                
    def __validateChildSettings(self):
        """
        Validate that all options are appropriately set before doing a build
        """
        children = self.children(recursive=True)
        usedNames = {}
        for child in children:            
            part = child.options.getValue('part')
            side = child.options.getValue('side')
            name = '%s_%s' % (part, side)            
            if name in usedNames:
                raise RuntimeError("Cannot build; part %s and side %s used in %r and %r" \
                                   %(part, side, usedNames[name], child))
            else:
                usedNames[name] = child
        
    def notify(self, buildType):
        #notify relatives
        parent = self.parent()
        if parent:
            if hasattr(parent, 'childCompletedBuild'):
                parent.childCompletedBuild(self, buildType)
        for child in self.children():
            if hasattr(child, 'parentCompletedBuild'):
                child.parentCompletedBuild(self, buildType)
                
    
    def childCompletedBuild(self, child, buildType):
        #do parenting
        _logger.debug("Child %s complete %s build" % (child, buildType))
        if buildType == 'rig':
            plug = self.plugOfChild(child)
            parentNode = self.__plugNodes[plug]
             
            for node in child.getNodes('parent'):
                node.setParent(parentNode)            
                    
    def parentCompletedBuild(self, parent, buildType):
        if buildType == 'layout':
            if self._mirroring == 'source':
                other = self._getMirrorableWidget()
                self.mirror(other)
        
    def name(self):
        """ Return a name of the object."""        
        part = self.options.getValue('part')
        side = self.options.getValue('side')
        return '%s_%s' % (part, side)

    def __repr__(self):
        return "%s('%s')" % \
               (self.__class__.__name__, self.name())

    def __str__(self):
        return "%s('%s')" % \
               (self.__class__.__name__, self.name())
    
    @BuildCheck('layoutBuilt')
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
        char = self.options.getValue('char')
        side = self.options.getValue('side')
        part = self.options.getValue('part')        
        
        namer = Namer(c=char, s=side, p=part, r='bnd')
        for tok, jnt in result.items():
            jnt.rename(namer.name(d=tok))
        self._prepBindJoints(result)            
        return result

    def _prepBindJoints(self, jntDct):
        '''freeze the joints  {layoutBindJntName: newBindJntPynode}'''
        for jnt in jntDct.values():
            pm.makeIdentity(jnt, apply=1, t=1, r=1, s=1, n=1)
        
    def getNodes(self, category=None):
        nodes = []
        #don't warn about non-existing nodes
        with utils.SilencePymelLogger():
            if category is not None:
                if category not in self._nodeCategories.keys():
                    raise utils.BeingsError("Invalid category %s" % category)
                #return a copy of the list
                nodes = [n for n in self._nodeCategories[category] if pm.objExists(n)]
                self._nodeCategories[category] = copy.copy(nodes) # set it to the existing objs

                if category == 'parent':
                    otherCategoryNodes = set([])
                    for grp in self._nodeCategories.values():
                        otherCategoryNodes.update(grp)

                    for n in self.getNodes():
                        if isinstance(n, pm.nt.DagNode) and not n.getParent():
                            if n not in otherCategoryNodes:
                                _logger.warning("Directly parenting uncategoried top-level node '%s'"\
                                                % n.name())
                                nodes.append(n)                                

            else:
                nodes = self._nodes
                nodes = [n for n in nodes if pm.objExists(n)]
                self._nodes = copy.copy(nodes)
            
        return nodes
    
    def state(self): return self.__state

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
        # if parent:
        #     parent = checkName(parent)
        self._bindJoints[name] = [jnt, None]

        #setup parenting
        allJnts = [jnts[0] for jnts in self._bindJoints.values()]
        for key, jntPr in self._bindJoints.items():
            jnt = jntPr[0]
            par = jnt.getParent()
            if par in allJnts:
                self._bindJoints[key] = [jnt, par]                

    def registerControl(self, name, ctl, ctlType ='layout'):
        """Register a control that should be cached"""        
        ctlDiffer = self._differs[ctlType]
        if ctlType == 'layout':
            #we don't need to keep track of layout controls world matrices
            ctlDiffer.addObj(name, ctl, skip=['worldMatrix'])
        else:
            ctlDiffer.addObj(name, ctl)
        #add to display layer
        globalNode = control.layoutGlobalsNode()
        if ctlType == 'layout':
            #for shape in control.getShapeNodes(ctl):                
            globalNode.layoutControlVis.connect(ctl.v)
        elif ctlType == 'rig':
            ###for shape in control.getShapeNodes(ctl):                
            globalNode.rigControlVis.connect(ctl.v)

    
    def buildLayout(self, useCachedDiffs=True, altDiffs=None, children=True):
        if self.state() != 'unbuilt':
            if self.state() == 'layoutBuilt':
                self.cacheDiffs()            
            self.delete()
        
        self.__validateChildSettings()
        
        side = self.options.getValue('side')
        part = self.options.getValue('part')
        namer = Namer()
        namer.setTokens(side=side, part=part)        
        self._bindJoints = {}
        result = None
        with utils.NodeTracker() as nt:
            try:
                result = self._makeLayout(namer)
                self.__state = 'layoutBuilt'
            finally:
                self._nodes = nt.getObjects()

        #reset the differ
        for differ in self._differs.values():
            differ.setInitialState()
 
        for jntPr in self._bindJoints.values():
            node = jntPr[0]
            node.overrideEnabled.set(1)
            node.overrideDisplayType.set(2)
            
        if altDiffs is not None:
            self.applyDiffs(altDiffs)
        elif useCachedDiffs:
            self.applyDiffs(self._cachedDiffs)
        
        if children:
            for child in self.children():
                child.buildLayout()
        #notify relatives build finished
        self.notify('layout')
        
        return result
    
    def _makeLayout(self, namer):
        """
        build the layout
        """
        raise NotImplementedError    
    @BuildCheck('layoutBuilt', 'rigBuilt')
    def delete(self, cache=True):
        """
        Delete nodes
        """
        for child in self.children(recursive=True):
            child.delete(cache=cache)

        if cache:
            if self.state() == 'rigBuilt':
                _logger.debug('deleting a rig - skipping caching')
            else:
                self.cacheDiffs()
        #silence the pymel logger or it's pretty noisy about missing nodes
        with utils.SilencePymelLogger():
            for node in self.getNodes():
                if pm.objExists(node):
                    pm.delete(node)
        self._nodes = []
        self.__plugNodes = {}
        self._otherNodes = {}        
        for category in self.VALID_NODE_CATEGORIES:
            self._nodeCategories[category] = []
        self._nodeStatus = {}
        self.__state = 'unbuilt'
        
    @BuildCheck('layoutBuilt')    
    def cacheDiffs(self):
        """
        Store tweaks internally
        """
        self._cachedDiffs['rig'] = self._differs['rig'].getDiffs()
        self._cachedDiffs['layout'] = self._differs['layout'].getDiffs()
        #if this is mirrored, cache diffs on other rig too
        if self.mirroredState() == 'source':
            other = self._getMirrorableWidget()
            if other:
                other.cacheDiffs()
                
    def setDiffs(self, diffDct):
        """Set diffs"""
        self._cachedDiffs = diffDct
        
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

    @BuildCheck('layoutBuilt')
    def applyDiffs(self, diffDict):
        """
        Apply tweaks
        """
        rigDiffs = diffDict['rig']
        layoutDiffs = diffDict['layout']
        self._differs['rig'].applyDiffs(rigDiffs)
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
    
    #TODO:  Move node statuses and categories into a new class - this one is
    #way too big.
    def nodeStatus(self, node):
        """Set the status of a node."""
        status = self._nodeStatus.get(node, 'unhandled')
        
    def setNodeStatus(self, node, status):
        """Get the status of a node"""
        if status not in  ['handled', 'unhandled']:
            raise utils.BeingsError("Invalid status '%s'" % status)         
        status = self._nodeStatus[node] = status
        
    def buildRig(self, altDiffs=None, returnBeforeBuild=False, skipCallbacks=False):
        """build the rig
        @param altDiffs=None: Use the provided diff dict instead of the internal diffs
        @param returnBeforeBuild=False:  for developing rig methods.  Returns the args
        passed tot he _makeRig method"""
        self.__validateChildSettings()
        
        if self.state() == 'rigBuilt':
            self.delete()
            
        if self.state() != "layoutBuilt":
            self.buildLayout(altDiffs=altDiffs)
        else:
            if altDiffs:
                self.delete()
                self.buildLayout(altDiffs=altDiffs)
            else:
                self.cacheDiffs()
        #this seems to be a bug - if refresh isn't called, there is some odd behavior when things
        #are dupicated
        pm.refresh()
        
        namer = Namer()
        namer.setTokens(c=self.options.getValue('char'),
                        n='',
                        side=self.options.getValue('side'),
                        part=self.options.getValue('part'))
        namer.lockToks('c', 'n', 's', 'p') # makes sure they can't be changed by overridden methods

        #get the rig control data
        rigCtlData = control.getRebuildData(self._differs['rig'].getObjs())
        
        #duplicate the bind joints, and delete the rest of the rig
        bndJntNodes = []
        with utils.NodeTracker() as nt:
            jntDct = self.duplicateBindJoints()
            bndJntNodes = nt.getObjects()
        self.delete()
        
        #rename the joints according to the tokens they were registered with
        for tok, jnt in jntDct.items():
            jnt.rename(namer.name(d=tok, r='bnd'))
            
        with utils.NodeTracker() as nt:            
            #re-create the rig controls
            #TODO:  we should really pass a namer in here
            rigCtls = control.buildCtlsFromData(rigCtlData, prefix='%s_' % namer.getToken('c'))

            #kwarg for debugging
            if returnBeforeBuild:
                return  (namer, jntDct, rigCtls)
            
            #make the rig            
            result = self._makeRig(namer, jntDct, rigCtls)
            self.__state = 'rigBuilt'
            
            nodes = nt.getObjects()
            nodes.extend(bndJntNodes)
            with utils.SilencePymelLogger():
                self._nodes = [n for n in nodes if pm.objExists(n)]
            
        #Check that the rig was created properly
        for plug in self.plugs():
            if plug not in self.__plugNodes:            
                _logger.warning("The '%s' plug was not assigned a a node" % plug)
        
        #build children
        for child in self.children():
            child.buildRig(skipCallbacks=skipCallbacks)
        
        #notify relatives that build finished
        if not skipCallbacks:
            self.notify('rig')
        
        return result
                            
    def _makeRig(self, namer, bndJnts, rigCtls):
        raise NotImplementedError
    
    def setMirrored(self, val=True):
        """
        If the widget has a side and a similarly named widget on the opposite side
        is available, mirror it
        """
        if not val:
            self._mirroring = ''
            return
        _logger.debug("Mirroring %s" % self)
        other = self._getMirrorableWidget()
        if not other:
            _logger.info("No sibling widget with same part name and opposite side")
            return
        self._mirroring = 'source'
        other._mirroring = 'target'
        
    def _getMirrorableWidget(self):
        """Get the mirror-able sibling"""
        siblings = [w for w in self.parent().children(recursive=False) if w is not self]
        part = self.options.getValue('part')
        side = self.options.getValue('side')
        if side == 'lf':
            findSide = 'rt'
        elif side == 'rt':
            findSide = 'lf'
        else:
            _logger.info("Cannot mirror 'center' widgets")
            return
        for sibling in siblings:
            if sibling.options.getValue('part') == part and \
               sibling.options.getValue('side') == findSide:
                return sibling
        return None
    
    def mirroredState(self): return self._mirroring
    
    @BuildCheck('layoutBuilt')
    def mirror(self, other):
        '''
        Mirror this widget to another widget.  this assumes controls are in world space.
        Templates mirrored controls
        '''
        thisCtlDct = self._differs['layout'].getObjs()
        otherCtlDct = other._differs['layout'].getObjs()
        thisRigDct = self._differs['rig'].getObjs()
        otherRigDct = other._differs['rig'].getObjs()
        
        direct = ['tz', 'ty', 'rx', 'sx', 'sy', 'sz']
        inverted = ['tx', 'ry', 'rz']
        namer = Namer(c=self.options.getValue('char'),
                      s=self.options.getValue('side'),
                      p=self.options.getValue('part'))
        
        for thisDct, otherDct in [(thisCtlDct, otherCtlDct), (thisRigDct, otherRigDct)]:
            for k, thisCtl in thisDct.items():
                otherCtl = otherDct.get(k, None)
                otherCtl.template.set(1)
                if not otherCtl:
                    _logger.warning("Cannot mirror '%s' - it is not in the other rig" % k)
                    continue

                for attr in direct:
                    try:
                        pm.connectAttr('%s.%s' % (thisCtl, attr),
                                       '%s.%s' % (otherCtl, attr))
                    except RuntimeError:
                        pass
                    except Exception, e:
                        _logger.warning("Error during connection: %s" % str(e))                    

                for attr in inverted:                                
                    fromAttr = '%s.%s' % (thisCtl, attr)
                    toAttr = '%s.%s' % (otherCtl, attr)
                    char = self.options.getValue('char')
                    side = self.options.getValue('char')
                    mdn = pm.createNode('multiplyDivide',
                                        n=namer.name(d='%s%sTo%s%s' % (thisCtl,attr,otherCtl,attr)))

                    mdn.input2X.set(-1)
                    mdn.operation.set(1)
                    pm.connectAttr(fromAttr, mdn.input1X)
                    try:
                        pm.connectAttr(mdn.outputX, toAttr)                    
                    except RuntimeError:
                        pm.delete(mdn)                
                    except Exception, e:
                        _logger.warning("Error during connection: %s" % str(e))
                        pm.delete(mdn)
                    else:
                        self._nodes.append(mdn)

class Root(Widget):
    """Builds a master control and main hierarchy of a rig"""
    def __init__(self, part='master'):
        super(Root, self).__init__(part=part)
        self.options.setPresets('side', 'cn')
        self.addParentPart('master')
        self.options.addOpt('rigType', 'core', presets=['core'])
        
    def childCompletedBuild(self, child, buildType):
        pm.refresh()
        if buildType == 'rig':
            if self.root() == self:
                children = child.children(recursive=True) + [child]
                for child in children:                
                    masterNodes = child.getNodes('master')
                    if masterNodes:     
                        pm.parent(masterNodes, self._otherNodes['top'])
                    dntNodes = child.getNodes('dnt')
                    if dntNodes:
                        pm.parent(dntNodes, self._otherNodes['dnt'])
                    ikNodes = child.getNodes('ik')
                    for node in ikNodes:
                        if child.nodeStatus(node) != 'handled':
                            pm.parent(node, self.plugNode('master'))
        pm.refresh()
        super(Root, self).childCompletedBuild(child, buildType)
               
    def _makeLayout(self, namer):
        #mkae the layout control
        masterLayoutCtl = control.makeControl(shape='circle',
                                             color='red',
                                             scale=[4.5, 4.5, 4.5],
                                             name=namer.name(d='master_layout', s='ctl'),
                                             xformType='transform')        
        self.registerControl('master', masterLayoutCtl)
        masterJnt = pm.createNode('joint', name=namer.name(d='master', r='bnd'))
        self.registerBindJoint('master', masterJnt)
        
        #make rig control        
        masterCtl = control.makeControl(shape='circle',
                                       color='lite blue',
                                       xformType='transform',
                                       scale=[4,4,4], name = namer.name(r='ctl', d='master'))
        masterCtl.setParent(masterLayoutCtl)
        self.registerControl('master', masterCtl, ctlType='rig')

    def _makeRig(self, namer, bndJnts, rigCtls):
        self.setParentNode('master', rigCtls['master'])
        if self.root() == self:
            rigType = self.options.getValue('rigType')
            top = pm.createNode('transform', 
                                name=namer.name(d=rigType, p='', 
                                                s='',x='rig', force=True))            
            self._otherNodes['top'] = top
            dnt = pm.createNode('transform', 
                                name=namer.name(d=rigType, p='', 
                                                s='', x='dnt', force=True))
            dnt.setParent(top)
            self._otherNodes['dnt'] = dnt
            
        
            rigCtls['master'].setParent(top)
            
        #add master attrs
        rigCtls['master'].addAttr('uniformScale', min=0.001, dv=1, k=1)
        for channel in ['sx', 'sy', 'sz']:
            rigCtls['master'].uniformScale.connect(getattr(rigCtls['master'], channel))
        for ctl in rigCtls.values():
            NT.tagControl(ctl, uk=['tx', 'ty', 'tz', 'rx', 'ry', 'rz'])
        NT.tagControl(rigCtls['master'], uk=['uniformScale'])
WidgetRegistry().register(Root, 'Root', 'The widget under which all others should be parented')
        
#TODO:  COG needs to catch child nodes with 'cog' category
class CenterOfGravity(Widget):
    def __init__(self, part='cog', **kwargs):
        super(CenterOfGravity, self).__init__(part=part, **kwargs)
        self.options.setPresets('side', 'cn')
        self.addParentPart('cog_bnd')
        self.addParentPart('cog_ctl')        
        self.addParentPart('body_ctl')
        self.addParentPart('pivot_ctl')
        
    def childCompletedBuild(self, child, buildType):
        """Find all child nodes set to 'cog' or 'ik'"""
        pm.refresh()
        if buildType == 'rig':
            if self.root() == self:
                children = child.children(recursive=True) + [child]
                for child in children:            
                    cogNodes = child.getNodes('ik')
                    cogNodes.extend(child.getNodes('cog'))
                    if cogNodes:            
                        pm.parent(cogNodes, self.plugNode('cog_bnd'))
                        for node in cogNodes:
                            child.setNodeStatus(node, 'handled')
        pm.refresh()
        super(CenterOfGravity, self).childCompletedBuild(child, buildType)
        
    def _makeLayout(self, namer):
        
                
        cogLayoutCtl = control.makeControl(shape='circle',
                                          color='yellow',
                                          scale=[4, 4, 4],
                                          name=namer.name(d='cog_layout', s='ctl'),
                                          xformType='transform')
        cogLayoutCtl.ty.set(5)        
        self.registerControl('cog', cogLayoutCtl)
                
        cogJnt = pm.createNode('joint', name=namer.name(d='cog', r='bnd'))
        
        
        utils.snap(cogJnt, cogLayoutCtl)
        pm.parentConstraint(cogLayoutCtl, cogJnt)                
                
        self.registerBindJoint('cog', cogJnt)
        
        
        bodyCtl = control.makeControl(shape='triangle', color='green', xformType='transform',
                                  scale=[3.5, 3.5, 3.5], name=namer.name(r='ctl', d='body'))
        bodyCtl.setParent(cogLayoutCtl)
                                    
        pivotCtl = control.makeControl(shape='jack', color='yellow', xformType='transform', scale=[2,2,2],
                                   name=namer.name(r='ctl', d='body_pivot'))
        pivotCtl.setParent(cogLayoutCtl)
                                    
        cogCtl = control.makeControl(shape='triangle', color='green', xformType='transform', scale=[2,2,2],
                                 name=namer.name(r='ctl', d='cog'))
        cogCtl.setParent(cogLayoutCtl)
        
        
        self.registerControl('body', bodyCtl, ctlType='rig')
        self.registerControl('pivot', pivotCtl, ctlType='rig')
        self.registerControl('cog', cogCtl, ctlType='rig')
        
    def _makeRig(self, namer, bndJnts, rigCtls):
        #set up the positions of the controls
        
        ctlToks = rigCtls.keys()

        bndJnts['cog'].setParent(None)

        for tok in ['body', 'pivot', 'cog']:
            #snap the nodes to the cog but keep the shape positions
            control.snapKeepShape(bndJnts['cog'], rigCtls[tok])
                            
        rigCtls['pivot'].setParent(rigCtls['body'])
        rigCtls['cog'].setParent(rigCtls['pivot'])
        utils.insertNodeAbove(rigCtls['body'])
        
        #create the inverted pivot
        name = namer.name(d='pivot_inverse')
        pivInv = utils.insertNodeAbove(rigCtls['cog'], name=name)        
        mdn = pm.createNode('multiplyDivide', n=namer.name(d='piv_inverse', x='mdn'))
        mdn.input2.set([-1,-1,-1])
        rigCtls['pivot'].t.connect(mdn.input1)
        mdn.output.connect(pivInv.t)        
        
        #constrain the cog jnt to the cog ctl        
        pm.pointConstraint(rigCtls['cog'], bndJnts['cog'])
        pm.orientConstraint(rigCtls['cog'], bndJnts['cog'])
            
        #assign the nodes:
        for tok in ctlToks:
            self.setParentNode('%s_ctl' % tok, rigCtls[tok])
        self.setParentNode('cog_bnd', bndJnts['cog'])

        #tag controls
        
        #setup info for parenting
        self.setNodeCateogry(rigCtls['body'], 'parent')
        
WidgetRegistry().register(CenterOfGravity, 'Center Of Gravity', 'Put body widgets under this')



class RigModel(QtCore.QAbstractItemModel):
    '''
    Abstract item model for a rig 
    '''
    #a dummy object used as the 'root' of the rig
        
    def __init__(self, charname='mychar', parent=None):
        super(RigModel, self).__init__(parent=parent)
        self.root = Root()
        self.headers = ['Part', 'Side', 'Parent Part', 'Class', 'Mirrored']
        self._mimeDataWidgets = []
        self.connect(self.root, QtCore.SIGNAL('addedChildToHierarchy'), 
                     self._addedChild)
        self.connect(self.root, QtCore.SIGNAL('removedChildFromHierarchy'), 
                     self._removedChild)
        
    def _addedChild(self, parent, child):
        _logger.debug("Added child %r under parent %s" % (child, parent))
        #TODO: make this add rows
        self.reset()
    def _removedChild(self, parent, child):
        _logger.debug("Removed child %r under parent %s" % (child, parent))
        #TODO: make this rm rows
        self.reset()

    def index(self, row, col, parentIndex):
#        if not self.hasIndex(row, col, parentIndex):
#            return QtCore.QModelIndex()
        if not parentIndex.isValid():
            parent = self.root
        else:
            parent = parentIndex.internalPointer()
        child = parent.children()[row]
        return self.createIndex(row, col, child)
    
    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        widget = index.internalPointer()
        parent = widget.parent()
        if parent == self.root:
            return QtCore.QModelIndex()
        #get row of parent
        row = parent.parent().childIndex(parent)
        return self.createIndex(row, 0, parent)
        
    def rowCount(self, parentIndex):
        if parentIndex.column() > 0:
            return 0
        
        if not parentIndex.isValid():
            parent = self.root
        else:
            parent = parentIndex.internalPointer()
            
        return len(parent.children())
    
    def columnCount(self, parentIndex): return len(self.headers)
    def supportedDropActions(self):
        return QtCore.Qt.MoveAction | QtCore.Qt.CopyAction
    
    def flags(self, index):        
#        if not index.isValid():
#            return QtCore.Qt.ItemIsEnabled 
        flags =  QtCore.Qt.ItemIsEnabled | \
                QtCore.Qt.ItemIsSelectable | \
                QtCore.Qt.ItemIsEditable | \
                QtCore.Qt.ItemIsDragEnabled | \
                QtCore.Qt.ItemIsDropEnabled
                
        return flags
    
    def mimeTypes(self):
        types = QtCore.QStringList()
        types.append('application/x-widgetlist')
        types.append('application/x-widget-classname')
        return types
    
    def mimeData(self, indexList):
        widgets = []
        for i in range(len(indexList)):
            widgets.append(indexList[i].internalPointer())
        self._mimeDataWidgets = list(set(widgets))
        
        mimeData = QtCore.QMimeData()
        mimeData.setData("application/x-widgetlist", QtCore.QByteArray())
        return mimeData
    
    def dropMimeData(self, mimedata, action, row, column, parentIndex):
        if parentIndex.isValid():
            newParent = parentIndex.internalPointer()
        else:
            newParent = self.root
        
        if mimedata.hasFormat('application/x-widgetlist'):
            for widget in self._mimeDataWidgets:
                if widget.parent() is newParent:
                    continue
                
                widget.parent().rmChild(widget)
                newParent.addChild(widget)
                    
        elif mimedata.hasFormat('application/x-widget-classname'):
            data = mimedata.data('application/x-widget-classname')
            stream = QtCore.QDataStream(data, QtCore.QIODevice.ReadOnly)
            classname = QtCore.QString()
            stream >> classname        
            widget = WidgetRegistry().getInstance(str(classname))
            newParent.addChild(widget)
        return True
    
    def data(self, index, role):
        if not index.isValid():
            return QtCore.QVariant()
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        else:            
            widget = index.internalPointer()
            if index.column() == self.headers.index('Part'):                
                return QtCore.QVariant(widget.options.getValue('part'))
            if index.column() == self.headers.index('Side'):                
                return QtCore.QVariant(widget.options.getValue('side'))
            if index.column() == self.headers.index('Parent Part'):
                plug = widget.parent().plugOfChild(widget)
                return QtCore.QVariant(plug)
            if index.column() == self.headers.index('Class'):
                return QtCore.QVariant(widget.__class__.__name__)
            if index.column() == self.headers.index('Mirrored'):
                return QtCore.QVariant(widget.mirroredState())
            
            
            return QtCore.QVariant("Test..")
        
    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False
        
        widget = index.internalPointer()        
        header = self.headers[index.column()]
        value = str(value.toString())
        if header == 'Part':
            widget.options.setValue('part', value)
            
        if header == 'Side':                        
            if value not in widget.options.getPresets('side'):
                _logger.warning('invalid side "%s"' % value)
            else:
                widget.options.setValue('side', value)
                
        if header == 'Parent Part':
            parent = widget.parent()
            parent.setChildPlug(widget, value)
        
        self.emit(QtCore.SIGNAL("dataChanged(QModelIndex, QModelIndex)"), index, index)
        return True
        
    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant(self.headers[section])
        return QtCore.QVariant()

    def getBadNames(self):
        """
        Return a list of [('badID', widget)] for all widgets with a duplicate or invalid name
        """
        
        allWidgets = self.root.childWidgets()
        result = []
        IDs = []
        for widget in allWidgets:
            name = widget.name()
            if name not in IDs:
                IDs.append(name)
            else:
                result.append(name)
        return result
    
def getSaveData(widget):
    '''
    Get widget data needed to reconstruct the rig
    starting at root, for each child get:
    id: {parentWidgetID,
         parentNode,
         registered name,
         optionData,
         diffData}    
    '''
    result = {}
    allWidgets = widget.children(recursive=True) + [widget]
    for widget in allWidgets:
        if widget.state() == 'layoutBuilt':
            widget.cacheDiffs()
    registry = WidgetRegistry()
    
    #determine whether the cog has been removed from the widget        
    for widget in allWidgets:
        wdata = {}
        
        if not widget.parent():
            wdata['parentID'] = 'None'
            wdata['plug'] = 'None'
        else:                
            wdata['parentID'] = str(id(widget.parent()))            
            wdata['plug'] = str(widget.parent().plugOfChild(widget))
        wdata['options'] = widget.options.getData()
        wdata['diffs'] = widget.getDiffs()
        wdata['widgetName'] = registry.widgetName(widget)
        result[str(id(widget))] = wdata
        
    return result
    
    
def rigFromData(data):
    '''
    Get a rig from a data dict
    '''
    #create a rig instance
    data = copy.deepcopy(data)
    root = None
    #create widgets
    idWidgets = {}
    registry = WidgetRegistry()        
    for id_, dct in data.items():    
        wdg = registry.getInstance(dct['widgetName'])
        idWidgets[id_] = wdg
        wdg.setDiffs(dct['diffs'])
        wdg.options.setFromData(dct['options'])
        
    #parent them into rig
    for id_, wdg in idWidgets.items():
        parentID = data[id_]['parentID']
        if parentID == 'None':
            root = wdg                    
        else:
            try:
                parentWidget = idWidgets[parentID]
            except KeyError:
                _logger.warning("Cannot find parent widget for %s" % str(wdg))
                _logger.debug("idWidgetDct:\n%r" % idWidgets)                
                
            plug = data[id_]['plug']
            parentWidget.addChild(wdg, plug=plug)        
        
    return root


def _importAllWidgets(reloadThem=False):
    """
    Import all modules in 'widgets' directories.
    """
    rootDir = os.path.dirname(sys.modules[__name__].__file__)
    widgetsDir = os.path.join(rootDir, 'widgets')
    _logger.info("Loading widgets from %s" %  widgetsDir)
    modules = []
    for base in os.listdir(widgetsDir):
        path = os.path.join(widgetsDir, base)
        #don't match py files starting with an underscore
        match = re.match(r'^((?!_)[a-zA-Z0-9_]+)\.py$', base)
        if match and os.path.isfile(path):
            name = match.groups()[0]
            modules.append('beings.widgets.%s' % name)
    for module in modules:
        moduleObj = sys.modules.get(module, None)
        if moduleObj and reloadThem:
            _logger.info('Reloading %s' % module)
            reload(sys.modules[module])
        else:
            _logger.info('Importing %s' % module)
            __builtin__.__import__(module, globals(), locals(), [], -1)
    return modules    

