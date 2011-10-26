'''
API Utils
'''
import maya.OpenMaya as OM
import pymel.core as PM

def getShadingGroupMembership():
    '''
    Get a dictionary of shading group set information
    {'shadingGroup': [assignmnet1, assignment2...]}
    '''
    result = {}
    sgs = PM.ls(type='shadingEngine')
    for sg in sgs:
        result[sg.name()] = sg.members(flatten=True)
    return result
        

def strToObj(strObj, handle=False, dagPath=False):
    '''
    convert a string rep of an object into an MObject
    @param handle=False: return an MObjectHandle
    @param dagPath=False: return and MDagPath
    '''
    if isinstance(strObj, PM.PyNode):
        strObj = strObj.name()
    sl = OM.MSelectionList()
    sl.add(strObj)
    
    if dagPath:
        obj = OM.MDagPath()
        sl.getDagPath(0, obj)
    else:
        obj = OM.MObject()
        sl.getDependNode(0, obj)
    
    if handle and not dagPath:
        obj = OM.MObjectHandle(obj)
    return obj


def getMFn(node):
    '''
    convert an MObject, MDagPath, string, or PyNode to an MFn obj
    '''
    try:
        n = PM.PyNode(node)
        return n.__apimfn__()
    except:
        if isinstance(node, OM.MDagPath):
            name = node.fullPathName()
        else:
            nodeFn = OM.MFnDependencyNode(node)
            name = nodeFn.name()
        return PM.PyNode(name).__apimfn__()

