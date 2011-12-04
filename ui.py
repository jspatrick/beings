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
        if index.isValid():            
            return index.internalPointer()
        else:
            return self.TOP

    def index(self, row, col, parent):
        parent = self.widgetFromIndex(parent)
        assert parent is not None
        children = []
        if parent is not self.TOP:
            #top level
            children = self.char.childWidgets(parent)
        elif parent is self.TOP:
            children = self.char.topWidgets()
            
        _logger.debug("Creating index, row=%r, col=%r, parent=%r, children=%r" % (row, col, parent, children))
        
        #assert( 0 <= row < len(children))
        return self.createIndex(row, col, children[row])
    
    def rowCount(self, parent):
        parent = self.widgetFromIndex(parent)
        if parent is None:
            return 0
        if parent is self.TOP:
            return len(self.char.topWidgets())
        else:
            return len(self.char.childWidgets(parent))

    def columnCount(self,  parent):
        return len(self.columns)
    
    def parent(self, child):
        child = self.widgetFromIndex(child)
        if child is None or child is self.TOP:
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
        assert childNames[row] == parentID
            
        return self.createIndex(row, 0, parent)
        
    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:            
            return QVariant()
        
        widgetColName = self.columns[index.column()]
        widget = self.widgetFromIndex(index)
        assert widget is not None
        if widget is self.TOP:
            return QVariant(QString(""))
        if widgetColName == 'part':
            return QVariant(widget.options.getOpt('part'))
        elif widgetColName == 'side':
            return QVariant(widget.options.getOpt('side'))
        elif widgetColName == 'parent node':
            return QVariant(self.char.parentNode(widget) or '')
        elif widgetColName == 'class':
            return QVariant(widget.__class__.__name__)
        return QVariant()

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and \
           role == Qt.DisplayRole:
            assert 0 <= section <= len(self.columns)
            return QVariant(self.columns[section])
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
    

def _test():
    global g_uiInstance
    g_uiInstance = CharWidget()
    cog = g_uiInstance.model.char.topWidgets()[0]
    bl = core.BasicLeg()
    bl.options.setOpt('side', 'rt')
    bl2 = core.BasicLeg()
    g_uiInstance.model.char.addWidget(bl)
    g_uiInstance.model.char.addWidget(bl2)
    g_uiInstance.model.char.setParent(bl, cog, 'cog_bnd')
    g_uiInstance.model.char.setParent(bl2, cog, 'cog_bnd')
    g_uiInstance.show()
    g_uiInstance.model.reset()
