'''
Playlist Generator
This module can generate .m3u playlists with tv guide
and groups
'''
import re
import urllib2

class PlaylistGenerator(object):

    m3uheader = \
        '#EXTM3U url-tvg="http://www.teleguide.info/download/new3/jtv.zip"\n'
    m3uchanneltemplate = \
        '#EXTINF:-1 group-title="%s" tvg-name="%s"%s,%s\n%s\n'

    def __init__(self):
        self.itemlist = list()

    def addItem(self, itemdict):
        '''
        Adds item to the list
        itemdict is a dictionary with the following fields:
            name - item name
            url - item URL
            radio - true or false in case if is a radio stream (optional)
            tvg - item JTV name (optional)
            group - item playlist group (optional)
        '''
        self.itemlist.append(itemdict)

    @staticmethod
    def _generatem3uline(item):
        '''
        Generates EXTINF line with url
        '''
        return PlaylistGenerator.m3uchanneltemplate % (item.get('group', ''),
                                                       item.get('tvg', ''),
                                                       ' radio="true"' if item.get('radio', False) else '',
                                                       item.get('name'),
                                                       item.get('url'))

    def exportm3u(self, hostport, add_ts=False, m3uheader=m3uheader):
        '''
        Exports m3u playlist
        '''
        if add_ts:
                # Adding ts:// after http:// for some players
                hostport = 'ts://' + hostport

        for item in self.itemlist:
            if not item['name'] or len(item['name'].strip()) == 0 or not item['url'] or len(item['url'].strip()) == 0:
                continue

            item['tvg'] = item.get('tvg', '') if item.get('tvg') else item.get('name')  # .replace(' ', '_')

            if  item.get('transit', True):
                # For .acelive and .torrent
                item['url'] = re.sub('^(http.+)$', lambda match: 'http://' + hostport + '/torrent/' + urllib2.quote(match.group(0), '') + '/stream.mp4', item['url'], flags=re.MULTILINE)
                # For Sopcast
                item['url'] = re.sub('^(sop.+)$', lambda match: 'http://' + hostport + '/sop/' + urllib2.quote(match.group(0), '') + '/tv.asf', item['url'], flags=re.MULTILINE)
                # For PIDs
                item['url'] = re.sub('^(acestream://)?(?P<pid>[0-9a-f]{40})$', 'http://' + hostport + '/pid/\\g<pid>/stream.mp4', item['url'], flags=re.MULTILINE)

            m3uheader += PlaylistGenerator._generatem3uline(item)

        return m3uheader
