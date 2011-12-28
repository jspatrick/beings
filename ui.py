from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic
import beings.core as core
import beings.utils as utils
import logging, sys, os
logging.basicConfig()
_logger = logging.getLogger(__name__)

core._importAllWidgets(reloadThem=True)

def getResource(fileName):
    basedir = os.path.dirname(sys.modules[__name__].__file__)
    resource = os.path.join(basedir, 'ui_resources', fileName)
    return resource
class PopupError():
    """
    Decorator that will raise error messages
    """
    def __init__(self, parent=None):
        self._parent = parent
    def __call__(self, func):
        
        def new(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
            except Exception, e:
                QMessageBox.critical(self._parent, "Beings Error", str(e))
                raise
            
            return result
        doc = func.__doc__ or ""
        new.__doc__ = "<Using PopupError Decorator>\n%s" % doc
        new.__dict__.update(func.__dict__)
        new.__name__ = func.__name__
        return new

#PROMOTED WIDGETS
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
                
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-widget'):
            if event.dropAction() == Qt.CopyAction:
                event.accept()
            else:
                QTreeView.dragEnterEvent(self, event)
        else:
            event.ignore()
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat('application/x-widget'):
            if event.dropAction() == Qt.CopyAction:
                event.accept()
            else:
                QTreeView.dragMoveEvent(self, event)
        else:
            event.ignore()
            
    def dropEvent(self, event):
        if event.mimeData().hasFormat('application/x-widget'):
            if event.dropAction() == Qt.CopyAction:
                widget = core.widgetFromMimeData(event.mimeData())
                pos = QCursor.pos()
                mousePos = self.viewport().mapFromGlobal(QCursor.pos())
                index = self.indexAt(mousePos)
                model = index.model()
                if model:
                    parentWidget = model.widgetFromIndex(index)
                else:
                    parentWidget = None
                _logger.debug("Parenting under %r"  % parentWidget)
                self.rig.addWidget(widget, parent=parentWidget)                
                event.accept()
                
            elif event.dropAction() == Qt.MoveAction:
                QTreeView.dropEvent(self, event)
                
        else:
            event.ignore()

class WidgetList(QListWidget):
    def __init__(self, parent=None):
        _logger.debug('initializing promoted WidgetList')
        super(WidgetList, self).__init__(parent=parent)
        self.setDragEnabled(True)
        
    def startDrag(self, dropActions):
        widgetName = str(self.currentItem().text())
        widget = core.WidgetRegistry().getInstance(widgetName)
        drag = QDrag(self)
        drag.setMimeData(core.getWidgetMimeData(widget))
        drag.start(Qt.CopyAction)
        
#MAIN WIDGETS
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
        _logger.debug('initializing promoted RigWidget')
        uic.loadUi(getResource('rigwidget.ui'), self)
        self.rigView.setItemDelegate(RigViewDelegate(self))
        self.__registry = core.WidgetRegistry()
        #populate the widget list
        for wdg in self.__registry.widgetNames():
            self.widgetList.addItem(wdg)

    @pyqtSlot()
    @PopupError()
    def on_buildLayoutBtn_released(self):
        self.rigView.rig.buildLayout()
        
    @pyqtSlot()
    @PopupError()
    def on_buildRigBtn_released(self):
        self.rigView.rig.buildRig()
        
    @pyqtSlot()
    @PopupError()
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

