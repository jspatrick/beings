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
        self.setItemDelegate(RigViewDelegate(self.rig, self))
        
    def setModel(self, rig):
        self.rig = rig
        
        return super(WidgetTree, self).setModel(rig)
    
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
        

class WidgetAction(QAction):
    def __init__(self, *args, **kwargs):
        w = kwargs.pop('widget', None)
        self._widget = w
        super(WidgetAction, self).__init__(*args, **kwargs)
        self.connect(self, SIGNAL('triggered()'), self.widgetTrigger)
        
    def setWidget(self, w):
        self._widget = w

    def widgetTrigger(self):
        '''Emit a triggeredWidget signal with a widget'''
        self.emit(SIGNAL('triggeredWidget'), self._widget)
        
def staticKwargsFunc(func, **staticKwargs):
    """
    Wrap a function with static kwargs, but allow for args and additional kwargs
    """
    def new(*args, **kwargs):
       kwargs.update(staticKwargs)
       return func(*args, **kwargs)
    new.__name__ = func.__name__
    doc = func.__doc__ or ""
    new.__doc__ = "<Wrapped with wrapFunc>%s" % doc
    new.__dict__.update(func.__dict__)
    return new

class RigViewDelegate(QItemDelegate):
    def __init__(self, rig, parent=None):
        self._rig = rig
        super(RigViewDelegate, self).__init__(parent)
        
    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress and index.isValid():                        
            if event.button() == Qt.RightButton:
                widget = model.widgetFromIndex(index)
                
                menu = QMenu()
                rmAction = WidgetAction("Remove (preserve children)", self, widget=widget)
                self.connect(rmAction, SIGNAL('triggeredWidget'), self._rig.rmWidget)
                menu.addAction(rmAction)
                
                rmDeleteAction = WidgetAction("Remove (delete children)", self, widget=widget)
                self.connect(rmDeleteAction, SIGNAL('triggeredWidget'),
                             staticKwargsFunc(self._rig.rmWidget, removeChildren=True))
                menu.addAction(rmDeleteAction)
                
                mirrorAction = WidgetAction("Mirror", self, widget=widget)                
                self.connect(mirrorAction, SIGNAL('triggeredWidget'), self._rig.setMirrored)
                menu.addAction(mirrorAction)

                unmirrorAction = WidgetAction("Un-Mirror", self, widget=widget)
                self.connect(unmirrorAction, SIGNAL('triggeredWidget'), self._rig.setUnMirrored)
                menu.addAction(unmirrorAction)
                
                menu.exec_(self.parent().viewport().mapToGlobal(event.pos()))
                
        return super(RigViewDelegate, self).editorEvent(event, model, option, index)
    
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
        model = index.model()
        if index.column() == model.headers.index('Part'):
            widget = model.widgetFromIndex(index)
            editor.setText(widget.options.getValue('part'))
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
    def on_deleteRigBtn_released(self):
        self.rigView.rig.delete()
        
        
_ui = None
def initUI():            
    global _ui
    if type(_ui) != RigWidget:
        _ui = RigWidget()
    _ui.show()
    return _ui

