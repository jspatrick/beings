'''
Utils for tagging nodes

RigIt tags have the following syntax:
RITag_tagType: "key^value~key^value"
'''
import logging, copy
import maya.cmds as MC
from beings.utils.Exceptions import * #@UnusedWildImport
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
#constants
TAG_PREFIX = 'beings_'

def _strToDict(str_):
    return eval(str_)

def _dictToStr(dct):
    """Set the attribute to be an encoded string of dct"""
    return repr(dct)


class NodeTag(dict):
    """
    A dictionary-like object for tagging nodes
    >>> tag = NodeTag('myCoolTag')
    >>> tag['categories'] = ['x', 'y', 'z']
    >>> tag.setTag(node1, node2, node3)
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
        dict.__init__(self)
        
        self._tag = self.tagName(tag)
        if node:
            node = str(node)
            if MC.attributeQuery(self._tag, n=node, ex=1):
                tagStr = MC.getAttr('%s.%s' % (node, self._tag), type='string')
                self.update(_strToDict(tagStr))            

    def _addTag(self, nodes):
        for node in nodes:
            
            if not MC.attributeQuery(self._tag, n=node, ex=1):
                MC.addAttr(node, ln=self._tag, dt='string')
                
    def setTag(self, *nodes):
        nodes = [str(n) for n in nodes]
        self._addTag(nodes)
        for node in nodes:
            MC.setAttr('%s.%s' (node, self._tag), _dictToStr(self), type='string')


class ControlTag(NodeTag):
    """
    Tag rig controls
    """
    LOCK_ATTRS = ['lockedKeyable', 'unlockedKeyable', 'unlockedUnkeyable']
    _lockAttrMap = {'lk': 'lockedKeyable',
                 'uk': 'unlockedKeyable',
                 'uu': 'unlockedUnkeyable'}
    CONTROL_TAG = 'control'
    
    @classmethod
    def getControls(cls, root):
        '''Get all nodes under root that are controls'''        
        all = set(MC.ls("*.%s" % cls.tagName(cls.CONTROL_TAG), o=1) or [])
        all.intersection_update(MC.listRelatives(root, ad=1, pa=1) or [] + [root])
        return list(all)
    
    def __init__(self, node=None, dct=None):
        NodeTag.__init__(self, 'control', node=node, dct=dct)
        for attr in self.LOCK_ATTRS:
            self[attr] = self.get(attr, [])

    def __setitem__(self, k, v):     
        if k not in self.LOCK_ATTRS:
            k = self._lockAttrMap.get(k, None)
            if not k:
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
    
    #TODO:continue fixing node tags
    @classmethod
    def setLocks(cls, *nodes):
        """Set attribute locks on nodes"""
        for node in nodes:
            notSet =['message', 'translate', 'rotate', 'scale', 'rotatePivot', 'scalePivot', 'rotateAxis', 'selectHandle']
            for a in MC.listAttr(node, k=1):
                if a in notSet:
                    continue
                a = '%s.%s' % (node, a)
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
    nodeList = [str(node) for node in nodeList]
    parseList = copy.copy(nodeList)
    if getChildren:
        for node in nodeList:
            try:
                rels = MC.listRealtives(node, ad=1, pa=1) or []            
            parseList.extend([node for node in rels if node not in parseList])

    result = {}
    tagAttr = TAG_PREFIX + tag
    for node in parseList:
        if node.hasAttr(tagAttr):
            result[node] = NodeTag(tag, node=node)

    return result


