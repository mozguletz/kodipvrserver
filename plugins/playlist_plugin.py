import codecs
import json
import logging
import time

from modules.PlaylistGenerator import PlaylistGenerator
from modules.PluginInterface import PVRProxyPlugin


class Playlist(PVRProxyPlugin):
    handlers = ('playlist',)

    logger = logging.getLogger('playlist')
    m3uheader = '#EXTM3U url-tvg="http://%s/epg"\n'

    playlist_json = None
    playlisttime = int(time.time())

    def generatePlaylist(self):
        try:
            Playlist.logger.debug('Reading Local Playlist')
            Playlist.playlist_json = codecs.open('channels.json', encoding='utf-8').read()
            Playlist.playlisttime = int(time.time())


        except Exception as e:
            Playlist.logger.error("Exception: Can't open playlist!\n" + repr(e))
            return False

        return True


    def handle(self, connection):
        # 30 minutes cache
        if not Playlist.playlist_json or (int(time.time()) - Playlist.playlisttime > 5 * 60):
            if not self.generatePlaylist():
                connection.dieWithError()
                return

        hostport = connection.headers['Host']
        Playlist.logger.debug(connection.headers)
        connection.send_response(200)
        connection.send_header('Content-Type', 'application/x-mpegurl')
        connection.send_header('Content-Disposition', 'inline; filename="playlist.m3u"')
        connection.end_headers()


        # Un-JSON channel list
        try:
            jsonplaylist = json.loads(Playlist.playlist_json)
        except Exception as e:
            Playlist.logger.error("Can't parse JSON Radio Playlist!" + repr(e))
            return False

        playlistgen = PlaylistGenerator()

        # Addind Radio channels from JSO
        for channel in jsonplaylist['radio']['channels']:
            channel['radio'] = 'true'
            channel['transit'] = False
            if not channel.get('hide'):
                playlistgen.addItem(channel)

        # Addind TV channels from JSON
        for channel in jsonplaylist['tv']['channels']:
            if not channel.get('hide'):
                playlistgen.addItem(channel)

        connection.wfile.write(playlistgen.exportm3u(hostport, False, Playlist.m3uheader % hostport).encode('utf-8'))
