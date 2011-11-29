from PyQt4.QtGui import *
from PyQt4.QtCore import *
import core

class CharDataModel(QAbstractItemModel):
    def __init__(self, charName):
        self.char = core.Rig(charName)

        self.rows = ['widget ID', 'part', 'side', 'parent node']
        
    def rowCount(self, index=QModelIndex()):
        return len(self.char.listWidgets())
    
    def columnCount(self, index=QModelIndex()):
        return len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or \
           not (0<= index.row() < len(self.widgets)):
            return QVariant()
        widgetID = self.listWidgets()[index.row()]
        widgetColName = self.rows[index.row()]
        widget = self.char.getWidget(widgetID)
        if role == Qt.QDisplayRole:
            if widgetColName == 'widget ID':
                return QVariant(widgetID)
            elif widgetColName == 'part':
                return QVariant(widget.options.getOpt('part'))
            elif widgetColName == 'side':
                return QVariant(widget.options.getOpt('side'))
            elif widgetColName == 'parent node':
                return QVariant(self.char.parentNode(widget) or '')
        return QVariant()
g_uiInstance = None
class CharWidget(QWidget):
    def __init__(self, charName='jeffy'):
        self.model = CharDataModel(charName)
        self.tableView1 = QTableView()
        self.tableView1.setModel(self.model)
        layout = QVBoxLayout()
        layout.addWidget(self.tableView1)
        self.setLayout(layout)
        
