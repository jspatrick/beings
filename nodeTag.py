'''
Utils for tagging nodes

RigIt tags have the following syntax:
RITag_tagType: "key^value~key^value"
'''
import logging, copy
import maya.cmds as MC
from beings.utils.Exceptions import * #@UnusedWildImport
_logger = logging.getLogger(__name__)

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
    node = str(node)
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


def rmTag(node, tagName):
    node = str(node)
    if MC.attributeQuery(tagName, node=node, ex=1):
        MC.deleteAttr('%s.%s' % node, tagName)


def getNodesWithTag(tagname, inNodeList=None):
    tagAttr = getTagAttr(tagname)
    nodes = MC.ls('*.%s' % tagAttr, o=1) or []
    if inNodeList is not None:
        nodes = list(set(nodes).intersection(inNodeList))
    return nodes
