'''
A class that will track node creation 
'''
import logging
import maya.OpenMaya as OM
import pymel.core as PM

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.DEBUG)

def pathFromMObj(mObj):
    """
    Return a unique path to an mObject
    """
    if mObj.hasFn(OM.MFn.kDagNode):
        result = OM.MFnDagNode(mObj).partialPathName()
    elif mObj.hasFn(OM.MFn.kDependencyNode):
        result = OM.MFnDependencyNode(mObj).name()
    else:
        result = "ERROR"
    return result

def nodeAddedCallback(list_):
    def callback(mObj, clientData):
        logger.debug("Checking node of type %s" % mObj.apiTypeStr())
        logger.debug("seeing whether %s should be added" % pathFromMObj(mObj))
        handle = OM.MObjectHandle(mObj)
        list_.append(handle)
    return callback

class NodeTracker(object):
    '''
    A class for tracking Maya Objects as they are created and deleted.
    Can (and probably should) be used as a context manager
    '''

    def __init__(self):
        self._addedCallbackID = None
        self._objects = []

    def startTrack(self):
        if not self._addedCallbackID:
            logger.debug("%s: Beginning object tracking" % str(self))
            self._addedCallbackID = OM.MDGMessage.addNodeAddedCallback(nodeAddedCallback(self._objects))
            logger.debug("registered node added callback")

    def endTrack(self):
        """
        Stop tracking and remove the callback
        """

        if self._addedCallbackID:
            logger.debug("%s: Ending object tracking" % str(self))
            OM.MMessage.removeCallback(self._addedCallbackID)
            self._addedCallbackID = None
            logger.debug("deregistered node added callback")

    def getObjects(self, asPyNodes=True):
        """
        Return a list of maya objects as strings.
        """
        result = []

        toRemove = []
        for objHandle in self._objects:
            logger.debug("Object valid status: %s" % str(objHandle.isValid()))
            logger.debug("Object alive status: %s" % str(objHandle.isAlive()))
            if not objHandle.isValid():
                toRemove.append(objHandle)
            else:
                nodeName = pathFromMObj(objHandle.object())
                #pymel's undo node should be ignored
                if nodeName != '__pymelUndoNode':
                    result.append(nodeName)

        for objHandle in toRemove:
            self._objects.remove(objHandle)

        if asPyNodes:
            result = [PM.PyNode(n) for n in result]

        return result

    def isTracking(self):
        """
        Return True/False
        """
        if self._addedCallbackID:
            return True
        return False


    def reset(self):
        self.endTrack()
        self._objects = []

    def __enter__(self):
        self.startTrack()
        return self

    def __exit__(self, exctype, excval, exctb):
        self.endTrack()


    def __del__(self):
        """
        Ensure tracking has ended
        """
        if self.isTracking():
            self.endTrack()
            logger.warning("%s: Ending tracking on garbage collected Tracker" % str(self))
