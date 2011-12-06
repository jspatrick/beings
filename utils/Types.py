'''
Utility Objects
'''
import bisect, copy, logging
from cPickle import dumps, load, loads
from cStringIO import StringIO

from PyQt4.QtCore import *
from PyQt4.QtGui import *
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

# Backport of OrderedDict() class that runs on Python 2.4, 2.5, 2.6, 2.7 and pypy.
# Passes Python2.7's test suite and incorporates all the latest updates.
# http://code.activestate.com/recipes/576693/
try:
    from thread import get_ident as _get_ident
except ImportError:
    from dummy_thread import get_ident as _get_ident

try:
    from _abcoll import KeysView, ValuesView, ItemsView
except ImportError:
    pass


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

    def addOpt(self, optName, defaultVal, optType=str, **kwargs):
        self.__options[optName] = optType(defaultVal)
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
    
    def getOpt(self, optName):
        self._checkName(optName)
        return self.__options[optName]
    
    def setOpt(self, optName, val):
        self._checkName(optName)
        changed=False
        if val != self.__options[optName]:
            changed = True
        self.__options[optName] = val        
        self.emit(SIGNAL('optSet'), optName, val)
        if changed:
            self.emit(SIGNAL('optChanged'), optName)
        
    def getAllOpts(self):
        return copy.deepcopy(self.__options)
    def setAllOpts(self, optDct):
        for optName, optVal in optDct.items():
            self.setOpt(optName, optVal)

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
            return QVariant(QString(self.options.getOpt('part')))
        elif col == 1:
            return QVariant(QString(self.options.getOpt('side')))
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
        (self.options.getOpt('part'), self.options.getOpt('side'))

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
            widget.options.setOpt('part', value)
        if header == 'Side':
            
            if value not in ['cn', 'lf', 'rt']:
                _logger.warning('invalid side "%s"' % value)
            else:
                widget.options.setOpt('side', value)
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
    

class OrderedDict(dict):
    'Dictionary that remembers insertion order'
    # An inherited dict maps keys to values.
    # The inherited dict provides __getitem__, __len__, __contains__, and get.
    # The remaining methods are order-aware.
    # Big-O running times for all methods are the same as for regular dictionaries.

    # The internal self.__map dictionary maps keys to links in a doubly linked list.
    # The circular doubly linked list starts and ends with a sentinel element.
    # The sentinel element never gets deleted (this simplifies the algorithm).
    # Each link is stored as a list of length three:  [PREV, NEXT, KEY].

    def __init__(self, *args, **kwds):
        '''Initialize an ordered dictionary.  Signature is the same as for
        regular dictionaries, but keyword arguments are not recommended
        because their insertion order is arbitrary.

        '''
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        try:
            self.__root
        except AttributeError:
            self.__root = root = []                     # sentinel node
            root[:] = [root, root, None]
            self.__map = {}
        self.__update(*args, **kwds)

    def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
        'od.__setitem__(i, y) <==> od[i]=y'
        # Setting a new item creates a new link which goes at the end of the linked
        # list, and the inherited dictionary is updated with the new key/value pair.
        if key not in self:
            root = self.__root
            last = root[0]
            last[1] = root[0] = self.__map[key] = [last, root, key]
        dict_setitem(self, key, value)

    def __delitem__(self, key, dict_delitem=dict.__delitem__):
        'od.__delitem__(y) <==> del od[y]'
        # Deleting an existing item uses self.__map to find the link which is
        # then removed by updating the links in the predecessor and successor nodes.
        dict_delitem(self, key)
        link_prev, link_next, key = self.__map.pop(key)
        link_prev[1] = link_next
        link_next[0] = link_prev

    def __iter__(self):
        'od.__iter__() <==> iter(od)'
        root = self.__root
        curr = root[1]
        while curr is not root:
            yield curr[2]
            curr = curr[1]

    def __reversed__(self):
        'od.__reversed__() <==> reversed(od)'
        root = self.__root
        curr = root[0]
        while curr is not root:
            yield curr[2]
            curr = curr[0]

    def clear(self):
        'od.clear() -> None.  Remove all items from od.'
        try:
            for node in self.__map.itervalues():
                del node[:]
            root = self.__root
            root[:] = [root, root, None]
            self.__map.clear()
        except AttributeError:
            pass
        dict.clear(self)

    def popitem(self, last=True):
        '''od.popitem() -> (k, v), return and remove a (key, value) pair.
        Pairs are returned in LIFO order if last is true or FIFO order if false.

        '''
        if not self:
            raise KeyError('dictionary is empty')
        root = self.__root
        if last:
            link = root[0]
            link_prev = link[0]
            link_prev[1] = root
            root[0] = link_prev
        else:
            link = root[1]
            link_next = link[1]
            root[1] = link_next
            link_next[0] = root
        key = link[2]
        del self.__map[key]
        value = dict.pop(self, key)
        return key, value

    # -- the following methods do not depend on the internal structure --

    def keys(self):
        'od.keys() -> list of keys in od'
        return list(self)

    def values(self):
        'od.values() -> list of values in od'
        return [self[key] for key in self]

    def items(self):
        'od.items() -> list of (key, value) pairs in od'
        return [(key, self[key]) for key in self]

    def iterkeys(self):
        'od.iterkeys() -> an iterator over the keys in od'
        return iter(self)

    def itervalues(self):
        'od.itervalues -> an iterator over the values in od'
        for k in self:
            yield self[k]

    def iteritems(self):
        'od.iteritems -> an iterator over the (key, value) items in od'
        for k in self:
            yield (k, self[k])

    def update(self, *args, **kwds):
        '''od.update(E, **F) -> None.  Update od from dict/iterable E and F.

        If E is a dict instance, does:           for k in E: od[k] = E[k]
        If E has a .keys() method, does:         for k in E.keys(): od[k] = E[k]
        Or if E is an iterable of items, does:   for k, v in E: od[k] = v
        In either case, this is followed by:     for k, v in F.items(): od[k] = v

        '''
        if len(args) > 2:
            raise TypeError('update() takes at most 2 positional '
                            'arguments (%d given)' % (len(args),))
        elif not args:
            raise TypeError('update() takes at least 1 argument (0 given)')
        self = args[0]
        # Make progressively weaker assumptions about "other"
        other = ()
        if len(args) == 2:
            other = args[1]
        if isinstance(other, dict):
            for key in other:
                self[key] = other[key]
        elif hasattr(other, 'keys'):
            for key in other.keys():
                self[key] = other[key]
        else:
            for key, value in other:
                self[key] = value
        for key, value in kwds.items():
            self[key] = value

    __update = update  # let subclasses override update without breaking __init__

    __marker = object()

    def pop(self, key, default=__marker):
        '''od.pop(k[,d]) -> v, remove specified key and return the corresponding value.
        If key is not found, d is returned if given, otherwise KeyError is raised.

        '''
        if key in self:
            result = self[key]
            del self[key]
            return result
        if default is self.__marker:
            raise KeyError(key)
        return default

    def setdefault(self, key, default=None):
        'od.setdefault(k[,d]) -> od.get(k,d), also set od[k]=d if k not in od'
        if key in self:
            return self[key]
        self[key] = default
        return default

    def __repr__(self, _repr_running={}):
        'od.__repr__() <==> repr(od)'
        call_key = id(self), _get_ident()
        if call_key in _repr_running:
            return '...'
        _repr_running[call_key] = 1
        try:
            if not self:
                return '%s()' % (self.__class__.__name__,)
            return '%s(%r)' % (self.__class__.__name__, self.items())
        finally:
            del _repr_running[call_key]

    def __reduce__(self):
        'Return state information for pickling'
        items = [[k, self[k]] for k in self]
        inst_dict = vars(self).copy()
        for k in vars(OrderedDict()):
            inst_dict.pop(k, None)
        if inst_dict:
            return (self.__class__, (items,), inst_dict)
        return self.__class__, (items,)

    def copy(self):
        'od.copy() -> a shallow copy of od'
        return self.__class__(self)

    @classmethod
    def fromkeys(cls, iterable, value=None):
        '''OD.fromkeys(S[, v]) -> New ordered dictionary with keys from S
        and values equal to v (which defaults to None).

        '''
        d = cls()
        for key in iterable:
            d[key] = value
        return d

    def __eq__(self, other):
        '''od.__eq__(y) <==> od==y.  Comparison to another OD is order-sensitive
        while comparison to a regular mapping is order-insensitive.

        '''
        if isinstance(other, OrderedDict):
            return len(self)==len(other) and self.items() == other.items()
        return dict.__eq__(self, other)

    def __ne__(self, other):
        return not self == other

    # -- the following methods are only used in Python 2.7 --

    def viewkeys(self):
        "od.viewkeys() -> a set-like object providing a view on od's keys"
        return KeysView(self)

    def viewvalues(self):
        "od.viewvalues() -> an object providing a view on od's values"
        return ValuesView(self)

    def viewitems(self):
        "od.viewitems() -> a set-like object providing a view on od's items"
        return ItemsView(self)        
