"""
Beings - rig any kind of being!  Human beings! Amphibious beings! Mechanical beings!
"""

import logging, os, re, sys, __builtin__
logging.basicConfig()

__DEVMODE=True

class BeingsFilter(logging.Filter):
    def __init__(self, name=''):
        logging.Filter.__init__(self, name=name)
    def filter(self, record):
        '''Add contextual info'''
        msg = '[function: %s: line: %i] : %s' % (record.funcName, record.lineno, record.msg)
        record.msg= msg
        return True
    
_beingsRootLogger = logging.getLogger('beings')
if _beingsRootLogger.getEffectiveLevel() == 0:
    _beingsRootLogger.setLevel(logging.INFO)
    
for fltr in _beingsRootLogger.filters:
    _beingsRootLogger.removeFilter(fltr)    
if __DEVMODE:
    _beingsRootLogger.addFilter(BeingsFilter())


def importAllWidgets(reloadThem=False):
    rootDir = os.path.dirname(sys.modules[__name__].__file__)
    widgetsDir = os.path.join(rootDir, 'widgets')
    _beingsRootLogger.info("Loading widgets from %s" %  widgetsDir)
    modules = []
    for base in os.listdir(widgetsDir):
        path = os.path.join(widgetsDir, base)
        match = re.match(r'^([a-zA-Z0-9]+)\.py$', base)
        if match and os.path.isfile(path):
            name = match.groups()[0]
            modules.append('beings.widgets.%s' % name)
    for module in modules:
        if reloadThem:
            moduleObj = sys.modules.get(module, None)
            if moduleObj:
                _beingsRootLogger.info('Auto reloading %s' % module)
                reload(sys.modules[module])
                
        __builtin__.__import__(module)
    return modules


