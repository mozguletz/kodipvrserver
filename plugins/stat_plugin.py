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
        connection.wfile.write('<html><body>')
        connection.wfile.write('<h4>Connected clients: ' + str(self.stuff.clientcounter.total) + '</h4>')
        connection.wfile.write('<h5>Concurrent connections limit: ' + str(self.config.maxconns) + '</h5>')

        for engine in self.stuff.clientcounter.engines:

            connection.wfile.write(str(engine))
            if self.stuff.clientcounter.engines[engine].getType() == 'sop':
                buffering = self.stuff.clientcounter.engines[engine].buffer_loaded_progress()
                connection.wfile.write(' (Buffering %d%%)' % buffering if buffering != -1 else ' (Connecting...)')

            connection.wfile.write(' : ')

            if self.stuff.clientcounter.clients.has_key(engine):
                connection.wfile.write(str(self.stuff.clientcounter.clients[engine][0]) + ' ' + str(self.stuff.clientcounter.clients[engine][1]) + '<br>')
            else:
                connection.wfile.write('No clients, waiting to be destroyed')
        connection.wfile.write('</body></html>')
