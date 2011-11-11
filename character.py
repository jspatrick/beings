import logging, re, copy, weakref
import json
import pymel.core as pm
import throttle.control as control
import throttle.utils as utils
import throttle.nodetracking as nodetracking


class Character(object):
    '''
    A character tracks widgets, organizes the build, etc
    '''
    def __init__(self, charName, rigType='core'):
        self.__widgets = {}
        self.__parents = {}
        self.__charNodes = {}
        self.__rigType = 'core'
        self.namer = utils.Namer(charName)
        
    def charName(self): return self.namer.getToken('character')
    
    def addWidget(self, widget, parentName=None, parentNode=None):
        name = widget.name() 
        if name in self.__widgets.keys():
            raise utils.ThrottleError("Rig already has a widget called '%s'" % name)
        self.__widgets[name] = widget
        self.__parents[name] = (parentName, parentNode)
        
    
    def _getChildWidgets(self, parent=None):
        '''Get widgets that are children of parent.'''
        result = []
        for wdgName, parentTup in self.__parents.items():
            if parentTup[0] == parent:
                result.append(wdgName)
        return result

    def _buildMainHierarhcy(self):
        '''
        build the main group structure
        '''
        pass
