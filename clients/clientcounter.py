'''
Simple Client Counter for VLC VLM
'''


class ClientCounter(object):

    def __init__(self):
        self.clients = dict()
        self.engines = dict()
        self.total = 0

    def get(self, id):
        return self.clients.get(id, (False,))[0]

    def existsSameIP(self, id, ip):
        for client in self.clients:
            return id != client and ip in self.clients[client][1]
        return False

    def add(self, id, ip):
        if self.clients.has_key(id):
            self.clients[id][0] += 1
            self.clients[id][1].append(ip)
        else:
            self.clients[id] = [1, [ip]]

        self.total += 1
        return self.clients[id][0]

    def delete(self, id, ip):
        if self.clients.has_key(id):
            self.total -= 1
            if self.clients[id][0] == 1:
                del self.clients[id]
                return False
            else:
                self.clients[id][0] -= 1
                self.clients[id][1].remove(ip)
        else:
            return False

        return self.clients[id][0]

    def getEngine(self, id):
        return self.engines.get(id, False)

    def addEngine(self, id, value):
        if self.engines.has_key(id):
            return False

        self.engines[id] = value
        return True

    def deleteEngine(self, id):
        if not self.engines.has_key(id):
            return False

        del self.engines[id]
        return True
