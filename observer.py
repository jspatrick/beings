class Event(object):
    def __init__(self, eventType):
        self.eventType = eventType

class Observable(object):
    def __init__(self):
        self.__callbacks = []

    def subscribe(self, eventType, callback):
        self.__callbacks.append((eventType, callback))

    def notify(self, eventType, **kwargs):
        event = Event(eventType)
        for k, v in kwargs.items():
            setattr(event, k, v)
            
        for subscribedEvent, callback in self.__callbacks:
            if eventType == subscribedEvent:
                callback(event)
