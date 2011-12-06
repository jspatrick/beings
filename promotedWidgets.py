from PyQt4.QtCore import *
from PyQt4.QtGui import *
import beings.core as core

class WidgetTree(QTreeView):
    def __init__(self, parent=None):
        super(WidgetTree, self).__init__(parent)
        self.rig = core.Rig('mychar')
        self.setModel(self.rig)
        self.rig.reset()

        self.setAnimated(True)
        self.connect(self.model(), SIGNAL("dataChanged(QModelIndex,QModelIndex)"),
                     self.change)
        self.dragEnabled()
        self.acceptDrops()
        self.showDropIndicator()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.expandAll()
        
    def change(self, topLeftIndex, bottomRightIndex):
        self.update(topLeftIndex)
        self.expandAll()
        self.expanded()
        
    def expanded(self):
        for column in range(self.model().columnCount(QModelIndex())):
                self.resizeColumnToContents(column)
