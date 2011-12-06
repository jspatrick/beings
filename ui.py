from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic
import beings.core as core
import beings.utils as utils
import logging, sys, os
logging.basicConfig()
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

def getResource(fileName):
    basedir = os.path.dirname(sys.modules[__name__].__file__)
    resource = os.path.join(basedir, 'ui_resources', fileName)
    return resource
                
class RigWidget(QWidget):
    def __init__(self, parent=None):
        super(RigWidget, self).__init__(parent=parent)
        uic.loadUi(getResource('rigwidget.ui'), self)        
        
    def addWidget(self, inst):
        self.rigView.rig.addWidget(inst)
        
    @pyqtSlot()
    def on_buildLayoutBtn_released(self):
        self.rigView.rig.buildLayout()
        
    @pyqtSlot()
    def on_buildRigBtn_released(self):
        self.rigView.rig.buildRig()
_testInst = None
def treeTest():            
    global _testInst
    _testInst = RigWidget()
    leg = core.getWidgetInstance('Basic Leg')
    leg2 = core.getWidgetInstance('Basic Leg')
    _testInst.addWidget(leg)
    _testInst.addWidget(leg2)
    _testInst.show()

