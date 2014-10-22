import time

import gevent.event

from pvrclient import *
from pvrconfig import PVRConfig


class HLSException(Exception):

    '''
    Exception from AceClient
    '''
    pass


class HLSClient(PVRClient):
    ENGINE_TYPE = 'hls'

    def __init__(self, vlc_client):
        self.engine = vlc_client
        # Shutting down flag
        self._shuttingDown = gevent.event.Event()

    def __del__(self):
        self.destroy()

    def init(self, stream_name, input_name):
        self.stream_name = stream_name
        self.engine.startBroadcast(stream_name, input_name, PVRConfig.vlcmux, PVRConfig.vlchlspreaccess)

    def destroy(self):
        if self._shuttingDown.isSet():
            # Already in the middle of destroying
            return
        self._shuttingDown.set()
        self.engine.stopBroadcast(self.stream_name)

    def getType(self):
        return HLSClient.ENGINE_TYPE

    def getUrl(self, timeout=40):
        time.sleep(1)
        return 'http://' + PVRConfig.vlchost + ':' + str(PVRConfig.vlcoutport) + '/' + self.stream_name

    def getPlayEvent(self, timeout=None):
        '''
        Blocking while in PAUSE, non-blocking while in RESUME
        '''
        # self._resumeevent.wait(timeout=timeout)
        return

