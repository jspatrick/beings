"""
The core widget and rig objects that custom widgets should inherit
"""
import logging, re, copy, os, sys, __builtin__, json
import maya.cmds as MC
import pymel.core as PM
from PyQt4 import QtCore

import control as control
reload(control)
import utils as utils
reload(utils)

from utils.Naming import Namer
from observer import Observable
from options import OptionCollection
import nodeTag as NT
reload(NT)


_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO)

#set up logging

class BeingsFilter(logging.Filter):
    def __init__(self, name=''):
        logging.Filter.__init__(self, name=name)
    def filter(self, record):
        '''Add contextual info'''
        msg = '[function: %s: line: %i] : %s' % \
              (record.funcName, record.lineno, record.msg)
        record.msg= msg
        return True

def _setupLogging():
    rootLogger = logging.getLogger()
    _beingsRootLogger = logging.getLogger('beings')
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


class TreeItem(Observable):
    """
    An object that may have children and a parent.
    Tree items form a directed acyclical graph.

    Tree items must define their available plugs.
    When children are added, they are added
    to a particular plug in the parent item.
    Plugs must be configured on the TreeItem instances
    before children are added.

    The root tree item may have a null plug ("").
    As soon as the item is not a root, this null
    plug is removed.
    """

    def __init__(self, plugs=[]):
        super(TreeItem, self).__init__()

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
        """Can be overridden by subclasses to customize behvaior after a
        child is added"""


    def removedChild(self, child):
        """Can be overridden by subclassed to customize behavior after a child
        is removed"""


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

        self.notify('addedChild', parent=self, child=child)
        parent = self.parent()
        while parent:
            parent.notify('addedChild', parent=self, child=child)
            parent = parent.parent()

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

        self.notify('removedChild', parent=self, child=child)

        parent = self.parent()
        while parent:
            parent.notify('removedChild', parent=self, child=child)
            parent = parent.parent()

        return child

    def plugOfChild(self, child): return self.__childPlugs[self.childIndex(child)]

    def setChildPlug(self, child, plug):
        if plug not in self.plugs():
            _logger.warning("invalid plug '%s'" % plug)
            return False
        index = self.childIndex(child)
        self.__childPlugs[index] = plug



def duplicateBindJoints(jointList, namer, resolution='bnd'):
    """
    Duplicate the bind joints.  Give a new prefix
    @param jointDict: a dict of {'jointToken', jointName}
    @param namer: a namer object used to name the new joints
    """
    #check that all parents are also joints in the dict
    reverseJointDict = {}
    for k, v in jointDict.items():
        reverseJointDict[v] = k

    parentJnts = {} # map of joint tokens to parent joint tokens
    for jnt in jointList:
        par = MC.listRelatives(jnt, parent=1)
        par = par[0] if par else None
        if par in jointList:
            parentJnts[jnt] = par

    #store so we can reset it
    origResTok = namer.getToken('r')
    namer.setTokens(r=resolution)

    result = {}
    for tok, jnt in jointDict.items():
        MC.select(cl=1)
        result[tok] = MC.duplicate(jnt, po=1, n=namer(tok))[0]
        if MC.listRelatives(result[tok], parent=1):
            MC.parent(result[tok], world=True)

        MC.makeIdentity(result[tok], r=1, t=0, s=0, n=0, apply=True)

    #do parenting
    for key, parentKey in parentToks.items():
        if not parentKey:
            continue
        parent = namer(parentKey)
        MC.parent(result[key], parent)

    #freeze joints
    newJnts = result.values()
    for jnt in newJnts:
        MC.makeIdentity(jnt, apply=1, t=1, r=1, s=1, n=1)

    utils.fixInverseScale(newJnts)

    #reset tokens
    namer.setTokens(r=origResTok)

    return result



def _addControlToDisplayLayer(ctl, layer):
    if layer not in ['layout', 'rig']:
        raise RuntimeError("invalid layer")
    lyrName = '%s_ctl_lyr' % layer
    if not MC.objExists(lyrName):
        MC.createDisplayLayer(name=lyrName, empty=True)

    for shape in control.getShapeNodes(ctl):
        shape = str(shape)
        #do manual connection so we can keep the control colors
        MC.connectAttr('%s.displayType' % lyrName,
                       '%s.overrideDisplayType' % shape)
        MC.connectAttr('%s.visibility' % lyrName,
                       '%s.overrideVisibility' % shape)
        MC.connectAttr('%s.enabled' % lyrName,
                       '%s.overrideEnabled' % shape)


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

        self.options.subscribe('optChanged', self._optionChanged)
        self.options.subscribe('optAboutToChange', self._optionAboutToChange)

        self._nodes = [] #stores all nodes
        self.__state = 'unbuilt'
        self._joints = set()
        self._controls = set()
        self._cachedDiffs = {}

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
        self.__plugNodes[part] = str(node)

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

    def _optionChanged(self, event):
        opt = event.optName
        oldVal = event.oldVal
        newVal = event.newVal

        #if the char is changed on any node, it should be changed for all nodes in the hierarchy
        if opt == 'char':
            root = self.root()
            allNodes = root.children(recursive=True) + [root]
            for node in allNodes:
                if hasattr(node, "options"):
                    if node.options.getValue('char') != newVal:
                        node.options.setValue('char', newVal, quiet=True)

    def _optionAboutToChange(self, event):
        opt = event.optName
        oldVal = event.oldVal
        newVal = event.newVal

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

    def __notifyBuildComplete(self, buildType):
        """Notify relatives that this widget has completed a build"""
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
                utils.fixInverseScale([node])
                MC.parent(node, parentNode)

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

    #todo:  remove this from the class.  Call it with a bindJoints arg
    @BuildCheck('layoutBuilt', 'rigBuilt')
    def getNodes(self, category=None):
        nodes = []
        #don't warn about non-existing nodes
        with utils.SilencePymelLogger():
            if category is not None:
                if category not in self._nodeCategories.keys():
                    raise utils.BeingsError("Invalid category %s" % category)
                #return a copy of the list
                print self._nodeCategories[category]
                nodes = [n for n in self._nodeCategories[category] if MC.objExists(n)]
                self._nodeCategories[category] = copy.copy(nodes) # set it to the existing objs

                if category == 'parent':
                    otherCategoryNodes = set([])
                    for grp in self._nodeCategories.values():
                        otherCategoryNodes.update(grp)

                    for n in self.getNodes():
                        if MC.objectType(n, isAType='transform') and not MC.listRelatives(n, parent=1):
                            if n not in otherCategoryNodes:
                                _logger.warning("Directly parenting uncategoried top-level node '%s'"\
                                                % n)
                                nodes.append(n)

            else:
                nodes = self._nodes
                nodes = [n for n in nodes if MC.objExists(n)]
                self._nodes = copy.copy(nodes)

        return nodes

    def state(self): return self.__state

    def registerBindJoint(self, jnt):
        '''Register bind joints to be duplicated'''
        self._joints.add(jnt)
        control.setStorableXformAttrs(jnt, worldSpace=True, categories=['bindJnt'])

    def registerControl(self, ctl, ctlType ='layout'):
        """Register a control that should be cached"""
        if ctlType not in ['rig', 'layout']:
            raise RuntimeError("Invalid ctl type '%s'" % ctlType)

        ctl = str(ctl)
        if not control.isStorableXform(ctl):
            control.makeStorableXform(ctl)

        if control in self._controls:
            raise RuntimeError("%s is already a control in widget" % control)

        if ctlType == 'layout':
            #we don't need to keep track of layout controls world matrices
            control.setStorableXformAttrs(ctl, categories=['layout'],
                                          worldSpace=False)
        else:
            control.setStorableXformAttrs(ctl, categories=['rig'],
                                          worldSpace=True)
        self._controls.add(ctl)


    def buildLayout(self, useCachedDiffs=True, altDiffs=None, children=True):
        if self.state() != 'unbuilt':
            if self.state() == 'layoutBuilt':
                self.cacheDiffs()
            self.delete()

        self.__validateChildSettings()

        side = self.options.getValue('side')
        part = self.options.getValue('part')
        char = self.options.getValue('char')
        namer = Namer()
        namer.setTokens(side=side, part=part, c=char)
        self._joints = set()
        result = None

        MC.select(clear=1)

        with utils.NodeTracker() as nt:
            topNode = MC.createNode('transform', name=self.name(), parent=None)
            try:
                result = self._makeLayout(namer)
                self.__state = 'layoutBuilt'

            finally:
                self._nodes = nt.getObjects()

        #parent all nodes under a single group
        parentToTopNode = []
        for node in self._nodes:
            if not MC.objectType(node, isAType='transform'):
                continue
            if not MC.listRelatives(node, parent=1, pa=1) and node != topNode:
                parentToTopNode.append(node)

        for node in parentToTopNode:
            MC.parent(node, topNode)


        #set all bind joints to be referenced nodes so we can't
        #select them directly
        for jnt in self._joints:
            MC.setAttr('%s.overrideEnabled' % jnt, 1)
            MC.setAttr('%s.overrideDisplayType' % jnt, 2)

        if altDiffs is not None:
            self.applyDiffs(altDiffs)
        elif useCachedDiffs and self._cachedDiffs:
            self.applyDiffs(self._cachedDiffs)

        #build all children
        if children:
            for child in self.children():
                child.buildLayout()


        #setup display layers
        ctls = control.getStorableXformRebuildData(inNodeList=self._controls,
                                            categories=['layout'])
        for ctl in ctls:
            _addControlToDisplayLayer(ctl, 'layout')
        ctls = control.getStorableXformRebuildData(inNodeList=self._controls,
                                            categories=['rig'])
        for ctl in ctls:
            _addControlToDisplayLayer(ctl, 'rig')

        #notify relatives build finished
        self.__notifyBuildComplete('layout')

        return result

    def _makeLayout(self, namer):
        """
        build the layout
        """
        return namer

    @BuildCheck('layoutBuilt', 'rigBuilt')
    def delete(self, cache=True, deleteChildren=False):
        """
        Delete nodes
        """
        if deleteChildren:
            for child in self.children(recursive=True):
                child.delete(cache=cache)

        #if this widget is mirrored, we must cache and delete
        #the mirrored widget
        if self.mirroredState() == 'source' and self.state() == 'layoutBuilt':
            _logger.info("deleting a mirrored widget - deleteing the other side first")
            other = self._getMirrorableWidget()
            if other.state() == 'layoutBuilt':
                _logger.debug("deleting mirrored target %r" % other)
                other.delete()

        if cache:
            if self.state() == 'rigBuilt':
                _logger.debug('deleting a rig - skipping caching')
            else:
                self.cacheDiffs()
        #silence the pymel logger or it's pretty noisy about missing nodes
        with utils.SilencePymelLogger():
            for node in self.getNodes():
                if MC.objExists(node):
                    MC.delete(node)
        self._joints = set()
        self._controls = set()
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
        self._cachedDiffs['rig'] = control.getStorableXformRebuildData(inNodeList=self._controls,
                                                                       categories=['rig'])
        self._cachedDiffs['layout'] = control.getStorableXformRebuildData(inNodeList=self._controls,
                                                                       categories=['layout'])
        self._cachedDiffs['joints'] = control.getStorableXformRebuildData(inNodeList=self._joints)
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
        if self.state() == 'layout':
            if cached:
                return self._cachedDiffs
            else:
                result = {}
                result['rig'] = control.getStorableXformRebuildData(inNodeList=self._controls,
                                                                       categories=['rig'])
                result['layout'] = control.getStorableXformRebuildData(inNodeList=self._controls,
                                                                       categories=['layout'])
                result['joints'] = control.getStorableXformRebuildData(inNodeList=self._joints,
                                                                       categories=['joints'])
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
        #it's importants that layoutDiffs are set first - they are in local space,
        #rig controls are in world space
        for diffDct in [layoutDiffs, rigDiffs]:
            for nodeName, info in diffDct.items():
                control.makeStorableXform(nodeName, **info)

    def setNodeCateogry(self, node, category):
        '''
        Add a node to a category.  This is used by the parenting
        system to determine where to place a node in the hierarchy
        of the character
        '''
        if category not in self._nodeCategories.keys():
            raise utils.BeingsError("invalid category %s" % category)

        self._nodeCategories[category].append(str(node))

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

        if self.state() == 'rigBuilt' or self.state() == 'layoutBuilt':
            self.delete()

        if altDiffs is not None:
            self._cachedDiffs = altDiffs
        elif not self._cachedDiffs:
            self.buildLayout()
            self.delete()


        #this seems to be a bug - if refresh isn't called, there is some odd behavior when things
        #are dupicated
        MC.refresh()

        namer = Namer()
        namer.setTokens(c=self.options.getValue('char'),
                        n='',
                        side=self.options.getValue('side'),
                        part=self.options.getValue('part'))
        namer.lockToks('c', 'n', 's', 'p') # makes sure they can't be changed by overridden methods

        with utils.NodeTracker() as nt:
            #re-create the rig controls
            rigCtls = control.makeStorableXformsFromData(self._cachedDiffs['rig'], skipParenting=True)
            for ctl in rigCtls:
                control.flushControlScaleToShape(ctl)
            bindJnts =  control.makeStorableXformsFromData(self._cachedDiffs['joints'])

            #kwarg for debugging
            if returnBeforeBuild:
                self._nodes = [n for n in nt.getObjects() if MC.objExists(n)]
                self.__state = 'rigBuilt'
                return  namer

            #make the rig
            result = self._makeRig(namer)
            self.__state = 'rigBuilt'

            self._nodes = [n for n in nt.getObjects() if MC.objExists(n)]

        #Check that the rig was created properly
        for plug in self.plugs():
            if plug not in self.__plugNodes:
                _logger.warning("The '%s' plug was not assigned a a node" % plug)

        #build children
        for child in self.children():
            child.buildRig(skipCallbacks=skipCallbacks)

        #notify relatives that build finished
        if not skipCallbacks:
            self.__notifyBuildComplete('rig')

        return result

    def _makeRig(self, namer):
        return namer

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
                        MC.connectAttr('%s.%s' % (thisCtl, attr),
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
                    mdn = MC.createNode('multiplyDivide',
                                        n=namer.name(d='%s%sTo%s%s' % (thisCtl,attr,otherCtl,attr)))

                    MC.setAttr('%s.input2X' % mdn, -1)
                    MC.setAttr('%s.opreatinon' % mdn, 1)

                    MC.connectAttr(fromAttr, '%s.input1X' % mdn)
                    try:
                        MC.connectAttr('%s.outputX' % mdn, toAttr)
                    except RuntimeError:
                        MC.delete(mdn)
                    except Exception, e:
                        _logger.warning("Error during connection: %s" % str(e))
                        MC.delete(mdn)
                    else:
                        self._nodes.append(mdn)

class Root(Widget):
    """Builds a master control and main hierarchy of a rig"""

    @staticmethod
    def tagInputScaleAttr(node, attrName):
        """Add a uniform scale input attr to a node.
        It will be detected and connected to the master uniform scale
        attribute"""

        tag = {'attr': attrName}
        NT.setTag(node, 'uniformScaleInput', tag)

    def __init__(self, part='master'):
        super(Root, self).__init__(part=part)
        self.options.setPresets('side', 'cn')
        self.addParentPart('master')
        self.options.addOpt('rigType', 'core', presets=['core'])

    def childCompletedBuild(self, child, buildType):
        MC.refresh()
        if buildType == 'rig':
            if self.root() == self:
                children = child.children(recursive=True) + [child]
                for child in children:

                    #connect input scale
                    uniScaleNodes = NT.getNodesWithTag('uniformScaleInput',
                                                            inNodeList = child.getNodes())
                    for node in uniScaleNodes:
                        attr = getTag(node, 'uniformScaleInput')['attr']

                        _logger.info("Connecting uniform scale to %s.%s" % (node, attr))
                        MC.connectAttr('%s.uniformScale' % self._otherNodes['master'],
                                       '%s.%s' % (node, attr))

                    masterNodes = child.getNodes('master')
                    if masterNodes:
                        MC.parent(masterNodes, self._otherNodes['top'])
                    dntNodes = child.getNodes('dnt')
                    if dntNodes:
                        MC.parent(dntNodes, self._otherNodes['dnt'])
                    ikNodes = child.getNodes('ik')
                    for node in ikNodes:
                        if child.nodeStatus(node) != 'handled':
                            MC.parent(node, self.plugNode('master'))
        MC.refresh()
        super(Root, self).childCompletedBuild(child, buildType)

    def _makeLayout(self, namer):
        #mkae the layout control
        masterLayoutCtl = control.makeControl(namer.name(d='layout', r='ctl'),
                                              shape='circle',
                                              color='red',
                                              s=[4.5, 4.5, 4.5],
                                              xformType='transform')
        self.registerControl(masterLayoutCtl)

        #make rig control
        masterCtl = control.makeControl(namer('', r='ctl'),
                                        shape='circle',
                                        color='lite blue',
                                        xformType='transform',
                                        s=[4,4,4])
        MC.parent(masterCtl, masterLayoutCtl)
        self.registerControl(masterCtl, ctlType='rig')

    def _makeRig(self, namer):
        masterCtl = namer(r='ctl')
        self.setParentNode('master', masterCtl)

        if self.root() == self:
            rigType = self.options.getValue('rigType')
            top = MC.createNode('transform',
                                name=namer.name(d=rigType, p='',
                                                s='',x='rig', force=True))
            self._otherNodes['top'] = top
            dnt = MC.createNode('transform',
                                name=namer.name(d=rigType, p='',
                                                s='', x='dnt', force=True))
            MC.parent(dnt,top)
            self._otherNodes['dnt'] = str(dnt)

            self._otherNodes['master'] = str(masterCtl)

            MC.parent(masterCtl, top)

        #add master attrs
        MC.addAttr(masterCtl, ln='uniformScale', min=0.001, dv=1, k=1)
        for channel in ['sx', 'sy', 'sz']:
            MC.connectAttr('%s.uniformScale' % masterCtl, '%s.%s' % (masterCtl, channel))


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
        MC.refresh()
        if buildType == 'rig' and self.root() == self:

            children = child.children(recursive=True) + [child]
            for child in children:
                cogNodes = child.getNodes('ik')
                cogNodes.extend(child.getNodes('cog'))
                if cogNodes:
                    pm.parent(cogNodes, self.plugNode('cog_bnd'))
                    for node in cogNodes:
                        child.setNodeStatus(node, 'handled')
        MC.refresh()

        super(CenterOfGravity, self).childCompletedBuild(child, buildType)


    def _makeLayout(self, namer):
        cogLayoutCtl = control.makeControl(namer.name(d='layout', r='ctl'),
                                           shape='circle',
                                           color='yellow',
                                           s=[4, 4, 4],
                                           xformType='transform')
        MC.setAttr('%s.ty' % cogLayoutCtl, 5)
        self.registerControl(cogLayoutCtl)

        cogJnt = MC.createNode('joint', name=namer('', r='bnd'))

        utils.snap(cogJnt, cogLayoutCtl)
        MC.parentConstraint(cogLayoutCtl, cogJnt)

        self.registerBindJoint(cogJnt)


        bodyCtl = control.makeControl(namer('body', r='ctl'),
                                      shape='triangle',
                                      color='green',
                                      xformType='transform',
                                      s=[3.5, 3.5, 3.5])
        MC.parent(bodyCtl, cogLayoutCtl)
        control.setEditable(bodyCtl, True)

        pivotCtl = control.makeControl(namer.name('body_pivot', r='ctl'),
                                       shape='jack',
                                       color='yellow',
                                       xformType='transform',
                                       s=[2,2,2])
        MC.parent(pivotCtl, cogLayoutCtl)
        control.setEditable(pivotCtl, True)

        cogCtl = control.makeControl(namer.name('', r='ctl'),
                                     shape='triangle',
                                     color='green',
                                     xformType='transform',
                                     s=[2,2,2])
        control.setEditable(cogCtl, True)
        MC.parent(cogCtl, cogLayoutCtl)


        self.registerControl(bodyCtl, ctlType='rig')
        self.registerControl(pivotCtl, ctlType='rig')
        self.registerControl(cogCtl, ctlType='rig')


    def _makeRig(self, namer):
        #set up the positions of the controls
        rigCtls = {}
        for name in ['', 'body', 'body_pivot']:
            ctl = namer(name, r='ctl')
            if not MC.objExists(ctl):
                raise RuntimeError("cannot get control for '%s'" % ctl)
            rigCtls[name] = ctl

        cogJnt = namer('', r='bnd')
        if not MC.objExists(cogJnt):
            raise RuntimeError("cannot get control for '%s'" % cogJnt)
        self.setNodeCateogry(cogJnt, 'parent')

        MC.parent(rigCtls['body_pivot'], rigCtls['body'])
        MC.parent(rigCtls[''], rigCtls['body_pivot'])
        bodyZero = utils.insertNodeAbove(rigCtls['body'])
        self.setNodeCateogry(bodyZero, 'parent')


        #create the inverted pivot
        name = namer.name(d='pivot_inverse')
        pivInv = utils.insertNodeAbove(rigCtls[''], name=name)
        mdn = MC.createNode('multiplyDivide', n=namer.name(d='piv_inverse', x='mdn'))
        MC.setAttr('%s.input2' % mdn, -1,-1,-1, type='double3')
        MC.connectAttr('%s.t' % rigCtls['body_pivot'], '%s.input1' % mdn)
        MC.connectAttr('%s.output' % mdn, '%s.t' % pivInv)

        #constrain the cog jnt to the cog ctl
        MC.pointConstraint(rigCtls[''], cogJnt)
        MC.orientConstraint(rigCtls[''], cogJnt)

        #assign the nodes:

        self.setParentNode('cog_ctl', rigCtls[''])
        self.setParentNode('body_ctl', rigCtls['body'])
        self.setParentNode('pivot_ctl', rigCtls['body_pivot'])
        self.setParentNode('cog_bnd', cogJnt)

        #tag controls


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
        self.root.subscribe('addedChild', self._addedChild)
        self.root.subscribe('removedChild', self._removedChild)

    def _addedChild(self, event):
        parent = event.parent
        child = event.child

        _logger.debug("Added child %r under parent %s" % (child, parent))
        #TODO: make this add rows
        self.reset()

    def _removedChild(self, event):
        parent = event.parent
        child = event.child

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


def buildRig(fromPath=None, skipBuild=False):
    _importAllWidgets(reloadThem=True)
    if fromPath:
        if not os.path.exists(fromPath):
            raise RuntimeError("%s does not exist" % fromPath)

        with open(fromPath) as f:
            data = json.load(f)
        rig  = rigFromData(data)
        if not skipBuild:
            rig.buildRig()

    return rig

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
