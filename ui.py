import logging, sys, os, json
from functools import partial
_logger = logging.getLogger(__name__)

__rootLevel = logging.getLogger().level

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic
import core
import utils
import options
#seems like importing pyqt changes root logger level to 0
logging.getLogger().setLevel(__rootLevel)

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
        self.rig = core.RigModel()
        self.setModel(self.rig)
        self.rig.reset()
        self.setAnimated(True)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.showDropIndicator()
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.expandAll()
        self.setItemDelegate(RigViewDelegate(self))

        self.clicked.connect(self.onSelectionChanged)

    def onSelectionChanged(self):
        index = self.selectedIndexes()[0]
        model = self.model()
        widget = model.widgetFromIndex(index)
        self.emit(SIGNAL('widgetSelected'), widget)

    def setModel(self, rig):
        self.rig = rig
        super(WidgetTree, self).setModel(rig)
        self.rig.reset()


class WidgetList(QListWidget):
    def __init__(self, parent=None):
        _logger.debug('initializing promoted WidgetList')
        super(WidgetList, self).__init__(parent=parent)
        self.setDragEnabled(True)

    def startDrag(self, dropActions):
        widgetName = str(self.currentItem().text())
        data = QByteArray()
        stream = QDataStream(data, QIODevice.WriteOnly)
        stream << QString(widgetName)
        mimeData = QMimeData()
        mimeData.setData("application/x-widget-classname", data)
        drag = QDrag(self)
        drag.setMimeData(mimeData)
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
    def __init__(self, parent=None):
        super(RigViewDelegate, self).__init__(parent)

    @property
    def _rig(self):
        return self.parent().rig

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress and index.isValid():
            if event.button() == Qt.RightButton:
                widget = model.widgetFromIndex(index)
                menu = QMenu()

                if widget.children:
                    #TODO: fix this
                    # rmAction = QAction("Remove (preserve children)", self)
                    # self.connect(rmAction, SIGNAL('triggered()'),
                    #              partial(widget.parent().rmChild, widget, reparentChildren=True ))
                    # menu.addAction(rmAction)

                    rmDeleteAction = QAction("Remove (delete children)", self)
                    self.connect(rmDeleteAction, SIGNAL('triggered()'),
                                 partial(widget.parent().rmChild, widget))
                    menu.addAction(rmDeleteAction)

                else:
                    rmDeleteAction = QAction("Remove", self)
                    self.connect(rmDeleteAction, SIGNAL('triggered()'),
                                     partial(widget.parent().rmChild, widget))

                    menu.addAction(rmDeleteAction)


                mirrorAction = QAction("Mirror", self)
                self.connect(mirrorAction, SIGNAL('triggered()'), partial(self.setMirrored, widget, True, index, model))
                menu.addAction(mirrorAction)

                unmirrorAction = QAction("Un-Mirror", self)
                self.connect(unmirrorAction, SIGNAL('triggered()'), partial(self.setMirrored, widget, False, index, model))
                menu.addAction(unmirrorAction)

                menu.exec_(self.parent().viewport().mapToGlobal(event.pos()))

        return super(RigViewDelegate, self).editorEvent(event, model, option, index)

    def setMirrored(self, widget, val, index, model):

        widget.setMirrored(val)
        model.refreshWidgetItems(widget)

        other = widget.getMirrorableWidget()
        if other:
            model.refreshWidgetItems(other)

        else:
            _logger.warning("cannot get mirrored widget")

    def createEditor(self, parent, option, index):
        model = index.model()
        if index.isValid():
            widget = model.widgetFromIndex(index)
        else:
            widget = model.root

        if index.column() == model.headers.index('Side'):
            combobox = QComboBox(parent)
            sides = widget.options.getPresets('side')
            combobox.addItems(sides)
            combobox.setEditable(False)
            return combobox

        elif index.column() == model.headers.index('Parent Part'):
            parts = widget.parent().plugs()
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

        widget = model.widgetFromIndex(index)
        item = model.itemFromIndex(index)

        if index.column() == model.headers.index('Side'):
            widget.options.setValue('side', str(editor.currentText()))
            item.setText(editor.currentText())
            
        elif index.column() == model.headers.index('Parent Part'):
            widget.parent().setChildPlug(widget, str(editor.currentText()))
            item.setText(editor.currentText())
        else:
            up = editor.metaObject().userProperty()
            val = str(up.read(editor).toString())
            item.setText(val)
            if index.column() == model.headers.index('Part'):
                widget.options.setValue('part', val)



class RigWidget(QWidget):
    def __init__(self, parent=None):

        super(RigWidget, self).__init__(parent=parent)
        _logger.debug('initializing promoted RigWidget')
        uic.loadUi(getResource('rigwidget.ui'), self)
        self.__fileName = None
        self.__registry = core.WidgetRegistry()
        #populate the widget list
        for wdg in self.__registry.widgetNames():
            self.widgetList.addItem(wdg)
        self.menuBar = QMenuBar(self)

        self.options = options.OptionCollection()
        self.options.addOpt('lock', True, optType=bool)
        self.rigOptionsView.setModel(options.OptionCollectionModel(self.options))
        self.options.addOpt('character name', 'char', optType=str)

        fileMenu = self.menuBar.addMenu('&File')
        newAction = self.createAction('&New', slot=self.fileNew)
        saveAsAction = self.createAction("&Save As..", slot=self.saveRig)
        loadAction = self.createAction("&Open..", slot=self.fileOpen)
        fileMenu.addActions([newAction, saveAsAction, loadAction])

        self.connect(self.rigView, SIGNAL('widgetSelected'), self.onWidgetSelected)

    def createAction(self, text, slot=None, shortcut=None, icon=None,
                     tip=None, checkable=False, signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action

    def onWidgetSelected(self, widget):
        model = options.OptionCollectionModel(widget.options)
        self.widgetOptionsView.setModel(model)

    def fileOpen(self):
        """browse to a file and load rig"""
        dir = os.path.dirname(self.__fileName) \
                if self.__fileName is not None else "."
        fname = unicode(QFileDialog.getOpenFileName(self,
                            "Beings - Choose Rig File", dir,
                            "Beings Database (*.brd)"))

        if fname:
            with open(fname) as f:
                data = core.loadJsonData(f)
            self.loadRig(data)
        self.__fileName = str(fname)

    def fileNew(self):
        rig = core.RigModel("mychar")
        self.rigView.setModel(rig)

    def saveRig(self):
        """Save the rig data to a file"""

        filePath = QFileDialog.getSaveFileName(None,
                            "Beings - Save rig file", ".",
                            "Beings Database (*.brd)")
        if filePath:
            data = core.getSaveData(self.rigView.model().root)
            with open(filePath, 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=True)
        self.__fileName = str(filePath)
        _logger.info("Saved rig as %s" % filePath)

    def loadRig(self, data):
        """Load the rig data
        @param data:  a rig dictionary"""
        root = core.rigFromData(data)
        self.rigView.model().root = root
        self.rigView.model().reset()

    def _root(self):
        return self.rigView.model().root

    @pyqtSlot()
    @PopupError()
    def on_buildLayoutBtn_released(self):
        root = self._root()
        charName = self.options.getValue('character name')
        root.options.setValue('char', charName)
        for child in root.children(recursive=True):
            child.options.setValue('char', charName)

        root.buildLayout()
        if self.options.getValue('lock'):
            root.lockNodes()


    @pyqtSlot()
    @PopupError()
    def on_buildRigBtn_released(self):
        root = self._root()
        charName = self.options.getValue('character name')
        root.options.setValue('char', charName)
        for child in root.children(recursive=True):
            child.options.setValue('char', charName)

        root.buildRig()
        if self.options.getValue('lock'):
            root.lockNodes()


    @pyqtSlot()
    @PopupError()
    def on_deleteRigBtn_released(self):
        self.rigView.model().root.delete(deleteChildren=True)


_ui = None
def initUI():
    global _ui
    if type(_ui) != RigWidget:
        _ui = RigWidget()
    _ui.show()
    return _ui
