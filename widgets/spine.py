import logging
import maya.cmds as MC
import pymel.core as PM

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

def arclenOfJoints(jnts, inclusive=True):
    pass

def distanceOfJoints(jnts):
    pass

def epCurveFromJnts(jnts):
    pass


def cvCurveFromNodes(nodes, name='crv'):
    cmd = ['curve -d 2 -k 0 -name "%s"' % name]

    for i in range(len(nodes)-1):
        cmd.append('-k %i' % i)
        
    cmd.append('-k %i' % (len(nodes)-2))
    
    for node in nodes:
        p = MC.xform(node, q=1, ws=1, rp=1)
        cmd.append('-p %f %f %f' % (p[0], p[1], p[2]))
        
    cmd = ' '.join(cmd)
    _logger.debug(cmd)
    MM.eval(cmd)


def surfaceFromJnts(jnts):
    pass

def createJntAttrs(jnt):
    pass
    #uniformStretchParam
    #stretchParam
    #noStretchParam

def createSurfaceJnts(ikJnts):
    pass


def closestPointOnSurface(node, surface, attr='closestPoint'):
    """
    Create a closest point on surface node.  Create an attr on the
    joint that the closestPoint is wired to
    """
    pass

def createIkSpineSystem(jnts, ctls):
    ikSpineNode = PM.createNode('transform', n='ikSpineNode')
    ikSpineNode.addAttr('uniformStretch', k=1, dv=0, min=0, max=1)
    ikSpineNode.addAttr('stretchAmt', k=1, dv=1, min=0, max=1)
    for i, jnt in enumerate(jnts):
        ikSpineNode.addAttr('spinePos%i' % i)
        ikSpineNode.addAttr('spineRot%i' % i)
        ikSpineNode.addAttr('spineScl%i' % i)
        
    
if __name__  == "__main__":
    print "hello world"
    bndjnts = ['bnd_a', 'bnd_b', 'bnd_c', 'bnd_d', 'bnd_e']
    ctls = ['ctl_a', 'ctl_b', 'ctl_c', 'ctl_d']
    
    cvCurveFromNodes(ctls)
