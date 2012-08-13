import logging
from observer import Observable

_logger = logging.getLogger(__name__)


class TreeItem(Observable):
    """
    An object that may have children and a parent.
    Tree items form a directed acyclical graph.
    """

    def __init__(self):
        super(TreeItem, self).__init__()
        self.__parent = None
        self.__children = []


    def parent(self): return self.__parent
    def _setParent(self, parent):
        self.__parent = parent

    def children(self, recursive=False):
        result = []
        for child in self.__children:
            if recursive:
                result.extend(child.children())
            result.append(child)
        return result

    def childIndex(self, child):
        try:
            return self.__children.index(child)
        except:
            _logger.error("Trying to find %r in %s" % (child, self.__children))
            raise

    def root(self):
        node = self
        while node.__parent is not None:
            node = node.__parent
        return node

    def addedChild(self, child):
        """Can be overridden by subclasses to customize behvaior after a
        child is added"""
        pass

    def removedChild(self, child):
        """Can be overridden by subclassed to customize behavior after a child
        is removed"""
        pass

    def addChild(self, child, plug=""):

        #don't allow the same instance in the tree twice
        root = self.root()
        ids = [id(w) for w in root.children(recursive=True)]
        ids.append(id(root))
        if id(child) in ids:
            raise RuntimeError("Cannot add the same instance twice")

        child._setParent(self)
        self.__children.append(child)
        self.addedChild(child)

        self.notify('addedChild', parent=self, child=child)
        parent = self.parent()
        while parent:
            parent.notify('addedChild', parent=self, child=child)
            parent = parent.parent()

    def _reparentGrandchildren(self, child):
        grandChildren = child.children(recursive=False)
        for grandChild in grandChildren:
            child.rmChild(grandChild)
            self.addChild(grandChild)

    def rmChild(self, child, reparentChildren=False):
        """
        Remove a child
        @param reparentChildren=True: if True, reparent child's children to the this obj.
        """
        _logger.debug("removing %r" % child)
        _logger.debug("Current children before removing: %r" % self.__children)

        if reparentChildren:
            self._reparentGrandchildren(child)

        index = self.childIndex(child)
        self.__children.pop(index)
        child._setParent(None)
        self.removedChild(child)

        self.notify('removedChild', parent=self, child=child)

        parent = self.parent()
        while parent:
            parent.notify('removedChild', parent=self, child=child)
            parent = parent.parent()

        return child



class PluggedTreeItem(TreeItem):
    """
    Plugged Tree items must define their available plugs.
    When children are added, they are added
    to a particular plug in the parent item.
    Plugs must be configured on the TreeItem instances
    before children are added.

    The root tree item may have a null plug ("").
    As soon as the item is not a root, this null
    plug is removed.
    """

    def __init__(self, plugs=None):
        super(PluggedTreeItem, self).__init__()

        if not plugs:
            plugs = []
        self.__plugs = set([str(p) for p in plugs])
        self.__childPlugs = []

    def plugOfChild(self, child): return self.__childPlugs[self.childIndex(child)]

    def setChildPlug(self, child, plug):
        if plug not in self.plugs():
            _logger.warning("invalid plug '%s'" % plug)
            return False
        index = self.childIndex(child)
        self.__childPlugs[index] = plug

    def plugs(self): return list(self.__plugs)
    def addPlug(self, plugName):
        self.__plugs.add(str(plugName))
    def rmPlug(self, plugName): self.__plugs.difference_update(str(plugName))

    def addChild(self, child, plug=""):
        if not self.__plugs:
            raise RuntimeError("must add plugs to the parent before adding a child")
        if not plug:
            _logger.debug("plug not specified, using first available")
            plug = self.plugs()[0]
        elif plug not in self.plugs():
            raise KeyError("Invalid plug '%s'" % plug)

        self.__childPlugs.append(plug)

        try:
            return super(PluggedTreeItem, self).addChild(child)
        except:
            self.__childPlugs.pop()
            raise

    def _reparentGrandchildren(self, child):
        grandChildren = child.children(recursive=False)
        plug = self.plugs()[0]

        for grandChild in grandChildren:
            child.rmChild(grandChild)
            self.addChild(grandChild, plug=plug)


    def rmChild(self, child, reparentChildren=False):
        """
        Remove a child
        @param reparentChildren=True: if True, reparent child's children to the this obj.
        """
        _logger.debug("Removing '%s'" % child)
        index = self.childIndex(child)
        self.__childPlugs.pop(index)
        return super(PluggedTreeItem, self).rmChild(child, reparentChildren=reparentChildren)
