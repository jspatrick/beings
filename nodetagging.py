'''
Utils for tagging nodes

RigIt tags have the following syntax:
RITag_tagType: "key^value~key^value"
'''
import logging, copy
import pymel.core as pm
from utils.Exceptions import * #@UnusedWildImport

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

#constants
TAG_PREFIX = 'RItag_'

#tag types
UNLOCKED_TAG = 'unlockedAttrs'


g_allTags = (UNLOCKED_TAG,)

class DctNodeTag(object):
    """
    A dictionary-like object for tagging nodes
    """

    def __init__(self, node, tag, dct=None):
        """
        Store an attribute of an object internally
        """
        #if it's not passed with the prefix, add it
        if not tag.startswith(TAG_PREFIX):
            tag = TAG_PREFIX + tag

        node = pm.PyNode(node)
        self.node = node

        try:
            self.nodeAttr = pm.Attribute(node.name() + "." + tag)

        except:
            #create the node tag if not already created
            #self._enforceTags(tag.strip(TAG_PREFIX))

            try:
                assert(isinstance(node, pm.nt.Transform))
            except AssertionError:
                logger.debug('Tagger is tagging a non-transform node, "%s"' % node.name())

            #udAttrs = node.listAttr(ud=True)

            #add the attribute if it's not there yet
            #if "%s.%s" % (node.name(), tag) not in [attr.name() for attr in udAttrs]:
            node.addAttr(tag, dt='string')
            self.nodeAttr = pm.Attribute(node.name() + "." + tag)

        if dct is not None:
            self.nodeAttr.set(self._dictToAttr(dct))

    def _attrToDict(self):
        str_ = self.nodeAttr.get()
        #it should either be empty or have at least one element
        if not str_:
            return {}
        kpList = str_.split('~')
        #pop off an empty item at the end, if there was a hanging tilde
        if kpList[-1] == "":
            kpList.pop()
        l = [item.split('^') for item in kpList]
        d = {}
        for k, v in l:
            #try to cast the string as some basic data types
            if v == 'True':
                v = True
            elif v == 'False':
                v = False
            elif v == 'None':
                v = None
            else:
                try:
                    v = int(v)
                except ValueError:
                    try:
                        v = float(v)
                    except ValueError:
                        pass
            d[k] = v
        return d

    def _dictToAttr(self, dct):
        """Set the attribute to be an encoded string of dct"""

        result = ''
        for k, v in dct.items():
            result += '%s^%s~' % (k, v)
        self.nodeAttr.set(result)
        return result[:-1]

#    @staticmethod
#    def _enforceTags(tag):
#        if tag not in g_allTags:
#            raise RIError('%s is not a valid tag.  Valid tags include: %s' \
#                          % (tag, ", ".join(g_allTags)))
            
    def clear(self):
        """Reset the node tag"""
        self._dictToAttr({})

    def __delitem__(self, k):
        d = self._attrToDict()
        del d[k]
        self._dictToAttr(d)

    def __setitem__(self, k, v):
        d = self._attrToDict()
        d[k] = v
        self._dictToAttr(d)

    def __getitem__(self, k):
        d = self._attrToDict()
        return d[k]

    def __contains__(self, x):
        d = self._attrToDict()
        return x in d

    def keys(self):
        d = self._attrToDict()
        return d.keys()

    def values(self):
        d = self._attrToDict()
        return d.values()

    def items(self):
        d = self._attrToDict()
        return d.items()

    def __str__(self):
        d = self._attrToDict()
        return str(d)



class LockNodeTag(DctNodeTag):
    """
    A Node Tag subclass for working with a Node Lock tag
    """
    def __init__(self, node, dct=None):
        super(LockNodeTag, self).__init__(node, UNLOCKED_TAG, dct)
        self.state = 'unlocked'

    def addUnlocked(self, *attrs):
        msg = ""
        for attr in attrs:
            try:
                attr = self.node.attr(attr)
                self.__setitem__(attr.name(includeNode=False), True)
            except pm.MayaAttributeError:
                msg += "%s is not a valid attribute on %s\n" % (attr, self.node.name())
        if msg:
            raise RIError(msg)

    def getUnlocked(self):
        """
        Return attrs that will be excluded from locking
        """
        return [k for k, v in self.items() if v == True]

    def getLocked(self):
        """
        Return attributes that have been locked by the NodeLock
        """
        return [k for k, v in self.items() if v == False]

    def lock(self):
        """
        lock all untagged, keyable attributes of node    
        """
        unlocked = self.getUnlocked()
        for attr in self.node.listAttr(keyable=True):
            if attr.name(includeNode=False) in unlocked:
                continue
            attr.lock()
            attr.set(keyable=False)
            attr.set(channelBox=False)
            #set the attr as False in the dict so we know it's been locked here
            self.__setitem__(attr.name(includeNode=False), False)

    def unlock(self):
        """
        unlock attrs that were locked
        """
        locked = self.getLocked()
        for attr in locked:
            attr = self.node.attr(attr)
            attr.unlock()
            attr.set(channelBox=True)
            attr.set(keyable=True)
            self.__delitem__(attr.name(includeNode=False))

def tagNode(node, tag):
    """
    Tag a node with an attribute.  If the tag attribute exists, do nothing.
    @Return: NodeTag 
    """
    if UNLOCKED_TAG in tag:
        return LockNodeTag(node)

    return DctNodeTag(node, tag)


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
    node = pm.PyNode(node)
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
