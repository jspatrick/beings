from PyQt4.QtCore import *
from PyQt4.QtGui import *
import core
import bisect, logging
logging.basicConfig()
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)


class CharDataModel(QAbstractTableModel):
    def __init__(self, charName):
        super(CharDataModel, self).__init__()
        self.char = core.Rig(charName)
        self.columns = ['part', 'side', 'parent node', 'class']        
        
    class TOP(object): pass
    
    def widgetFromIndex(self, index):
        _logger.debug("Getting widget index, internalpointer=%r" % index.internalPointer())
        obj = index.internalPointer()
        if obj:
            return obj
        else:
            return self.TOP
    
    def index(self, row, col, parent):
        parent = parent.internalPointer()        
        if not parent:
            #top level
            children = self.char.topWidgets()
        else:
            children = self.char.childWidgets(parent)
        _logger.debug("Creating index, row=%r, col=%r, parent=%r, children=%r" % (row, col, parent, children))
        assert( 0 <= row < len(children))
        return self.createIndex(row, col, children[row])
        
    def rowCount(self, parent):
        parent = parent.internalPointer()        
        if not parent:
            return len(self.char.topWidgets())
        else:
            return len(self.char.childWidgets(parent))
    
    def columnCount(self,  parentIndex=QModelIndex()):
        return len(self.columns)
    
    def parent(self, child):
        child = child.internalPointer()
        if not child:
            return QModelIndex()        
        parent = self.char.parentWidget(child)        
        if parent is None:
            return QModelIndex()
        
        parentID = parent.name(id=True)
        grandParent = self.char.parentWidget(parent)        
        if grandParent is None:            
            childNames = [w.name(id=True) for w in self.char.topWidgets()]
        else:
            childNames = [w.name(id=True) for w in self.char.childWidgets(grandParent)]
        _logger.debug("siblings of %s are: %s" % (parentID, childNames))
        row = bisect.bisect_left(childNames, parentID)
        return self.createIndex(row, 0, parent)
        
    def data(self, index, role=Qt.DisplayRole):
        widget = index.internalPointer()        
        if not widget:
            return QVariant()        
        widgetColName = self.columns[index.column()]
        
        if role == Qt.DisplayRole:
            if widgetColName == 'part':
                return QVariant(widget.options.getOpt('part'))
            elif widgetColName == 'side':
                return QVariant(widget.options.getOpt('side'))
            elif widgetColName == 'parent node':
                return QVariant(self.char.parentNode(widget) or '')
            elif widgetColName == 'class':
                return QVariant(widget.__class__.__name__)
        return QVariant()
    
    # def headerData(self, section, orientation, role=Qt.DisplayRole):
    #     if role == Qt.TextAlignmentRole:
    #         if orientation == Qt.Horizontal:
    #             return QVariant(int(Qt.AlignLeft|Qt.AlignVCenter))

    #     if role == Qt.DisplayRole:
    #         if orientation == Qt.Horizontal:
    #             return QVariant(self.rows[section])
            
    #     return QVariant()
    
g_uiInstance = None
class CharWidget(QWidget):
    def __init__(self, charName='jeffy', parent=None):
        super(CharWidget, self).__init__(parent=parent)
        self.model = CharDataModel(charName)
        self.treeView = QTreeView()
        self.treeView.setModel(self.model)
        layout = QVBoxLayout()
        layout.addWidget(self.treeView)
        self.setLayout(layout)
        
