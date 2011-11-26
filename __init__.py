"""
Beings - rig any kind of being!  Human beings! Amphibious beings! Mechanical beings!
"""

import logging
logging.basicConfig()

class BeingsFilter(logging.Filter):
    def __init__(self, name=''):
        logging.Filter.__init__(self, name=name)
    def filter(self, record):
        '''Add contextual info'''
        msg = '[function: %s: line: %i] : %s' % (record.funcName, record.lineno, record.msg)
        record.msg= msg
        return True

_beingsRootLogger = logging.getLogger('beings')
for fltr in _beingsRootLogger.filters:
    _beingsRootLogger.removeFilter(fltr)
_beingsRootLogger.addFilter(BeingsFilter())
