from PyQt4.QtGui import *
from PyQt4.QtCore import *
import core

class CharDataModel(QAbstractTableModel):
    def __init__(self, charName):
        super(CharDataModel, self).__init__()
        self.char = core.Rig(charName)

        self.rows = ['widget ID', 'part', 'side', 'parent node']
        
    def rowCount(self, index=QModelIndex()):
        return len(self.char.listWidgets())
    
    def columnCount(self, index=QModelIndex()):
        return len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or \
           not (0<= index.row() < self.rowCount()):
            return QVariant()
        widgetID = self.char.listWidgets()[index.row()]
        widgetColName = self.rows[index.column()]
        widget = self.char.getWidget(widgetID)
        if role == Qt.DisplayRole:
            if widgetColName == 'widget ID':
                return QVariant(widgetID)
            elif widgetColName == 'part':
                return QVariant(widget.options.getOpt('part'))
            elif widgetColName == 'side':
                return QVariant(widget.options.getOpt('side'))
            elif widgetColName == 'parent node':
                return QVariant(self.char.parentNode(widget) or '')
        return QVariant()
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.TextAlignmentRole:
            if orientation == Qt.Horizontal:
                return QVariant(int(Qt.AlignLeft|Qt.AlignVCenter))
            return QVariant(int(Qt.AlignRight|Qt.AlignVCenter))
        if role != Qt.DisplayRole:
            return QVariant()
        if orientation == Qt.Horizontal:
            return QVariant(self.rows[section])
        else:
            return QVariant(int(section + 1))
g_uiInstance = None
class CharWidget(QWidget):
    def __init__(self, charName='jeffy', parent=None):
        super(CharWidget, self).__init__(parent=parent)
        self.model = CharDataModel(charName)
        self.tableView1 = QTableView()
        self.tableView1.setModel(self.model)
        layout = QVBoxLayout()
        layout.addWidget(self.tableView1)
        self.setLayout(layout)
        
