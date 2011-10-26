'''
Decorators and context managers
'''
import pymel.core as pm
import logging
import NodeTracking as NT

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def TrackBuildNodes(f):
    """
    Track nodes created during a function, and store them
    """
    def wrappedF(self, *args, **kwargs):
        tracker = NT.NodeTracker()
        tracker.startTrack()
        result = f(self, *args, **kwargs)
        tracker.endTrack()
        self._nodes = tracker.getObjects(asPyNodes=True)
        return result

    wrappedF.__name__ = f.__name__
    wrappedF.__doc__ = str(f.__doc__) + "\n[Using BuiltStateCheck decorator]"
    wrappedF.__dict__.update(f.__dict__)

    return wrappedF

class RestoreSelection(object):
    '''
    Restore the selection after running
    '''
    def __init__(self):
        pass

    def __call__(self, func):
        """
        Convert *args to shapes
        """
        def new(*args, **kwargs):
            sel = pm.ls(sl=True)
            result = func(*args, **kwargs)
            pm.select(sel)
            return result

        doc = "<Using RestoreSelection>\n"
        doc += str(func.__doc__)

        new.__doc__ = doc
        new.__name__ = func.__name__
        new.__dict__.update(func.__dict__)

        return new

class TransformsToShapes(object):
    """
    Convert PyNode transform arguments to a function into shape nodes
    """

    def __init__(self, func):
        self._func = func

        doc = "<Using XfToShapes>\n<Warning: this modifies number and type of args>\n"
        doc += self._func.__doc__

        self.__doc__ = doc
        self.__name__ = func.__name__

    def __call__(self, *args, **kwargs):
        """
        Convert *args to shapes
        """
        newArgs = []
        for arg in args:
            newArgs.extend(arg.listRelatives(children=True, shapes=True))

        return self._func(newArgs, **kwargs)

class KeepShape(object):
    '''
    A context manager that will temporarily unparent shape nodes
    '''
    def __init__(self, xformNodeList):
        '''
        temporarily unparent shape nodes
        '''
        self._nDict = {}
        self._tmpGrp = pm.group(name='tmp_shapeholder', em=1, w=1)
        for node in xformNodeList:
            self._nDict[node] = pm.listRelatives(node, type='geometryShape', s=1)

        def __enter__(self):
            for node, shapeList in self._nDict.items():
                for shape in shapeList:
                    pm.parent(shape, self._tmpGrp, s=1)
