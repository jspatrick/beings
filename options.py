import logging, re, copy, os, sys
print sys.executable

from beings.treeItem import TreeItem
from PyQt4 import QtGui, QtCore

_logger = logging.getLogger(__name__)


class OptionCollection(Observable):
    def __init__(self):
        '''
        A collection of options
        '''
        super(OptionCollection, self).__init__()

        self.__options = {}
        self.__presets = {}
        self.__rules = {}
        self.__optPresets = {}
        self.__defaults = {}

    def addOpt(self, optName, defaultVal, optType=str, **kwargs):
        """
        @keyword optType: type type (default to str)
        @event optionAdded: optName(str)
        """
        self.__options[optName] = optType(defaultVal)
        self.__defaults[optName] = optType(defaultVal)
        self.__rules[optName] = {}
        self.__rules[optName]['optType'] = optType
        self.__rules[optName]['hidden'] = kwargs.get('hidden', False)
        self.__rules[optName]['min'] =  kwargs.get('min', None)
        self.__rules[optName]['max'] = kwargs.get('max', None)
        presets = kwargs.get('presets')
        if presets:
            self.setPresets(optName, *presets)
        if not kwargs.get('quiet'):
            self.notify('optAdded', optName=optName)

    def _checkName(self, optName):
        if optName not in self.__options:
            raise utils.BeingsError("Invalid option %s") % optName

    def setRule(self, opt, rule, value):
        currentVal = self.__rules[opt].get(rule, None)
        if currentVal is None:
            raise utils.BeingsError("Invalid rule %s" % rule)

    def setPresets(self, optName, *args, **kwargs):
        self._checkName(optName)
        replace = kwargs.get('replace', False)
        if replace:
            self.__presets[optName] = set(args)
        else:
            presets = self.__presets.get(optName, set([]))
            presets = presets.union(args)
            self.__presets[optName] = presets

    def getRules(self, optName):
        return copy.deepcopy(self.__rules[optName])

    def getPresets(self, optName):
        self._checkName(optName)
        r = self.__presets.get(optName, None)
        if r:
            return sorted(list(r))
        else:
            return None

    def getValue(self, optName):
        self._checkName(optName)
        return self.__options[optName]

    def setValue(self, optName, val, quiet=False):
        """
        @event optAboutToChange: optName(str), oldVal(str), newVal(str)
        @event optSet: optName(str), newVal(str)
        @event optChanged: optName(str), oldVal(str), newVal(str)
        """
        self._checkName(optName)
        changed=False
        if val != self.__options[optName]:
            changed = True
        oldVal = self.__options[optName]

        if not quiet:
            if changed:
                self.notify('optAboutToChange', optName=optName, oldVal=oldVal, newVal=val)

        #validate the new value
        presets = self.getPresets(optName)
        if presets and val not in presets:
            raise ValueError('Invalid value "%r"' % val)
        min_ = self.__rules[optName].get('min', None)
        max_ = self.__rules[optName].get('max', None)
        if min_ is not None and val < min_:
            raise ValueError('Minimum val is %; got %s' % (min_, val))
        if max_ is not None and val > max:
            raise ValueError('Maximum val is %; got %s' % (max_, val))

        self.__options[optName] = val

        if not quiet:
            self.notify('optSet', optName=optName, newVal=val)
            if changed:
                self.notify('optChanged', optName=optName, oldVal=oldVal, newVal=val)

    #TODO:  Get option data
    def getData(self):
        '''Return the values of all options not set to default values'''
        return copy.deepcopy(self.__options)

    def setFromData(self, data):
        '''
        Set options based on data gotten from getData
        '''
        for opt, val in data.items():
            self.setValue(opt, val)

    def getAllOpts(self, includeHidden=True):
        result = copy.deepcopy(self.__options)
        if not includeHidden:
            tmp = result
            result = {}
            for opt, val in tmp.iteritems():
                if not self.__rules[opt]['hidden']:
                    result[opt] = val
        return result

    def setAllOpts(self, optDct):
        for optName, optVal in optDct.items():
            self.setValue(optName, optVal)

#todo: implement delegate
class OptionCollectionModel(QtCore.QAbstractItemModel):
    #any method that changes options should call the refresh method
    #to update the object's internal data

    _columns = ['Option', 'Value']
    def __init__(self, optionCollection, parent=None):
        super(OptionCollectionModel, self).__init__(parent=parent)
        assert isinstance(optionCollection, OptionCollection)
        self.__optionCollection = optionCollection
        self.__optionCollection.subscribe('optSet', self._optChanged)
        self.__optionCollection.subscribe('optAdded', self._optAdded)
        self.__refresh()

    def _optAdded(self, event):
        self.__refresh()

    def _optChanged(self, event):
        self.__refresh()

    def __refresh(self):
        #todo: instead of resetting, compare new data against old and modify
        #as needed
        opts = self.__optionCollection.getAllOpts(includeHidden=False)
        self.__keys = sorted(opts.keys())
        self.__values = [opts[k] for k in self.__keys]
        self.reset()

    def columnCount(self, parentIndex):

        return len(self._columns)

    def rowCount(self, parentIndex):
        if not parentIndex.isValid():
            return len(self.__keys)
        return 0

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal:
            if role == QtCore.Qt.DisplayRole:
                if section == 0:
                    return "Option"
                elif section == 1:
                    return "Value"

        return QtCore.QVariant()

    
    def data(self, index, role):
        if index.isValid() and role == QtCore.Qt.DisplayRole:
            row = index.row()
            col = index.column()
            if col == (self._columns.index('Option')):
                return self.__keys[row]

            elif col == (self._columns.index('Value')):
                pyVal = self.__values[row]

                if type(pyVal) not in [str, int, float]:
                    _logger.warning("non-core option typing not implemented")
                    return QtCore.QVariant()

                return pyVal

        return QtCore.QVariant()

    def parent(self, index):
        return QtCore.QModelIndex()

    def index(self, row, col, parentIndex):
        if not parentIndex.isValid():
            return self.createIndex(row, col)
        return QtCore.QModelIndex()

    def setData(self, index, value, role):

        if index.isValid() and role == QtCore.Qt.EditRole:
            row = index.row()
            col = index.column()

            if col == (self._columns.index('Value')):
                key = self.__keys[row]
                rules = self.__optionCollection.getRules(key)

                optType = rules['optType']
                if optType == str:
                    value = str(value.toString())
                elif optType == int:
                    value = int(value.toDouble()[0])
                elif optType == float:
                    value = float(value.toDouble()[0])
                else:
                    raise NotImplementedError("invalid type %r" % optType)

                self.__optionCollection.setValue(key, value)
                self.__refresh()

                ind = self.index(row, col, QtCore.QModelIndex())
                self.emit(QtCore.SIGNAL('dataChanged(QModelIndex, QModelIndex)'),
                                        ind,
                                        ind)
                return True

        return False

    def flags(self, index):

        flags =  QtCore.Qt.ItemIsEnabled
        if index.column() == self._columns.index('Value'):
            flags = flags | QtCore.Qt.ItemIsEditable

        return flags



if __name__ == '__main__':
    import beings.options as O
    import PyQt4.QtGui as QTG
    import PyQt4.QtGui as QTC

    reload(O)

    oc = O.OptionCollection()
    oc.addOpt('testOpt', 20, optType=int)
    oc.addOpt('testOpt2', 20.234, optType=float)
    oc.addOpt('name', 'chester')
    oc.addOpt('name2', 'chesterasdf')
    oc.setValue('name', 'poo')
    ocm = O.OptionCollectionModel(oc)
    tm = QTG.QTreeView()
    tm.setModel(ocm)
    tm.show()
