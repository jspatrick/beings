'''
Python Utilities
'''
import sys, inspect, json

def isIterable(obj, strings=False):
    '''
    Is the object iterable?
    '''
    if isinstance(obj, basestring) and strings == False:
        return False

    if hasattr(obj, '__iter__'):
        return True
    return False

def getSubclasses(module, cls, exclude=[]):
    """
    Return a list of subclasses of cls
    """
    allClasses = inspect.getmembers(sys.modules[module], inspect.isclass)
    allClasses = [(x, c) for x, c in allClasses if issubclass(c, cls) and c != cls and c not in exclude]
    result = {}
    for x, c in allClasses:
        result[x] = c
    return result

def isIter(arg, string=False):
    '''
    Is the arg iterable?
    string=False(bool):  consider string an iterable item
    '''

    if isinstance(arg, basestring):
        if string:
            return True
        return False
    if hasattr(arg, '__iter__'):
        return True
    return False

#json utils
def _decode_list(lst):
    newlist = []
    for i in lst:
        if isinstance(i, unicode):
            i = i.encode('utf-8')
        elif isinstance(i, list):
            i = _decode_list(i)
        newlist.append(i)
    return newlist

def _decode_dict(dct):
    newdict = {}
    for k, v in dct.iteritems():
        if isinstance(k, unicode):
            k = k.encode('utf-8')
        if isinstance(v, unicode):
             v = v.encode('utf-8')
        elif isinstance(v, list):
            v = _decode_list(v)
        newdict[k] = v
    return newdict
