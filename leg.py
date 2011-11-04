'''
Try a different approach.
'''
import logging, re, copy

import pymel.core as pm
import throttle.control as control
import throttle.utils as utils

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class Diff(object):
    '''
    A difference from a default layout
    '''
    def __init__(self):
        self.__tweakData = {}
        
    def apply(self, layout):
        """
        Apply this tweak to a layout
        """
        #if it can't be applied, just warn

class ControlXformDiff(Diff):
    '''
    Apply transform tweaks
    '''
    def __init__(self):
        pass
        
        
class Namer(object):
    '''
    Store name information, and help name nodes.    
    Nodes are named based on a token pattern.  Nodes should always be named via
    this namer, so that it can be replaced with a different namer if a different
    pattern is desired
    '''
    tokenSymbols = {'c': 'character',
                       'n': 'characterNum',
                       'r': 'resolution',
                       's': 'side',
                       'p': 'part',
                       'd': 'description',
                       'x': 'suffix',
                    'e': 'extras'}

    def __init__(self, characterName):
        self.__namedTokens = {'character': characterName,
                              'characterNum': '',
                              'resolution': '',
                              'side': '',
                              'part': '',
                              'description': '',
                              'extras': '',
                              'suffix': ''}
        
        self._pattern = "$c$n_$r_$s_$p_$d_$e_$x"
    
    def _fullToken(self, token):
        if token in self.tokenSymbols.values():
            return token
        elif token in self.tokenSymbols.keys():
            return self.tokenSymbols[token]
        else:
            raise Exception("Invalid token '%s'" % token)
        
    def _shortToken(self, token):
        if token in self.tokenSymbols.keys():
            return token
        elif token in self.tokenSymbols.values():
            for k, v in self.tokenSymbols.items():
                if self.tokenSymbols[k] == token:
                    return k
        else:
            raise Exception("Invalid token '%s'" % token)
        
    def setToken(self, token, name):
        key = self._fullToken(token)
        if key == 'side':
            if name not in ['lf', 'rt', 'cn']:
                raise Exception ("invalid side '%s'" % name)
        self.__namedTokens[key] = name
        
    def getToken(self, token):
        fullToken = self._fullToken(token)
        return self.__namedTokens[fullToken]
    
    def name(self, **kwargs):
        nameParts = copy.copy(self.__namedTokens)
        for tok, val in kwargs.items():
            fullTok = self._fullToken(tok)
            nameParts[fullTok] = val
        name = self._pattern
        for shortTok, longTok in self.tokenSymbols.items():
            name = re.sub('\$%s' % shortTok, nameParts[longTok], name)
        name = '_'.join([tok for tok in name.split('_') if tok])
        return name
        
class BuildCheck(object):
    """
    warn and gracefully exit if the object is not in the
    right state to use the decorated method
    """
    def __init__(self, *acceptableStates, **kwargs):
        self.__raiseException = kwargs.get('raiseException', False)
        self.__acceptableStates = acceptableStates
        
    def __call__(self, method):
        """
        Decorate the method, checking that it's in an acceptable state
        """
        def new(thisObj, *args, **kwargs):
            if thisObj.state()not in self.__acceptableStates:
                msg = "Not in one of these states: %s" \
                    % ", ".join(self.__acceptableStates)
                if self.__raiseException:
                    raise utils.ThrottleError(msg)
                else:
                    _logger.warning(msg)
                    return
            else:
                return method(thisObj, *args, **kwargs)
        new.__name__  = method.__name__
        new.__doc__   = method.__doc__
        new.__dict__.update(method.__dict__)
        return new

class LegLayout(object):
    
    def __init__(self):
        self.__namer = Namer('leg')
        self.__tweaks = []
        self.__nodes = []
        
    @BuildCheck('built')
    def duplicateJoints(self, newPrefix):
        """
        Duplicate the bind joints.
        """
        
    def state(self):
        """
        Return built or unbuilt
        """
        return "unbuilt"
    
    @BuildCheck('unbuilt')
    def build(self):
        """
        build the layout
        """
        legJoints = {}
        toks = ['hip', 'knee', 'ankle', 'ball', 'toe', 'toeTip']
        pm.select(cl=1)
        legJoints['hip'] = pm.joint(p =[0, 5, 0])
        legJoints['knee'] = pm.joint(p =[0, 3.5, 1])
        legJoints['ankle'] = pm.joint(p =[0, 1, 0])
        legJoints['ball'] = pm.joint(p =[0, 0, 0.5])
        legJoints['toe'] = pm.joint(p =[0, 0, 1])
        legJoints['toeTip'] = pm.joint(p =[0, 0, 1.5])
        for tok in toks:
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])            
        
        
    @BuildCheck('built')
    def delete(self):
        """
        Delete the layout
        """
    
    @BuildCheck('built')
    def cacheTweaks(self):
        """
        Store tweaks internally
        """
        
    def getTweaks(self, cached=False):
        """
        get the object's tweaks, if built
        @param cached=False: return tweaks cached in memory
        """
        pass
    
    @BuildCheck('built')
    def applyTweaks(self, tweaks):
        """
        Apply tweaks
        """
        pass

class LegRig(object):
    def __init__(self, layout):
        self.__layout = layout
        
    def build(self, charName, side='cn'):
        """
        Build the rig, using the information in the layout
        """
        pass
    
    def _getTopFkChildren(self):
        """
        Get the nodes that should be directly parented under another rig's node
        """
        pass
    
    def _getTopIkChildren(self):
        """
        Get the nodes that should be parented under the character's 'master' control
        """
        pass
    
    def _getDNTNodes(self):
        """
        Get the nodes that should be parented under the DNT
        """
    def parentTo(self, otherRig, node):
        """
        parent this rig to otherRig under node
        """
        pass
