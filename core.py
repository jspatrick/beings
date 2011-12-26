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

import logging, re, copy, weakref, bisect, json
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

#set up logging 
__DEVMODE=True
class BeingsFilter(logging.Filter):
    def __init__(self, name=''):
        logging.Filter.__init__(self, name=name)
    def filter(self, record):
        '''Add contextual info'''
        msg = '[function: %s: line: %i] : %s' % (record.funcName, record.lineno, record.msg)
        record.msg= msg
        return True
    
_beingsRootLogger = logging.getLogger('beings')
if _beingsRootLogger.getEffectiveLevel() == 0:
    _beingsRootLogger.setLevel(logging.INFO)
    
for fltr in _beingsRootLogger.filters:
    _beingsRootLogger.removeFilter(fltr)    
_beingsRootLogger.addFilter(BeingsFilter())

_registeredWidgets = {}
CLASS_INDEX, DESCRIPTION_INDEX = range(2)
def registerWidget(class_, niceName=None, description=None):
    global _registeredWidgets
    if niceName is None:
        niceName = class_.__name__
    if description is None:
        description = 'No description provided'
    if niceName in _registeredWidgets.keys() or \
       class_ in _registeredWidgets.values():
        _logger.debug("%s is already registered" % niceName)
    _registeredWidgets[niceName] = (class_, description)
    
def listWidgets():
    return _registeredWidgets.keys()
def getWidgetInstance(widgetName):
    return _registeredWidgets[widgetName][CLASS_INDEX]()
def getWidgetDescription(widgetName):
    return _registeredWidgets[widgetName][DESCRIPTION_INDEX]()


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
        nameParts = copy.copy(self.__namedTokens)
        for tok, val in kwargs.items():
            fullTok = self._fullToken(tok)
            #check if locked
            if fullTok in self._lockedToks:
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

class OptionCollection(QObject):
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
        self.emit(SIGNAL('optionAdded'), optName)
        
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
    
    def setValue(self, optName, val):
        self._checkName(optName)
        changed=False
        if val != self.__options[optName]:
            changed = True
        self.__options[optName] = val        
        self.emit(SIGNAL('optSet'), optName, val)
        if changed:
            self.emit(SIGNAL('optChanged'), optName)
            
    #TODO:  Get option data
    def getData(self):
        '''Return the values of all options not set to default values'''
        pass
    
    def setFromData(self, data):
        '''
        Set options based on data gotten from getData
        '''
        pass
        
    def getAllOpts(self):
        return copy.deepcopy(self.__options)
    def setAllOpts(self, optDct):
        for optName, optVal in optDct.items():
            self.setValue(optName, optVal)

g_widgetList = []
def getWidgetMimeData(widget):
    global g_widgetList
    if widget not in g_widgetList:
        g_widgetList.append(widget)
    widgetIndex = g_widgetList.index(widget)
    
    data = QByteArray()
    stream = QDataStream(data, QIODevice.WriteOnly)
    stream << QString(str(widgetIndex))
    mimeData = QMimeData()
    mimeData.setData("application/x-widget", data)
    return mimeData
    
def widgetFromMimeData(mimeData):    
    if mimeData.hasFormat("application/x-widget"):
        data = mimeData.data("application/x-widget")
        stream = QDataStream(data, QIODevice.ReadOnly)
        index = QString()
        stream >> index
        index = int(str(index))
        return g_widgetList[index]
    
class WidgetTreeItem(object):
    KEY_INDEX, WIDGET_INDEX, CHILD_PART_INDEX = range(3)

    def __init__(self, part, isRoot=False):
        self._isRoot = isRoot
        self.parent = None
        self.children = []            
        self.numColumns = 5
        
        self._parentNodes = {}
        
        #set up options    
        self.options = OptionCollection()
        self.options.addOpt('part', part)
        self.options.addOpt('side', 'cn', presets=['cn', 'lf', 'rt'])
        self.options.addOpt('char', 'defaultchar')
    
    def childWidgets(self, recursive=True):
        result = []
        for child in self.children:
            childWidget = child[self.WIDGET_INDEX]
            if recursive:
                result.extend(childWidget.childWidgets())
            result.append(childWidget)
        return result
    
    def numChildren(self):
        return len(self.children)
    
    def childAtRow(self, row, returnIndex=None):
        if returnIndex is None:
            returnIndex = self.WIDGET_INDEX
        assert 0 <= row < len(self.children)
        return self.children[row][returnIndex]
    
    def rowOfChild(self, child):
        for i, item in enumerate(self.children):
            if item[self.WIDGET_INDEX] == child:
                return i
        return -1
    
    def childWithKey(self, key):
        if not self.children:
            return None
        i = bisect.bisect_left(self.children, (key, None))
        if i < 0 or i >= len(self.children):
            return None
        if self.children[i][self.KEY_INDEX] == key:
            return self.children[i][self.WIDGET_INDEX]
        return None

    def removeChild(self, child):
        row = self.rowOfChild(child)
        if row == -1:
            _logger.warning("%r is not a child of %r" % (child, self))
        self.children.pop(row)
        return child
    
    def insertChild(self, child, parentToPart=""):
        if self._isRoot:
            if parentToPart != "":
                raise KeyError("Children of a root node cannot have a parent to part")
        elif parentToPart not in self.listParentParts():
            raise KeyError("Invalid parent to part '%s'" % parentToPart)

        if child._isRoot:
            raise TypeError("Cannot parent root nodes")
        #order keys must be unique
        for currentChild in self.children:
            if currentChild[self.KEY_INDEX] == child.orderKey():
                _logger.warning("Widget with ID '%s' already is a child"\
                                % child.orderKey())
                return

        child.parent = self
        childList = (child.orderKey(), child, parentToPart)
        bisect.insort(self.children, childList)
        
    def getClassName(self):
        return self.__class__.__name__
    
    def getData(self, col):
        assert 0 <= col < self.numColumns
        if col == 0:
            return QVariant(QString(self.options.getValue('part')))
        elif col == 1:
            return QVariant(QString(self.options.getValue('side')))
        elif col == 2:
            if self.parent:
                row = self.parent.rowOfChild(self)
                child = self.parent.children[row][self.CHILD_PART_INDEX]
                return QVariant(QString(child))
            else:
                return QVariant(QString(""))
        elif col == 3:
            return QVariant(QString(self.getClassName()))
        elif col == 4:
            return self.orderKey()

    def orderKey(self): return "%s_%s" % \
        (self.options.getValue('part'), self.options.getValue('side'))

    def addParentPart(self, nodeName):
        '''Add the 'key' name of a node'''
        if nodeName in self._parentNodes.keys():
            _logger.warning("%s already is a parent node" % nodeName)
        self._parentNodes[nodeName] = None

    def setParentNode(self, nodeName, node):
        '''Set the actual node of a nodeName'''
        if nodeName not in self._parentNodes.keys():
            raise utils.BeingsError("Invalid parent node name '%s'" % nodeName)
        self._parentNodes[nodeName] = node

    def getParentNode(self, nodeName):
        if nodeName not in self._parentNodes.keys():
            raise utils.BeingsError("Invalid parent node name '%s'" % nodeName)
        return self._parentNodes[nodeName]

    def listParentParts(self):
        return self._parentNodes.keys()
        
class TreeModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)
        self.root = WidgetTreeItem("", isRoot=True)
        self.columns = self.root.numColumns
        self.headers = ['Part', 'Side', 'Parent Node', 'Class', 'ID']

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction
    
    def flags(self, index):
        defaultFlags = QAbstractItemModel.flags(self, index)
        if index.isValid():
            return Qt.ItemIsEditable | Qt.ItemIsDragEnabled | \
                    Qt.ItemIsDropEnabled | defaultFlags
        else:
            return Qt.ItemIsDropEnabled | defaultFlags
        
    def widgetFromIndex(self, index):
        return index.internalPointer() \
            if index.isValid() else self.root
    
    def indexFromWidget(self, widget, parentIndex=QModelIndex()):
        """Get the QModelIndex from a widget."""
        rows = self.rowCount(parentIndex)
        for i in range(rows):
            index = self.index(i, 0, parentIndex)
            if index.internalPointer() == widget:
                return index
            else:
                index = self.indexFromWidget(widget, parentIndex=index)
                if index != None:
                    return index
        return None        
    
    def rowCount(self, parent):
        widget = self.widgetFromIndex(parent)
        if widget is None:
            return 0
        else:
            return widget.numChildren()
        
    def mimeTypes(self):
        types = QStringList()
        types.append('application/x-widget')
        return types
    
    def mimeData(self, indexList):
        index = indexList[0]
        widget = self.widgetFromIndex(index)
        mimeData = getWidgetMimeData(widget)
        return mimeData
    
    def dropMimeData(self, mimedata, action, row, column, parentIndex):
        if action == Qt.IgnoreAction:
            return True
        dragNode = widgetFromMimeData(mimedata)
        if not dragNode:
            return False
        if dragNode.parent:
            dragNode.parent.removeChild(dragNode)
            
        parentNode = self.widgetFromIndex(parentIndex)
        if parentNode is self.root or parentNode is None:
            self.root.insertChild(dragNode)
        else:
            parentParts = parentNode.listParentParts()
            parentNode.insertChild(dragNode, parentParts[0])
        self.insertRow(parentNode.numChildren()-1, parentIndex)
        self.emit(SIGNAL("dataChanged(QModelIndex, QModelIndex)"), parentIndex, parentIndex)
        return True
    
    def insertRow(self, row, parent):
        return self.insertRows(row, 1, parent)
    
    def insertRows(self, row, count, parent):
         self.beginInsertRows(parent, row, (row + (count-1)))
         self.endInsertRows()
         return True
    
    def removeRow(self, row, parentIndex):
         return self.removeRows(row, 1, parentIndex)
    
    def removeRows(self, row, count, parentIndex):
         self.beginRemoveRows(parentIndex, row, row)    
         self.endRemoveRows()
         return True
    
    def columnCount(self, parent):
        return self.columns
    
    def index(self, row, column, parent):
        assert self.root
        widget = self.widgetFromIndex(parent)
        assert widget is not None
        try:
            return self.createIndex(row, column,
                                    widget.childAtRow(row))
        except AssertionError:
            return QModelIndex()
    def setData(self, index, value, role=Qt.EditRole):
        widget = self.widgetFromIndex(index)
        if widget is None or widget is self.root:
            return False
        header = self.headers[index.column()]
        value = str(value.toString())
        if header == 'Part':
            widget.options.setValue('part', value)
        if header == 'Side':
            
            if value not in ['cn', 'lf', 'rt']:
                _logger.warning('invalid side "%s"' % value)
            else:
                widget.options.setValue('side', value)
        self.emit(SIGNAL("dataChanged(QModelIndex, QModelIndex)"), index, index)
        return True
    
    def parent(self, child):
        widget = self.widgetFromIndex(child)
        if widget is None:
            return QModelIndex()
        parent = widget.parent
        if parent is None:
            return QModelIndex()
        grandparent = parent.parent
        if grandparent is None:
            return QModelIndex()
        row = grandparent.rowOfChild(parent)
        assert row != -1
        return self.createIndex(row, 0, parent)

    def data(self, index, role):
        if role == Qt.TextAlignmentRole:
            return QVariant(int(Qt.AlignTop|Qt.AlignLeft))
        if role != Qt.DisplayRole:
            return QVariant()
        widget = self.widgetFromIndex(index)
        assert widget is not None
        return widget.getData(index.column())
    
    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            assert 0 <= section <= len(self.headers)
            return QVariant(self.headers[section])
        return QVariant()
    

class Widget(WidgetTreeItem):
    
    layoutObjs = set([])
    VALID_NODE_CATEGORIES = ['master', 'dnt', 'cog', 'ik', 'fk']
    
    #Tree item reimplementations
    def getData(self, col):
        if col == 4: return self.name()
        else:
            return super(Widget, self).getData(col)
        
    def __init__(self, part='widget', **kwargs):

        #Get a unique part name.  This ensures all node names are unique
        #when multiple widgets are built.
        
        
        self.ref = self
        self.numColumns = 5        
                
        super(Widget, self).__init__(part)
        assert(self.options)
        self._ID = part
        self._nodes = [] #stores all nodes        
        self._bindJoints = {} #stores registered bind joints
        self._differs = {'rig': control.Differ(), 'layout': control.Differ()}
        self._cachedDiffs = {'rig': {}, 'layout': {}}
        self._nodeCategories = {}
        self._parentNodes = {}
        for categoy in self.VALID_NODE_CATEGORIES:
            self._nodeCategories[categoy] = []
        
    def _resetNodeCategories(self):
        for category in self.VALID_NODE_CATEGORIES:
            self._nodeCategories[category] = []            
    
    def name(self, id=False):
        """ Return a name of the object.
        partID should always be unique.  This can be used as a key
        in dictionaries referring to multiple instances"""
        if id:
            return self._ID
        part = self.options.getValue('part')
        side = self.options.getValue('side')
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
        char = self.options.getValue('char')
        side = self.options.getValue('side')
        part = self.options.getValue('part')        
        
        namer = Namer(c=char, s=side, p=part, r='bnd')
        for tok, jnt in result.items():
            jnt.rename(namer.name(d=tok))
        self._prepBindJoints(result)            
        return result

    def _prepBindJoints(self, jntDct):
        '''Orient bind joints.  jntDct is {layoutBindJntName: newBindJntPynode}'''
        pass

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

                if category == 'fk':
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

    def state(self):
        """
        Return built or unbuilt
        """
        if self.getNodes():
            
            if self._differs['layout'].getObjs().values()[0].exists():                
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

    @BuildCheck('unbuilt')
    def buildLayout(self, useCachedDiffs=True, altDiffs=None):
        
        side = self.options.getValue('side')
        part = self.options.getValue('part')
        namer = Namer()
        namer.setTokens(side=side, part=part)

        self._bindJoints = {}
        with utils.NodeTracker() as nt:
            try:
                self._makeLayout(namer)
            finally:
                self._nodes = nt.getObjects()
                
        #set up the differ
        for diffType, differ in self._differs.items():
            differ.setInitialState()
            
        if altDiffs is not None:
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
        with utils.SilencePymelLogger():
            for node in self.getNodes():
                if pm.objExists(node):
                    pm.delete(node)
        self._nodes = []
        self._resetNodeCategories()
        
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
        namer.setTokens(c=self.options.getValue('char'),
                        n='',
                        side=self.options.getValue('side'),
                        part=self.options.getValue('part'))
        namer.lockToks('c', 'n', 's', 'p')

        #get the rig control data
        rigCtlData = control.getRebuildData(self._differs['rig'].getObjs())
        #duplicate the bind joints, and delete the rest of the rig
        bndJntNodes = []
        with utils.NodeTracker() as nt:
            jntDct = self.duplicateBindJoints()
            bndJntNodes = nt.getObjects()
        self.delete()
        
        for tok, jnt in jntDct.items():
            jnt.rename(namer.name(d=tok, r='bnd'))
        with utils.NodeTracker() as nt:            
            #re-create the rig controls
            rigCtls = control.buildCtlsFromData(rigCtlData)

            #make the rig
            result = self._makeRig(namer, jntDct, rigCtls)
            
            nodes = nt.getObjects()
            nodes.extend(bndJntNodes)
            self._nodes = [n for n in nodes if pm.objExists(n)]
            
        #Check that the rig was created properly
        for key, node in self._parentNodes.items():
            if node == None:
                _logger.warning("The '%s' parentNodeName was not assigned a a node" % key)
                
        return result
    
    def _makeRig(self, namer, bndJnts, rigCtls):
        raise NotImplementedError
    
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
        
        masterLayoutCtl = control.makeControl(shape='circle',
                                             color='red',
                                             scale=[4.5, 4.5, 4.5],
                                             name=namer.name(d='master_layout', s='ctl'),
                                             xformType='transform')        
        self.registerControl('master', masterLayoutCtl)
        
        cogLayoutCtl = control.makeControl(shape='circle',
                                          color='yellow',
                                          scale=[4, 4, 4],
                                          name=namer.name(d='cog_layout', s='ctl'),
                                          xformType='transform')
        cogLayoutCtl.ty.set(5)
        cogLayoutCtl.setParent(masterLayoutCtl)  
        self.registerControl('cog', cogLayoutCtl)
                
        cogJnt = pm.createNode('joint', name=namer.name(d='cog', r='bnd'))
        masterJnt = pm.createNode('joint', name=namer.name(d='master', r='bnd'))
        cogJnt.setParent(masterJnt)
        
        utils.snap(cogJnt, cogLayoutCtl)
        pm.parentConstraint(cogLayoutCtl, cogJnt)                
        pm.parentConstraint(masterLayoutCtl, masterJnt)
        
        self.registerBindJoint('master', masterJnt)
        self.registerBindJoint('cog', cogJnt, parent=masterJnt)
        
        masterCtl = control.makeControl(shape='circle',
                                       color='lite blue',
                                       xformType='transform',
                                       scale=[4,4,4], name = namer.name(r='ctl', d='master'))
        masterCtl.setParent(masterLayoutCtl)
        
        bodyCtl = control.makeControl(shape='triangle', color='green', xformType='transform',
                                  scale=[3.5, 3.5, 3.5], name=namer.name(r='ctl', d='body'))
        bodyCtl.setParent(cogLayoutCtl)
                                    
        pivotCtl = control.makeControl(shape='jack', color='yellow', xformType='transform', scale=[2,2,2],
                                   name=namer.name(r='ctl', d='body_pivot'))
        pivotCtl.setParent(cogLayoutCtl)
                                    
        cogCtl = control.makeControl(shape='triangle', color='green', xformType='transform', scale=[2,2,2],
                                 name=namer.name(r='ctl', d='cog'))
        cogCtl.setParent(cogLayoutCtl)
        
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
            control.snapKeepShape(bndJnts['cog'], rigCtls[tok])
                    
        rigCtls['body'].setParent(rigCtls['master'])
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
registerWidget(CenterOfGravity, 'Center Of Gravity', 'The widget under which all others should be parented')

class Rig(TreeModel):
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
        self._nodes = []
        self._stateFlag = 'unbuilt'
        self.options = OptionCollection()
        self.options.addOpt('char', 'defaultcharname')
        self.options.setValue('char', charName)
        self.options.addOpt('rigType', 'core')
        self.options.setValue('rigType', rigType)
        self.options.addOpt('buildStyle', 'standard')
        self.options.setValue('buildStyle', buildStyle)
        
        self.cog = CenterOfGravity()
        self.cog.options.setValue('char', self.options.getValue('char'))        
        self.addWidget(self.cog)
    
    def addWidget(self, widget, parent=None, parentNode=None):        
        if parent is None:
            parent = self.root
            parentNode = ""
        parent.insertChild(widget, parentNode)        
        widget.options.setValue('char', self.options.getValue('char'))        
        parentIndex = self.indexFromWidget(parent)
        if parentIndex is None:
            parentIndex = QModelIndex()
        self.emit(SIGNAL('dataChanged(QModelIndex, QModelIndex)'), parentIndex, parentIndex)
        
    def buildLayout(self):
        self._stateFlag = 'built'
        for wdg in self.root.childWidgets():
            if wdg.state() == 'rigged':
                wdg.delete()
            wdg.buildLayout()
    
    def state(self):
        return self._stateFlag
                
    def buildRig(self, lock=False):
        self._stateFlag = 'rigged'
        with utils.NodeTracker() as nt:            
            self._buildMainHierarchy()                 
            self._nodes = nt.getObjects()
            
        for wdg in self.root.childWidgets():            
            wdg.buildRig()

        self._doParenting()
        if lock:
            NT.lockHierarchy(self._coreNodes['top'])
            
    def delete(self):
        for wdg in self.root.childWidgets():
            wdg.delete()
        with utils.SilencePymelLogger():
            for node in self._nodes:
                if pm.objExists(node):
                    pm.delete(node)
        self._nodes = []
        self._stateFlag = 'unbuilt'
        
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
                
    def _buildMainHierarchy(self):
        '''
        build the main group structure
        '''
        rigType = '_%s' % self.options.getValue('rigType')
        char = self.options.getValue('char')
        top = pm.createNode('transform', name='%s%s_rig' % (char, rigType))
        self._coreNodes['top'] = top
        dnt = pm.createNode('transform', name='%s%s_dnt' % (char, rigType))
        dnt.setParent(top)
        self._coreNodes['dnt'] = dnt
        model = pm.createNode('transform', name='%s%s_model' % (char, rigType))
        model.setParent(dnt)
        self._coreNodes['model'] = model

        
