from supervisely.app import StateJson, DataJson

from .handlers import *
from .functions import *
from .widgets import *


StateJson()['selectClassVisible'] = False
StateJson()['outputClassName'] = None
StateJson()['selectedObjectId'] = None
StateJson()['updatingClass'] = False

StateJson()['queueMode'] = 'objects'

StateJson()['anotherObjectLoading'] = False
StateJson()['markingObjectLoading'] = False

DataJson()['objectsLeftTotal'] = 0
DataJson()['objectsLeftQueue'] = 0
DataJson()['figuresLeftQueue'] = 0

