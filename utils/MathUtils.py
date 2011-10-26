"""
Various functions, classes, etc supporing vector and matrix math used
in rigging
"""
import math, copy
import pymel.core as pm
import maya.OpenMaya as OM
import PyUtils
reload(PyUtils)

class _VecCheck(object):
    """
    Dectorator for enforcing equal vector arg dimensions
    """
    def __call__(self, f):

        def new(*vectors):

            forceLen = len(vectors[0])
            for v in vectors:
                if len(v) != forceLen:
                    raise Exception("Vector dimensions must be equal")

            print vectors
            return f(*vectors)

        docMsg = '\n<Using Vector Check dectorator>'
        new.__name__ = f.__name__
        new.__doc__ = f.__doc__ and f.__doc__ + docMsg or docMsg[2:]
        new.__dict__.update(f.__dict__)

        return new

@_VecCheck()
def dot(v1, v2):
    """
    Return the dot product of two vectors
    """
    dot = 0
    for i in range(len(v1)):
        dot += v1[i] * v2[i]
    return dot

def mag(v):
    """
    Return the magnitude of vector v
    """
    s = 0
    for i in range(len(v)):
        s += v[i] ** 2

    return math.sqrt(s)

@_VecCheck()
def projectedVector(hVec, nVec):
    """
    Given a hypotenuse vector and another arbitrary vector, compute the
    projected vector parallel to nVec (pVec) and the perpendicular vector
    opposite nVec (oVec) such that:
    pVec + oVec == hVec
    @param hVec: a hypotenuse vector
    @type hVec: list

    @param nVec: an arbirary vector to projected
    @type nVec: list

    @return: (pVec, oVec)
    @type pVec: list
    @type oVec: list
    """

    #projected vector == nVec((nVec dot hVec)/mag(nVec)^2)

    mult = dot(nVec, hVec) / (mag(nVec) ** 2)
    pVec = []
    for i in nVec:
        pVec.append(i * mult)

    #pVec + oVec = hVec; oVec = hVec -pVec
    oVec = []
    for i in range(len(hVec)):
        oVec.append(hVec[i] - pVec[i])

    return (pVec, oVec)

def toList(m):
    '''
    Convert a PyMEL Matrix or [4][4] list into a flat 16-element list
    '''

    if isinstance(m, pm.datatypes.Matrix):
        m = [m.a00, m.a01, m.a02, m.a03,
                m.a10, m.a11, m.a12, m.a13,
                m.a20, m.a21, m.a22, m.a23,
                m.a30, m.a31, m.a32, m.a33]
    elif PyUtils.isIterable(m[0]):
        m = [m[0][0], m[0][1], m[0][2], m[0][3],
                m[1][0], m[1][1], m[1][2], m[1][3],
                m[2][0], m[2][1], m[2][2], m[2][3],
                m[3][0], m[3][1], m[3][2], m[3][3]]
    return m

def to4x4(l):
    '''
    Convert a PyMEL Matrix or flat list into a 4x4 element list
    '''
    if isinstance(l, pm.datatypes.Matrix):
        l = toList(l)

    elif PyUtils.isIterable(l[0]):
        l = [l[0][0], l[0][1], l[0][2], l[0][3],
            l[1][0], l[1][1], l[1][2], l[1][3],
            l[2][0], l[2][1], l[2][2], l[2][3],
            l[3][0], l[3][1], l[3][2], l[3][3]]

    return [[l[0], l[1], l[2], l[3]],
            [l[4], l[5], l[6], l[7]],
            [l[8], l[9], l[10], l[11]],
            [l[12], l[13], l[14], l[15]]]

def mMatrixToList(mMatrix):
    result = []
    m = mMatrix.matrix
    for r in range(4):
        for c in range(4):
            result.append(OM.MScriptUtil.getDouble4ArrayItem(m, r, c))
    return result

class Matrix4x4(object):
    '''
    The PyMEL matrix class seems to have a couple bugs
    '''
    def __init__(self, matrix):
        """
        Matrix can be a pymel matrix, a list of floats, or a list of float lists
        """

        if isinstance(matrix, OM.MMatrix) and not isinstance(matrix, pm.datatypes.Matrix):
            matrix = mMatrixToList(matrix)

        self._matrix = to4x4(matrix)
        self._mMatrix = OM.MMatrix()
        OM.MScriptUtil.createMatrixFromList(toList(matrix), self._mMatrix)

    def flatList(self):
        return toList(self._matrix)

    def matrix(self):
        return copy.copy(self._matrix)
    def mmatrix(self):
        return self._mMatrix

    def inverse(self):
        return Matrix4x4(self._mMatrix.inverse())

    def __mul__(self, other):
        if not isinstance(other, Matrix4x4):
            other = Matrix4x4(other)
        return Matrix4x4(self._mMatrix * other._mMatrix)

    def __str__(self):
        return self.flatList()




#test:
if __name__ == "__main__":
    print "Dot of opposite vectors: %.2f" % dot([1, 0, 0], [-1, 0, 0])
    print "Mag of <5,5,5>: %.2f" % float(mag([5, 5, 5]))
    print projectedVector([5, 5, 5], [2, 0, 0])


