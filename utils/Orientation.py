'''
Created on Jan 30, 2011

@author: john
'''
import logging, copy, math, cPickle

import maya.OpenMaya as OM
import pymel.core as pm

import PyUtils, MathUtils
logger = logging.getLogger(__name__)

ATTTR_MAP = {'translateX': ['translateX', 'tx'],
                  'translateY': ['translateY', 'ty'],
                  'translateZ': ['translateZ', 'tz'],
                  'rotateX': ['rotateX', 'rx'],
                  'rotateY': ['rotateY', 'ry'],
                  'rotateZ': ['rotateZ', 'rz'],
                  'scaleX': ['scaleX', 'sx'],
                  'scaleY': ['scaleY', 'sy'],
                  'scaleZ': ['scaleZ', 'sz']}

def mRotOrder(orientationObj):
    """
    Get the rotation order of the MEulerAngle class
    """
    ro = 'k%s' % orientationObj.rotOrder(asString=True, default=True).swapcase()
    return getattr(OM.MEulerRotation, ro)

def indexFromVector(vector):
    """
    If the vector represents an axis where only one value isn't zero,
    return the index of the non-zero axis
    """
    index=None
    for i in range(len(vector)):
        if vector[i]:
            if index:
                logger.warning("Multiple non-zero indices found; returning the first")
            else:
                index=i
    return index

class OrientationError(): pass
class Orientation(object):
    """
    This class stores and manages orientation information.  It is intended for
    use in layout, orientation, and re-orientation of nodes.
    """
    _axisVecDict = {"posX": [1, 0, 0],
                    "posY": [0, 1, 0],
                    "posZ": [0, 0, 1],
                    'negX': [-1, 0, 0],
                    'negY': [0, -1, 0],
                    'negZ': [0, 0, -1]}


    _defaultAxes = {'aim': ('posY', [0, 1, 0]),
                     'up': ('posX', [1, 0, 1]),
                     'weak': ('posZ', [0, 0, 1])}

    _rotOrderDict = {'xyz': 0,
                      'yzx': 1,
                      'zxy': 2,
                      'xzy': 3,
                      'yxz': 4,
                      'zyx': 5}

    _defaultRotOrder = ['up', 'aim', 'weak']

    #(aim, up) -> weak
    #there's a pattern here, but for now...
    _weakAxisDict = {('posX', 'posY'): 'posZ',
                      ('posX', 'negY'): 'negZ',
                      ('negX', 'posY'): 'negZ',
                      ('negX', 'negY'): 'posZ',

                      ('posX', 'posZ'): 'negY',
                      ('negX', 'negZ'): 'negY',
                      ('posX', 'negZ'): 'posY',
                      ('negX', 'posZ'): 'negY',

                      ('posY', 'posX'): 'negZ',
                      ('posY', 'negX'): 'posZ',
                      ('negY', 'posX'): 'posZ',
                      ('negY', 'negX'): 'negZ',

                      ('posY', 'posZ'): 'posX',
                      ('posY', 'negZ'): 'negX',
                      ('negY', 'posZ'): 'negX',
                      ('negY', 'negZ'): 'posX',

                      ('posZ', 'posX'): 'posY',
                      ('posZ', 'negX'): 'negY',
                      ('negZ', 'posX'): 'negY',
                      ('negZ', 'negX'): 'posY',

                      ('posZ', 'posY'): 'negX',
                      ('posZ', 'negY'): 'posX',
                      ('negZ', 'posY'): 'posX',
                      ('negZ', 'negY'): 'negX' }

    def __init__(self):
        """
        Initialize the Orient with default settings
        
        Layout objects are always constructed with the default settings.  Rig
        objects can then provide a different set of orientations and build the
        same rig with the new orients.  
        """

        self._orientAimAxis = "posY"
        self._orientUpAxis = "posX"
        self._orientWeakAxis = "posZ"
        self._rotOrder = 'xyz'
        self._aimFlipped = False

    @classmethod
    def defaultOrientation(cls):
        return cls()

    @classmethod
    def objFromData(cls, d):
        #import Orientation
        return cPickle.loads(d)

    def data(self):
        return cPickle.dumps(self)

    def isAimFlipped(self):
        """
        Has the orientation's aim axis been temporarily flipped from positive to negative? (or visa versa)
        This occurs during joint orient mirroring from left to right.  
        """
        return self._aimFlipped

    def flipAim(self):
        """
        Flip the aim axis, and track the flip state
        """
        if not self._aimFlipped:
            axis = self.getAxis('aim', asString=True)
            if axis[:-1] == 'pos':
                rev = 'neg'
            else:
                rev = 'pos'

            self.setAxis('aim', "%s%s" % (rev, axis[-1]))
            self._aimFlipped = True

        else:
            logger.info("Aim is already flippped")

    def unflipAim(self):
        if self._aimFlipped:
            axis = self.getAxis('aim', asString=True)
            if axis[:-1] == 'pos':
                rev = 'neg'
            else:
                rev = 'pos'

            self.setAxis('aim', "%s%s" % (rev, axis[-1]), force=True)
            self._aimFlipped = False
        else:
            logger.info('Skipping unflip: Aim is not flipped')

    def getAttr(self, xformNode, axis, type='translate'):
        axis = self.getAxis(axis, asString=True)[3]
        return getattr(xformNode, '%s%s' % (type, axis))
    
    def rotOrder(self, asString=False, default=False):
        if default:
            if asString:
                return self._rotOrder
            else:
                return self._rotOrderDict[self._rotOrder]
        else:
            return self._newRotOrder(asString=asString)

    def setRotOrder(self, rotOrder):
        '''
        Set the rotation order.  rotOrder can be an int or string
        '''
        if type(rotOrder) == type(0):
            self._rotOrder = [key for key, value in dict.items() if value == rotOrder][0]
        elif type(rotOrder) == type(""):
            self._rotOrder = rotOrder
        else:
            raise RIError("invalid type (%s)" % str(type(rotOrder)))

        return self

    def getAxisDefault(self, axis, asString=True):
        if not asString:
            return self._defaultAxes[axis.lower()][1]
        else:
            return self._defaultAxes[axis.lower()][0]


    def _setOrientAxis(self, axis, setting):
        """
        Set the aimAxis, upAxis and weakAxis.
        @param axis: one of 'aim', 'up', or 'weak'
        @param setting: 'posY', 'negZ', etc
        @return: a list of [__aimAxis, __upAxis, __weakAxis]
        """
        axisSettings = self._axisVecDict.keys()
        axes = ["aim", "up", "weak"]

        #todo:  make this less redundant
        if setting not in axisSettings:
            raise RIError("%s is not a valid setting\n.  Valid Settings:%s" % ', '.join(axisSettings))
        if axis == 'aim':
            self._orientAimAxis = setting
            otherAxes = {'weak': self._orientWeakAxis, 'up': self._orientUpAxis}
        elif axis == 'up':
            self._orientUpAxis = setting
            otherAxes = {'weak': self._orientWeakAxis, 'aim': self._orientAimAxis}
#        elif axis == 'weak':
#            self._orientWeakAxis = setting
#            otherAxes = {'aim': self._orientAimAxis, 'up': self._orientUpAxis}
        else:
            raise RIError("%s is not a valid axis.\nValid Axes:%s" % (axis, ',  '.join(axes)))
        #set the axis passed 
        axis = setting

        currentAxes = [axis[-1] for axis in [self._orientAimAxis, self._orientUpAxis, self._orientWeakAxis]]

        for axis in ["X", "Y", "Z"]:
            if axis not in currentAxes:
                missingAxis = axis
                break

        #find out if there is a current axis that is using the pos or negative version of this setting
        result = []
        for otherAxis, otherSetting in otherAxes.items():
            if setting[-1] == otherSetting[-1]:
                setattr(self, "_orient%sAxis" % otherAxis.capitalize(),
                        "%s%s" % (otherSetting[:-1], missingAxis))
                attr = getattr(self, "_orient%sAxis" % otherAxis.capitalize())
                result = [otherAxis, attr]

        return result

    def _vectorFromAxis(self, axis):
        """
        Get a vector from a string axis settting
        @param axis: 'aim', 'up', or 'weak'
        @return: 3-element list
        """
        if axis == 'aim':
            axis = self._orientAimAxis
        elif axis == 'up':
            axis = self._orientUpAxis
        elif axis == 'weak':
            axis = self._orientWeakAxis
        else:
            raise RIError("%s is not a valid axis.\nValid Axes:%s" % (axis, ',  '.join(self._axisVecDict.keys())))

        return self._axisVecDict[axis]

    def _validateAxisSetting(self, setting):
        """
        Validate that the setting is an appropriate string or list.  Raise
        an exception if not approptiate.
        @return: 'str' or 'vec'
        """
        if type(setting) == type(""):
            if setting not in self._axisVecDict.keys():
                msg = "%s is not a valid string axis setting." % setting
                msg += "Valid settings are:\n%s" % ", ".join(self._axisVecDict.keys())
                raise RIError(msg)
            return 'str'
        elif type(setting) == type([]) or type(setting) == type(()):
            if setting not in self._axisVecDict.values():
                msg = "%s is not a valid vector setting." % str(setting)
                msg += " Valid settings are:\n%s" % "; ".join([str(x) for x in self._axisVecDict.values()])
                raise RIError(msg)
            return 'vec'

        else:
            raise RIError("Can't use a %s to set axis.  Provide string or vector" % str(type(setting)))

    def getAxis(self, axis, asString=False):
        """
        Return the axis being used for the aim, up, or weak axis.  
        @param axis: the axis to get, ie 'aim'
        @param asString=False: Return the axis as a vector, ie [0,1,0]; else, return string, ie 'posY'
        @return: string ('posY') or vector ([0,1,0])
        """
        if not asString:
            return copy.copy(self._vectorFromAxis(axis.lower()))
        return copy.copy(getattr(self, '_orient%sAxis' % axis.capitalize()))

    def _correctWeak(self):
        """
        Correct the weak axis so the coordinate system doesn't flip
        """
        self._orientWeakAxis = self._weakAxisDict[(self._orientUpAxis, self._orientAimAxis)]

    def setAxis(self, axis, setting, force=False):
        """
        Set an axis. Setting can be a string or a 3-element list.
        Don't directly set the weak axis - it will always be forced into an orientation to keep
        the coordinates from ending up mirrored
        """
        if self._aimFlipped and not force:
            raise OrientationError("Cannot set axes while aim flipped")
        if axis == 'weak':
            raise RIError("Can't directly set the weak axis")

        settingType = self._validateAxisSetting(setting)
        if settingType == "str":
            self._setOrientAxis(axis.lower(), setting)

        elif settingType == "vec":
            for k, v in self._axisVecDict.items():
                if setting == v:
                    self._setOrientAxis(axis.lower(), k)

        self._correctWeak()
        return self

    def defaultRotOrder(self):
        """
        Get the default rotation order
        """
        return self._defaultRotOrder


    def _newRotOrder(self, asString=False, origOrient=None):
        """
        If we've re-oriented the joint, we also need to change the rotation order
        to match relative to the new axes.  For instance, if the first rotate axis
        was 'Y', the joint's first rotation was along its aim axis.  We want to preserve
        rotation order in terms of axes.
        """
        if not origOrient:
            origOrient = self.defaultOrientation()

        origRotOrder = origOrient.rotOrder(asString=True, default=True)
        #get the orig rot order in terms of axes
        origROMap = {'aim': None, 'up': None, 'weak': None}
        for vec in origROMap.keys():
            pos = origRotOrder.find(origOrient.getAxis(vec, asString=True)[-1].lower())
            origROMap[vec] = pos

        newOrient = [None, None, None]
        for k, v in origROMap.items():
            newOrient[v] = self.getAxis(k, asString=True)[-1].lower()


        newOrient = "".join(newOrient)
        if asString:
            return newOrient
        else:
            return self._rotOrderDict[newOrient]


    def newOrientSpaceVector(self, vector, origOrient=None):
        """
        Given an original vector, return the vector for an object in current Orientation space.
        If our axes are at their defaults, this will be the same as the arg.
        
        @param vector: a 3-element list, ie [1, 5, 3.2]
        @param origOrient=None: The original orientation the vector was in.  Uses default orientation by default
        """
        if not origOrient:
            origOrient = self.defaultOrientation()
        assert isinstance(origOrient, Orientation)

        result = [None, None, None]
        axes = ['up', 'aim', 'weak']
        for axis in axes:
            #get the position of the axis in the original list
            origAxisVec = origOrient.getAxis(axis)
            origListPos = None
            origMult = 1
            for i, n in enumerate(origAxisVec):
                if n:
                    origListPos = i
                    if n < 0:
                        #was the axis negative?
                        origMult = -1
                    break

            #get the position in the new list
            newAxisVec = self.getAxis(axis)
            newListPos = None
            newMult = 1
            for i, n in enumerate(newAxisVec):
                if n:
                    newListPos = i
                    if n < 0:
                        #is the new axis negative?
                        newMult = -1
                    break
            result[newListPos] = vector[origListPos] * origMult * newMult

        #if this is the right side, all values should be inverted to get mirrored vectors 
#        if useSide and self._side == 'rt':
#            result = [result[0] * -1, result[1] * -1, result[2] * -1]

        return result

    def newAngle(self, origAngles, origOrient=None, origRotOrder=0, useNewRotOrder=False):
        """
        Given an original set of Euler angles, return the angles for the current Orientation and rotation order
        If our axes are at their defaults, this will be the same as the arg.
        
        @param origAngles: a 3-element list, ie [90, 25, 40.2]
        @param origOrient=None: The original orientation the vector was in.  Uses default orientation by default
        """
        # just get the new vector and adjust for rotation order
        if not origOrient:
            origOrient = self.defaultOrientation()

        startMatrix = MathUtils.Matrix4x4([origOrient.getAxis('up') + [0],
                                    origOrient.getAxis('aim') + [0],
                                    origOrient.getAxis('weak') + [0],
                                    [0, 0, 0, 1]])

        endMatrix = MathUtils.Matrix4x4([self.getAxis('up') + [0],
                                  self.getAxis('aim') + [0],
                                  self.getAxis('weak') + [0],
                                  [0, 0, 0, 1]])

        multMatrix = endMatrix * startMatrix.inverse()

        er = OM.MEulerRotation(math.radians(origAngles[0]),
                               math.radians(origAngles[1]),
                               math.radians(origAngles[2]),
                               origRotOrder)

        finalM = multMatrix.mmatrix() * er.asMatrix()
        newEr = OM.MTransformationMatrix(finalM).eulerRotation()
        if useNewRotOrder:
            newEr = newEr.reorder(self.rotOrder())
        newAngles = [math.degrees(newEr.x), math.degrees(newEr.y), math.degrees(newEr.z)]
        return newAngles


    def rotateToSpace(self, obj, origOrient=None):
        '''
        Rotate an object to match the current space.  Eg, if the original object
        matches world axes but this object's orientation is different, rotate
        it to match the new space 
        #don't mirror these values in the case of orientation
        return self.getNewVector(newAngles, origOrient=origOrient)
        '''
        angle = obj.r.get()
        obj.r.set(self.newAngle(angle, origOrient=origOrient))

    def reorientJoints(self, joints, origOrient=None):
        '''
        Change the relative orientation joints
        '''
        for j in joints:
            jo = j.jointOrient.get()
            newAngle = self.newAngle(jo, origOrient=origOrient)
            children = j.listRelatives()
            for child in children:
                child.setParent(w=1)
            j.jointOrient.set(newAngle)
            for child in children:
                child.setParent(j)

##NOTE:  Not implemented.
#class OrientationWrapper(object):
#    def __init__(self, orientation, pyNode):
#        """
#        Store a reference to an orientation object that has been set up
#        with the joint's new orientation.  Intercept translation and matrix
#        methods and transform them to act as if the object were in its default
#        orientation
#        """
#        assert isinstance(orientation, Orientation)
#        self._orient = orientation
#        self._pyNode = pyNode
#
#    def __getattr__(self):
#        pass
#
#    def _absoluteTranslate(self, vector, space='local'):
#        pass
#
#    def _relativeTranslate(self, vector, space='local'):
#        pass
#
#    def _getTranslate(self, space='local'):
#        pass
#
#    def _absoluteScale(self, vector):
#        pass
#
#    def _getScale(self):
#        pass
#
#    def _absoluteRotate(self, vector, space='local'):
#        pass
#
#    def _relativeRotate(self, vector, space='local'):
#        pass
#
#    def _getRotate(self, space='local'):
#        pass

