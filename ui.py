from PyQt4.QtCore import *
from PyQt4.QtGui import *
import beings.core as core
import beings.utils as utils
import bisect, logging
reload(utils)
reload(core)
logging.basicConfig()
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)


class TreeTest(QTreeView):
    def __init__(self, parent=None):
        super(TreeTest, self).__init__(parent)
        self.rig = core.Rig('mychar')
        self.setModel(self.rig)
        leg = core.BasicLeg()
        leg2 = core.BasicLeg()
        self.rig.addWidget(leg, self.rig.cog, 'cog_bnd')
        self.rig.addWidget(leg2, self.rig.cog, 'cog_bnd')            
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
                
_testInst = None
def treeTest():            
    global _testInst
    _testInst = TreeTest()
    _testInst.show()

