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

TAG_PREFIX = 'beingsTag_'

#--------------------Base Tagging Functions--------------------
def getTagAttr(tagName):
    if not tagName.startswith(TAG_PREFIX):
        tagName = TAG_PREFIX + tagName
    return tagName

def _addTagAttr(nodes, tagName):
    tagAttr = getTagAttr(tagName)
    for node in nodes:
        if not MC.attributeQuery(tagAttr, n=node, ex=1):
            MC.addAttr(node, ln=tagAttr, dt='string')

def setTag(node, tagName, dct):
    if not isinstance(dct, dict):
        raise TypeError("tag value must be a dictionary")

    _addTagAttr([node], tagName)

    tagAttr = getTagAttr(tagName)
    MC.setAttr('%s.%s' % (node, tagAttr), repr(dct), type='string')

def hasTag(node, tagName):
    tagAttr = getTagAttr(tagName)
    if MC.attributeQuery(tagAttr, n=node, ex=1):
        return True
    return False

def getTag(node, tagName, noError=False):
    node = str(node)
    tagAttr = getTagAttr(tagName)

    result = {}
    if MC.attributeQuery(tagAttr, n=node, ex=1):
        tagStr = MC.getAttr('%s.%s' % (node, tagAttr))
        result = eval(tagStr)

    elif not noError:
        raise RuntimeError("%s does not have a '%s' tag" % (node, tagName))

    return result

def getNodesWithTag(tagname):
    tagAttr = getTagAttr(tagname)
    return MC.ls('*.%s' % tagAttr, o=1) or []

#--------------------Control Tagging Functions--------------------
# LOCK_ATTRS = ['lockedKeyable', 'unlockedKeyable', 'unlockedUnkeyable']
# LOCK_ATTTR_MAP = {'lk': 'lockedKeyable',
#                  'uk': 'unlockedKeyable',
#                  'uu': 'unlockedUnkeyable'}
# CONTROL_TAG_NAME = 'control'

# def tagControl(node, replaceProvided=False, reset=False **kwargs):
#     """
#     Tag a node as a control
#     @param node: the node to tag
#     @param replaceProvided: if the node already has control tags,
#     replace them with the supplied control values.  Any
#     unpassed category will remain intact.
#     @param reset=False: like replaceProvided, except that any
#     unpassed categories will reset to an empty list

#     @keyword lk/lockedKeyable: lockedKeyable controls.  Default to empty list
#     @keyword uk/unlockedKeyable: unlockedKeyable controls.
#     @keyworkd uu/unlockedUnkeyable: unlockedUnkeyable ctls
#     """

#     if not MC.objectType(node, isAType='transform'):
#         raise RuntimeError('only xforms can be controls')

#     lockedKeyable = kwargs.get('lk', kwargs.get('lockedKeyable', []))n
#     unlockedKeyable = kwargs.get('uk', kwargs.get('unlockedKeyable', []))
#     unlockedUnkeyable = kwargs.get('uu', kwargs.get('unlockedUnkeyable', []))



# def getControls(root):
#     """Get all nodes tagged as controls under and including the root node"""




#     @classmethod
#     def getControls(cls, root):
#         '''Get all nodes under root that are controls'''
#         all = set(MC.ls("*.%s" % cls.tagAttr(cls.CONTROL_TAG), o=1) or [])
#         all.intersection_update(MC.listRelatives(root, ad=1, pa=1) or [] + [root])
#         return list(all)

#     def __init__(self, node=None, dct=None):
#         NodeTag.__init__(self, 'control', node=node, dct=dct)
#         for attr in self.LOCK_ATTRS:
#             self[attr] = self.get(attr, [])

#     def __setitem__(self, k, v):
#         if k not in self.LOCK_ATTRS:
#             k = self._lockAttrMap.get(k, None)
#             if not k:
#                 _logger.warning("Invalid parameter %s, not setting" % k)
#                 return
#         if not self._checkInput(v):
#             return
#         NodeTag.__setitem__(self, k, v)

#     def _checkInput(self, v):
#         if not isinstance(v, list):
#             _logger.warning("Invalid parameter %r - must be a list" % v)
#             return False
#         for item in v:
#             if not isinstance(item, basestring):
#                 _logger.warning("Invalid attr %r - not a string" % item)
#                 return False
#         return True

#     #TODO:continue fixing node tags
#     @classmethod
#     def setLocks(cls, *nodes):
#         """Set attribute locks on nodes"""
#         for node in nodes:
#             notSet =['message', 'translate', 'rotate', 'scale', 'rotatePivot', 'scalePivot', 'rotateAxis', 'selectHandle']
#             for a in MC.listAttr(node, k=1):
#                 if a in notSet:
#                     continue
#                 a = '%s.%s' % (node, a)
#                 try:
#                     a.setLocked(True)
#                     a.setKeyable(False)
#                 except:
#                     _logger.debug('Cannot lock %s.%s' % (node.name(), a))
#                     pass
#             tag = cls(node=node)

#             for attrName in tag['unlockedUnkeyable']:
#                 _logger.debug('setting locks on %s' % attrName)
#                 attr = getattr(node, attrName)
#                 attr.setKeyable(False)
#                 attr.setLocked(False)
#             for attrName in tag['lockedKeyable']:
#                 _logger.debug('setting locks on %s' % attrName)
#                 attr = getattr(node, attrName)
#                 attr.setKeyable(False)
#                 attr.setLocked(True)
#             for attrName in tag['unlockedKeyable']:
#                 _logger.debug('setting locks on %s' % attrName)
#                 attr = getattr(node, attrName)
#                 attr.setKeyable(True)
#                 attr.setLocked(False)
#     @classmethod
#     def unlock(cls, *nodes, **kwargs):
#         if kwargs.get('all', None):
#             for node in nodes:
#                 for a in pm.listAttr(node):
#                     a = pm.PyNode('%s.%s' % (node.name(), a))
#                     try:
#                         a.setLocked(False)
#                     except:
#                         pass
#     def _setAction(self, attr, vals, action):
#         if isinstance(vals, basestring):
#             vals = [vals]
#         current = set(self[attr])
#         getattr(current, action)(vals)
#         self[attr] = list(current)

#     def add(self, attr, valList): self._setAction(attr, valList, 'update')
#     def remove(self, attr, valList): self._setAction(attr, valList, 'difference_update')


# # def lockHierarchy(root):
# #     '''Lock all nodes in a hierarhcy'''
# #     allNodes = root.listRelatives(ad=1) + [root]
# #     ControlTag.setLocks(*allNodes)

# # def tagControl(control, uk=[], lk=[], uu=[], replace=False):
# #     act = 'add'
# #     if replace:
# #         act='__setitem__'
# #     tag = ControlTag(control)
# #     actFunc = getattr(tag, act)
# #     actFunc('unlockedKeyable', uk)
# #     actFunc('unlockedUnkeyable', uu)
# #     actFunc('lockedKeyable', lk)
# #     tag.setTag(control)
# #     return tag


# # def getTaggedNodesTags(nodeList, tag, getChildren=True):
# #     """
# #     Return a {node:NodeTag} dict of all nodes tagged with tag
# #     @param nodeList: a list of string or PyNode nodes
# #     @param tag: a tag constant from this module
# #     @param getChildren = True: also return children of specified nodes
# #     @return dict: {PyNode: NodeTag,...}
# #     """
# #     #__enforceTags(tag)
# #     nodeList = [str(node) for node in nodeList]
# #     parseList = copy.copy(nodeList)
# #     if getChildren:
# #         for node in nodeList:
# #             try:
# #                 rels = MC.listRealtives(node, ad=1, pa=1) or []
# #             parseList.extend([node for node in rels if node not in parseList])

# #     result = {}
# #     tagAttr = TAG_PREFIX + tag
# #     for node in parseList:
# #         if node.hasAttr(tagAttr):
# #             result[node] = NodeTag(tag, node=node)

# #     return result
