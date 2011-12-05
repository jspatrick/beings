'''
Utils for tagging nodes

RigIt tags have the following syntax:
RITag_tagType: "key^value~key^value"
'''
import logging, copy
import pymel.core as pm
from beings.utils.Exceptions import * #@UnusedWildImport
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
#constants
TAG_PREFIX = 'beings_'

def _strToDict(str_):
    return eval(str_)
    # #it should either be empty or have at least one element
    # if not str_:
    #     return {}
    # kpList = str_.split('~')
    # #pop off an empty item at the end, if there was a hanging tilde
    # if kpList[-1] == "":
    #     kpList.pop()
    # l = [item.split('^') for item in kpList]
    # d = {}
    # for k, v in l:
    #     v = eval(v)
    #     d[k] = v
    # return d

def _dictToStr(dct):
    """Set the attribute to be an encoded string of dct"""
    return repr(dct)
    # result = ''
    # for k, v in dct.items():
    #     strv = repr(v)
    #     if "^" or "~" in strv:
    #         _logger.error('Cannot have an attr key containing ~ or ^')
    #     result += '%s^%s~' % (k, strv)        
    # return result

class NodeTag(dict):
    """
    A dictionary-like object for tagging nodes
    """
    @classmethod
    def tagName(self, tag):
        if not tag.startswith(TAG_PREFIX):
            tag = TAG_PREFIX + tag
        return tag
    
    def __init__(self, tag, node=None, dct=None):
        """
        Store an attribute of an object internally
        """    
        self._tag = self.tagName(tag)

        dict.__init__(self)
        if node:
            node = pm.PyNode(node)            
            if node.hasAttr(self._tag):                
                tagStr =getattr(node, self._tag).get()
                self.update(_strToDict(tagStr))            
        
    def _addTag(self, nodes):
        for node in nodes:
            if not node.hasAttr(self._tag):
                node.addAttr(self._tag, dt='string')
                
    def setTag(self, *nodes):
        nodes = [pm.PyNode(n) for n in nodes]
        self._addTag(nodes)
        for node in nodes:
            getattr(node, self._tag).set(_dictToStr(self))

class ControlTag(NodeTag):
    """
    Tag rig controls
    """
    LOCK_ATTRS = ['lockedKeyable', 'unlockedKeyable', 'unlockedUnkeyable']
    CONTROL_TAG = 'control'
    @classmethod
    def getControls(cls, root):
        '''Get all nodes under root that are controls'''        
        all = set(pm.ls("*.%s" % cls.tagName(cls.CONTROL_TAG), o=1))
        all.intersection_update(pm.listRelatives(root, ad=1, pa=1) + [root])
        return list(all)
    
    def __init__(self, node=None, dct=None):
        NodeTag.__init__(self, 'control', node=node, dct=dct)
        for attr in self.LOCK_ATTRS:
            self[attr] = self.get(attr, [])

    def __setitem__(self, k, v):
        if k not in self.LOCK_ATTRS:
            _logger.warning("Invalid parameter %s, not setting" % k)
            return
        if not self._checkInput(v):
            return
        NodeTag.__setitem__(self, k, v)
        
    def _checkInput(self, v):
        if not isinstance(v, list):
            _logger.warning("Invalid parameter %r - must be a list" % v)
            return False
        for item in v:
            if not isinstance(item, basestring):
                _logger.warning("Invalid attr %r - not a string" % item)
                return False
        return True        

    @classmethod
    def setLocks(cls, *nodes):
        """Set attribute locks on nodes"""
        for node in nodes:
            notSet =['message', 'translate', 'rotate', 'scale', 'rotatePivot', 'scalePivot', 'rotateAxis',
                     'selectHandle']
            for a in pm.listAttr(node):
                if a in notSet:
                    continue
                a = pm.PyNode('%s.%s' % (node.name(), a))
                try:
                    a.setLocked(True)
                    a.setKeyable(False)
                except:
                    _logger.debug('Cannot lock %s.%s' % (node.name(), a))
                    pass            
            tag = cls(node=node)
            
            for attrName in tag['unlockedUnkeyable']:
                _logger.debug('setting locks on %s' % attrName)
                attr = getattr(node, attrName)
                attr.setKeyable(False)
                attr.setLocked(False)
            for attrName in tag['lockedKeyable']:
                _logger.debug('setting locks on %s' % attrName)
                attr = getattr(node, attrName)
                attr.setKeyable(False)
                attr.setLocked(True)
            for attrName in tag['unlockedKeyable']:
                _logger.debug('setting locks on %s' % attrName)
                attr = getattr(node, attrName)
                attr.setKeyable(True)
                attr.setLocked(False)
    @classmethod
    def unlock(cls, *nodes, **kwargs):        
        if kwargs.get('all', None):
            for node in nodes:
                for a in pm.listAttr(node):
                    a = pm.PyNode('%s.%s' % (node.name(), a))
                    try:
                        a.setLocked(False)
                    except:
                        pass
    def _setAction(self, attr, vals, action):
        if isinstance(vals, basestring):
            vals = [vals]
        current = set(self[attr])
        getattr(current, action)(vals)
        self[attr] = list(current)
        
    def add(self, attr, valList): self._setAction(attr, valList, 'update')
    def remove(self, attr, valList): self._setAction(attr, valList, 'difference_update')
    
def lockHierarchy(root):
    '''Lock all nodes in a hierarhcy'''
    allNodes = root.listRelatives(ad=1) + [root]
    ControlTag.setLocks(*allNodes)
    
def tagControl(control, uk=[], lk=[], uu=[], replace=False):
    act = 'add'
    if replace:
        act='__setitem__'    
    tag = ControlTag(control)
    actFunc = getattr(tag, act)
    actFunc('unlockedKeyable', uk)
    actFunc('unlockedUnkeyable', uu)
    actFunc('lockedKeyable', lk)
    tag.setTag(control)
    return tag
def getTaggedNodesTags(nodeList, tag, getChildren=True):
    """
    Return a {node:NodeTag} dict of all nodes tagged with tag
    @param nodeList: a list of string or PyNode nodes
    @param tag: a tag constant from this module
    @param getChildren = True: also return children of specified nodes
    @return dict: {PyNode: NodeTag,...}
    """
    #__enforceTags(tag)
    nodeList = [pm.PyNode(node) for node in nodeList]
    parseList = copy.copy(nodeList)
    if getChildren:
        for node in nodeList:
            parseList.extend([node for node in node.listRelatives(ad=True) if \
                              node not in parseList])

    result = {}
    tagAttr = TAG_PREFIX + tag
    for node in parseList:
        if node.hasAttr(tagAttr):
            result[node] = DctNodeTag(node, tag)

    return result

#convenience methods

def tagUnlocked(node, *args):
    """
    Tag a set of unlocked channels on a node and return the LockTag object
    @param *args:  attributes to tag as unlocked
    Currently this doesn't support tagging shape nodes
    """
    #check for valid node and attrs on that node
    node = pm.pPyNode(node)
    if isinstance(node, pm.nt.GeometryShape):
        return None

    badAttrs = []
    for arg in args:
        try:
            node.attr(arg)
        except pm.MayaAttributeError:
            badAttrs.append(arg)
    if badAttrs:
        raise RIError("Invalid attributes on %s: %s" % (str(node), ', '.join(badAttrs)))

    tag = tagNode(node, UNLOCKED_TAG)
    tag.addUnlocked(*args)
    return tag

def lockNodes(*args, **kwargs):
    """
    Lock all untagged attributes on all nodes in *args.
    @param onlyLockedTagged=False:  Only lock attributes on nodes that have been 
    tagged with an unlockedAttrs tag
    @param unlock=False:  unlock the nodes instead of locking
    """
    unlock = kwargs.get('unlock', False)
    onlyLockTagged = kwargs.get('onlyLockTagged', False)

    nodeList = [pm.PyNode(node) for node in args]
    lockTags = []

    if onlyLockTagged:
        lockTags = getTaggedNodesTags(nodeList, UNLOCKED_TAG, getChildren=False)

    else:
        lockTags = [tagNode(node, UNLOCKED_TAG) for node in nodeList if not isinstance(node, pm.nt.GeometryShape)]

    for tag in lockTags:
        if unlock:
            tag.unlock()
        else:
            tag.lock()

    return lockTags
