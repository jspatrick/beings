from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic
import beings.core as core
import beings.utils as utils
import logging, sys, os
logging.basicConfig()
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

core._importAllWidgets(reloadThem=True)

def getResource(fileName):
    basedir = os.path.dirname(sys.modules[__name__].__file__)
    resource = os.path.join(basedir, 'ui_resources', fileName)
    return resource

class RigViewDelegate(QItemDelegate):
    def __init__(self, parent=None):
        super(RigViewDelegate, self).__init__(parent)
    def createEditor(self, parent, option, index):
        model = index.model()
        if index.column() == model.headers.index('Side'):
            combobox = QComboBox(parent)
            combobox.addItems(['lf', 'rt', 'cn'])
            combobox.setEditable(False)
            return combobox
        elif index.column() == model.headers.index('Parent Node'):
            parentIndex = model.parent(index)
            parts = model.widgetFromIndex(parentIndex).listParentParts()
            combobox = QComboBox(parent)
            combobox.addItems(parts)
            return combobox            
        else:
            return QItemDelegate.createEditor(self, parent, option, index)
    def setEditorData(self, editor, index):
        return QItemDelegate.setEditorData(self, editor, index)
    def setModelData(self, editor, model, index):
        if (index.column() == model.headers.index('Side')) or \
               (index.column() == model.headers.index('Parent Node')):
            model.setData(index, QVariant(editor.currentText()))
        else:
            QItemDelegate.setModelData(self, editor, model, index)
            
class RigWidget(QWidget):
    def __init__(self, parent=None):
        super(RigWidget, self).__init__(parent=parent)
        uic.loadUi(getResource('rigwidget.ui'), self)
        self.rigView.setItemDelegate(RigViewDelegate(self))
        self.__registry = core.WidgetRegistry()
        #populate the widget list
        for wdg in self.__registry.widgetNames():
            self.widgetList.addItem(wdg)
            
    @pyqtSlot()
    def on_buildLayoutBtn_released(self):
        self.rigView.rig.buildLayout()
        
    @pyqtSlot()
    def on_buildRigBtn_released(self):
        self.rigView.rig.buildRig()
        
    @pyqtSlot()
    def on_addWidgetBtn_released(self):
        wdg = str(self.widgetList.currentItem().text())
        inst = self.__registry.getInstance(wdg)
        self.rigView.rig.addWidget(inst)
        
        
_ui = None
def initUI():            
    global _ui
    if type(_ui) != RigWidget:
        _ui = RigWidget()
    _ui.show()
    return _ui

