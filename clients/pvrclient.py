from acemessages import PVRConst

class PVRClient(object):

    def __init__(self, host, port, connect_timeout=5, result_timeout=10):
        pass

    def destroy(self):
        pass

    def init(self, gender=PVRConst.SEX_MALE, age=PVRConst.AGE_18_24, product_key=None, pause_delay=0):
        pass

    def getUrl(self, timeout=40):
        pass

    def getPlayEvent(self, timeout=None):
        pass
