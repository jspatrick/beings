import logging, re, copy, os, sys, __builtin__, string
import pymel.core as pm

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

class Namer(object):
    """
    Store name information, and help name nodes.
    Nodes are named based on a token pattern.  Nodes should always be named via
    this namer, so that it can be replaced with a different namer if a different
    pattern is desired
    """
    tokenSymbols = {'c': 'character',
                       'r': 'resolution',
                       's': 'side',
                       'p': 'part',
                       'd': 'description'}

    _pattern = "$c_$r_$s_$p_$d"

    _patternRX = re.compile("""
    ^(?P<character>[A-Za-z]+)_
    (?P<resolution>[A-Za-z]+)?_?
    (?P<side>(lf)|(rt)|(cn))_
    (?P<part>[a-z]+)_?
    (?P<description>[a-z_]*)$""", re.VERBOSE)


    @classmethod
    def _fullToken(self, token):
        if token in self.tokenSymbols.values():
            return token
        elif token in self.tokenSymbols.keys():
            return self.tokenSymbols[token]
        else:
            raise Exception("Invalid token '%s'" % token)

    @classmethod
    def _shortToken(self, token):
        if token in self.tokenSymbols.keys():
            return token
        elif token in self.tokenSymbols.values():
            for k, v in self.tokenSymbols.items():
                if self.tokenSymbols[k] == token:
                    return k
        else:
            raise Exception("Invalid token '%s'" % token)

    @classmethod
    def getTokensFromName(cls, name):
        """Get a dictionary of tokens from a string name.
        @param name: the name
        @type name: str
        @return: dictionary of {fullToken: name}
        """
        match = cls._patternRX.match(name)
        if not match:
            raise RuntimeError("Invalid name '%s'" % match)
        groups = match.groups()

        result = {}
        for tok in cls.tokenSymbols.values():
            index = cls._patternRX.groupindex[tok] - 1
            result[tok] = groups[index] or ''

        return result


    def __init__(self, char, side, part, **toks):
        self.__namedTokens = {'character': '',
                              'characterNum': '',
                              'resolution': '',
                              'side': '',
                              'part': '',
                              'description': ''}


        self._lockedToks = []

        self.setTokens(character=char,
                       side=side,
                       part=part)
        self.lockToks('character', 'side', 'part')

        if toks:
            self.setTokens(**toks)

    def lockToks(self, *toks):
        """Do not allow overriding tokens"""
        for tok in toks:
            self._lockedToks.append(self._fullToken(tok))

    def unlockToks(self, *toks):
        for tok in toks:
            tok = self._fullToken(tok)
            try:
                index = self._lockedToks.index(tok)
                self._lockedToks.pop(index)
            except ValueError:
                _logger.debug("%s is not locked" % tok)

    def getToken(self, token):
        fullToken = self._fullToken(token)
        return self.__namedTokens[fullToken]

    def _validateTokens(self, **kwargs):
        for token, name in kwargs.items():
            name = str(name)
            if not name:
                continue

            key = self._fullToken(token)

            if key == 'side':
                if name not in ['lf', 'rt', 'cn']:
                    raise Exception ("invalid side '%s'" % name)

            if key == 'description':
                if not re.match('[a-z_]+', name):
                    raise Exception("invalid name '%s'" % name)
            elif not re.match('[a-z]+', name):
                raise Exception("invalid name '%s'" % name)

    def setTokens(self, **kwargs):
        self._validateTokens(**kwargs)
        for token, name in kwargs.items():
            name = str(name)
            self.__namedTokens[token] = name

    def name(self, *args, **kwargs):
        """Get a string name
        @param force=False:  force overrides on locked tokens
        @type force: bool
        @param alphaSuf=None: add an alphabetic suffix based on an integer index
        @type alphaSuf: int
        """
        alphaSuf = kwargs.pop('alphaSuf', None)

        #make a descrition value from args and alphaSuf
        key = 'description'
        d = kwargs.get(key, '')
        if not d:
            key='d'
            d = kwargs.get(key, '')
        dparts = []
        if args:
            dparts = list(args)
        if d:
            dparts.extend(d.split('_'))
        if alphaSuf is not None:
            dparts.append(string.ascii_lowercase[alphaSuf])

        if dparts:
            kwargs[key] = '_'.join(dparts)

        force = kwargs.pop('force', False)

        self._validateTokens(**kwargs)

        nameParts = copy.copy(self.__namedTokens)
        for tok, val in kwargs.items():
            fullTok = self._fullToken(tok)

            #check if locked
            if fullTok in self._lockedToks and not force:
                _logger.warning("Token '%s' is locked, cannot override with '%s'" \
                                % (fullTok, val))
            else:
                nameParts[fullTok] = val
        name = self._pattern
        for shortTok, longTok in self.tokenSymbols.items():
            name = re.sub('\$%s' % shortTok, nameParts[longTok], name)
        name = '_'.join([tok for tok in name.split('_') if tok])
        return name

    def __call__(self, *args, **kwargs):
        return self.name(*args, **kwargs)

    #TODO:  get prefix toks from pattern
    def stripPrefix(self, name, errorOnFailure=False, replaceWith=''):
        """Strip prefix from a name."""
        prefix = '%s%s_' % (self.getToken('c'), self.getToken('n'))
        newName = ''
        parts = name.split(prefix)
        if (parts[0] == ''):
            newName = newName.join(parts[1:])
        else:
            msg = 'Cannot strip %s from %s; parts[0] == %s' % (prefix, name, parts[0])
            if errorOnFailure:
                raise utils.BeingsError(msg)
            else:
                _logger.warning(msg)
                newName = name
        if replaceWith:
            newName = '%s_%s' % (replaceWith, newName)
        return newName

    def rename(self, node, *args, **kwargs):
        node = pm.PyNode(node)
        new = self.name(*args, **kwargs)
        node.rename(new)
        return node


def getGenericNodeName(fullNodeName):
    """
    From a control, get an 'id' that includes the resolution and description. These
    are the two pieces of a node name that aren't provided by the core namer.
    """
    assert ("^" not in fullNodeName)
    toks = Namer.getTokensFromName(fullNodeName)
    return '%s^%s' % (toks['resolution'], toks['description'])

def getFullNodeName(genericNodeName, namer=None, char=None, side=None, part=None):
    """
    Get a full node name from a generic name
    @param genericNodeName: the node name with a '^' character
    @param namer: a namer used for naming

    """
    try:
        assert ("^" in genericNodeName)
    except AssertionError:
        _logger.error("bad generic name '%r'" % genericNodeName)
        raise
    
    if not namer:
        namer = Namer(char, side, part)

    res, description = genericNodeName.split('^')
    return namer(r=res, d=description)
