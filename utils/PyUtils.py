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

def isSiblingInstance(obj1, obj2, stringsAreEqual=True):
    """
    Is object 1's class the same as object2's class?
    @param stringsAreEqual: str == unicode == basestring
    @param 
    """
    cls1 = obj1.__class__
    cls2 = obj2.__class__
    if stringsAreEqual:
        if issubclass(cls1, basestring):
            cls1 = basestring
        if issubclass(cls2, basestring):
            cls2 = basestring
        
    return cls1 == cls2

#json utils
def decodeList(lst):
    newlist = []
    for i in lst:
        if isinstance(i, unicode):
            i = i.encode('utf-8')
        elif isinstance(i, list):
            i = _decode_list(i)
        newlist.append(i)
    return newlist

def decodeDict(dct):
    newdict = {}
    for k, v in dct.iteritems():
        if isinstance(k, unicode):
            k = k.encode('utf-8')
        if isinstance(v, unicode):
             v = v.encode('utf-8')
        elif isinstance(v, list):
            v = decodeList(v)
        newdict[k] = v
    return newdict
