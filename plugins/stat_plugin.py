'''
Simple statistics plugin

To use it, go to http://127.0.0.1:8000/stat
'''
from modules.PluginInterface import PVRProxyPlugin


class Stat(PVRProxyPlugin):
    handlers = ('stat',)

    def __init__(self, PVRConfig, PVRStuff):
        self.config = PVRConfig
        self.stuff = PVRStuff

    def handle(self, connection):
        connection.send_response(200)
        connection.send_header('Content-type', 'text/html')
        connection.end_headers()
        connection.wfile.write(
            '<html><body><h4>Connected clients: ' + str(self.stuff.clientcounter.total) + '</h4>')
        connection.wfile.write(
            '<h5>Concurrent connections limit: ' + str(self.config.maxconns) + '</h5>')
        for i in self.stuff.clientcounter.clients:
            connection.wfile.write(str(i) + ' : ' + str(self.stuff.clientcounter.clients[i][0]) + ' ' +
                                   str(self.stuff.clientcounter.clients[i][1]) + '<br>')

        connection.wfile.write('<h5>Running engines: ' + str(len(self.stuff.clientcounter.engines)) + '</h5>')



        connection.wfile.write('</body></html>')
