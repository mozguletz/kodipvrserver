#!/usr/bin/env python2
# -*- coding: utf-8 -*-
'''
AceProxy: Ace Stream to HTTP Proxy

Origina Website: https://github.com/ValdikSS/AceProxy
		Website: https://github.com/mozguletz/aceproxy
'''
import BaseHTTPServer
import SocketServer
import glob
import hashlib
import logging
import os
from random import randrange
import signal
from socket import error as SocketException
import sys
import time
import urllib2

import gevent.monkey

import clients
from clients.clientcounter import ClientCounter
import plugins.modules.ipaddr as ipaddr
from pvrconfig import PVRConfig
import vlcclient


# Monkeypatching and all the stuff
gevent.monkey.patch_all()
try:
    import pwd
    import grp
except ImportError:
    # Windows
    pass



class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    requestlist = []

    def handle_one_request(self):
        '''
        Add request to requestlist, handle request and remove from the list
        '''
        HTTPHandler.requestlist.append(self)
        BaseHTTPServer.BaseHTTPRequestHandler.handle_one_request(self)
        HTTPHandler.requestlist.remove(self)

    def closeConnection(self):
        '''
        Disconnecting client
        '''
        if self.clientconnected:
            self.clientconnected = False
            try:
                self.wfile.close()
                self.rfile.close()
            except:
                pass

    def dieWithError(self, errorcode=500):
        '''
        Close connection with error
        '''
        logging.warning("Dying with error")
        if self.clientconnected:
            self.send_error(errorcode)
            self.end_headers()
            self.closeConnection()

    def proxyReadWrite(self):
        '''
        Read video stream and send it to client
        '''
        logger = logging.getLogger('http_proxyReadWrite')
        logger.debug("Started")

        self.vlcstate = True

        try:
            while True:
                if PVRConfig.videoobey and not PVRConfig.vlcuse:
                    # Wait for PlayEvent if videoobey is enabled. Not for VLC
                    self.engine.getPlayEvent()

                if PVRConfig.videoobey and PVRConfig.vlcuse:
                    # For VLC
                    try:
                        # Waiting 0.5 seconds. If timeout, there would be exception.
                        # Set vlcstate to False in the exception and pause the stream
                        # A bit ugly, huh?
                        self.engine.getPlayEvent(0.5)
                        if not self.vlcstate:
                            PVRStuff.vlcclient.unPauseBroadcast(self.vlcid)
                            self.vlcstate = True
                    except gevent.Timeout:
                        if self.vlcstate:
                            PVRStuff.vlcclient.pauseBroadcast(self.vlcid)
                            self.vlcstate = False

                if not self.clientconnected:
                    logger.debug("Client is not connected, terminating")
                    break

                data = self.video.read(65500)
                if data and self.clientconnected:
                    self.wfile.write(data)
                else:
                    logger.warning("Video connection closed")
                    break
        except SocketException:
            # Video connection dropped
            logger.warning("Video connection dropped")
        finally:
            self.video.close()
            self.closeConnection()

    def hangDetector(self):
        '''
        Detect client disconnection while in the middle of something
        or just normal connection close.
        '''
        logger = logging.getLogger('http_hangDetector')
        try:
            while True:
                if not self.rfile.read():
                    break
        except:
            pass
        finally:
            self.clientconnected = False
            logger.debug("Client disconnected")
            try:
                self.requestgreenlet.kill()
            except:
                pass
            finally:
                gevent.sleep()
            return

    def perform_validation(self):
        logger = logging.getLogger('http_HTTPHandler.perform_validation')
        # If firewall enabled
        if PVRConfig.firewall:
            self.clientinrange = any(map(lambda i: ipaddr.IPAddress(self.clientip) \
                                in ipaddr.IPNetwork(i), PVRConfig.firewallnetranges))

            if (PVRConfig.firewallblacklistmode and self.clientinrange) or \
                (not PVRConfig.firewallblacklistmode and not self.clientinrange):
                    logger.info('Dropping connection from ' + self.clientip + ' due to firewall rules')
                    self.dieWithError(403)  # 403 Forbidden
                    raise Exception('Not a valid IP')

        logger.info("Accepted connection from " + self.clientip)
        logger.info("RequestURL " + self.path)
        logger.info("User Agent " + self.headers.get('User-Agent'))

        try:
            # If first parameter is 'pid' or 'torrent' or it should be handled
            # by plugin
            if not (self.reqtype in ('pid', 'torrent', 'sop') or self.reqtype in PVRStuff.pluginshandlers):
                self.dieWithError(400)  # 400 Bad Request
                raise Exception('Not valid handler')
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            raise Exception('Not a valid handler')

        # Check if third parameter exists
        # …/pid/blablablablabla/video.mpg
        #                      |_________|
        # And if it ends with regular video extension
        try:
            if len(self.splittedpath) > 2 and not self.path.endswith(('.3gp', '.avi', '.flv', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.ogv', '.ts', '.asf')):
                logger.error("Request seems like valid but no valid video extension was provided")
                self.dieWithError(400)
                raise Exception('Not a valid handler video stream')
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            raise Exception('Not a valid handler video stream')

    def set_engine_type(self):
        if self.reqtype == 'sop':
            self.engine_type = 'sop'
        else:
            self.engine_type = 'ace'

    def handle_in_plugin(self):
        logger = logging.getLogger('http_HTTPHandler.handle_in_plugin')
        if self.reqtype in PVRStuff.pluginshandlers:
            try:
                PVRStuff.pluginshandlers.get(self.reqtype).handle(self)
            except Exception as e:
                logger.error('Plugin exception: ' + repr(e))
                self.dieWithError()
            finally:
                return True


    def do_HEAD(self):
        return self.do_GET(headers_only=True)

    def do_GET(self, headers_only=False):
        '''
        GET request handler
        '''
        self.engine_type = None

        logger = logging.getLogger('http_HTTPHandler')
        self.clientconnected = True
        # Don't wait videodestroydelay if error happened
        self.errorhappened = True
        # Headers sent flag for fake headers UAs
        self.headerssent = False
        # Current greenlet
        self.requestgreenlet = gevent.getcurrent()
        # Connected client IP address
        self.clientip = self.request.getpeername()[0]

        self.splittedpath = self.path.split('/')
        self.reqtype = self.splittedpath[1].lower()
        if len(self.splittedpath) > 2:
            self.path_unquoted = urllib2.unquote(self.splittedpath[2])

        # perform IP and URL validation
        try:
        	self.perform_validation()
        except Exception as e:
			logger.error(repr(e))
			return

        self.set_engine_type()

        # Handle request with plugin handler
        if self.handle_in_plugin():
            self.closeConnection()
            return


        # Limit concurrent connections
        if PVRConfig.maxconns > 0 and PVRStuff.clientcounter.total >= PVRConfig.maxconns:
            logger.debug("Maximum connections reached, can't serve this")
            self.dieWithError(503)  # 503 Service Unavailable
            return

        # Pretend to work fine with Fake UAs or HEAD request.
        useragent = self.headers.get('User-Agent')
        fakeua = useragent and useragent in PVRConfig.fakeuas
        if headers_only and fakeua:
            if fakeua:
                logger.debug("Got fake UA: " + self.headers.get('User-Agent'))
            # Return 200 and exit
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
            self.end_headers()
            self.closeConnection()
            return


        # create client id and vlc id
        if self.reqtype == 'pid':
            self.client_id = 'acestream://' + self.path_unquoted
            self.vlcid = self.path_unquoted
        else:
            self.client_id = self.path_unquoted
            self.vlcid = hashlib.md5(self.path_unquoted).hexdigest()


        # Make list with parameters
        self.params = list()
        for i in xrange(3, 8):
            try:
                self.params.append(int(self.splittedpath[i]))
            except (IndexError, ValueError):
                self.params.append('0')

        # Adding client to clientcounter
        total_clients = PVRStuff.clientcounter.add(self.client_id, self.clientip)
        # If we are the one client, but sucessfully got ace from clientcounter,
        # then somebody is waiting in the videodestroydelay state
        self.engine = PVRStuff.clientcounter.getEngine(self.client_id)
        if not self.engine:
            shouldcreateace = True
        else:
            shouldcreateace = False

        # If we don't use VLC and we're not the first client
        if total_clients != 1 and not PVRConfig.vlcuse:
            PVRStuff.clientcounter.delete(self.client_id, self.clientip)
            logger.error("Not the first client, cannot continue in non-VLC mode")
            self.dieWithError(503)  # 503 Service Unavailable
            return

        if shouldcreateace:
            if self.engine_type == 'ace':
            # If we are the only client, create AceClient
                try:
                	self.engine = clients.AceClient(PVRConfig.acehost,
                                                    PVRConfig.aceport,
                                                    connect_timeout=PVRConfig.aceconntimeout,
                                                    result_timeout=PVRConfig.aceresulttimeout)
                	logger.info("AceClient created")
                except clients.AceException as e:
                    logger.error("AceClient create exception: " + repr(e))
                    PVRStuff.clientcounter.delete(self.client_id, self.clientip)
                    self.dieWithError(502)  # 502 Bad Gateway
                    return
            elif self.engine_type == 'sop':
                try:
                    self.engine = clients.SopcastProcess()
                    self.engine.fork_sop(urllib2.unquote(self.path_unquoted), str(randrange(1025, 34999, 1)), str(randrange(35000, 65350, 1)))
                    logger.info("SopClient created")
                except Exception as e:
                    logger.error("SopClient create exception: " + repr(e))
                    PVRStuff.clientcounter.delete(self.client_id, self.clientip)
                    self.dieWithError(502)  # 502 Bad Gateway
                    return
            else:
                logger.error("Unknown engine: " + repr(e))
                PVRStuff.clientcounter.delete(self.client_id, self.clientip)
                self.dieWithError(502)  # 502 Bad Gateway
                return

        # Adding AceClient instance to pool
        PVRStuff.clientcounter.addEngine(self.client_id, self.engine)

        # Send fake headers if this User-Agent is in fakeheaderuas tuple
        fakeua = useragent and useragent in PVRConfig.fakeheaderuas
        if fakeua:
            logger.debug("Sending fake headers for " + useragent)
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
            self.end_headers()
            # Do not send real headers at all
            self.headerssent = True

        try:
            self.hanggreenlet = gevent.spawn(self.hangDetector)
            logger.debug("hangDetector spawned")
            gevent.sleep()

            if self.engine_type == 'ace':
                # Initializing AceClient
                if shouldcreateace:
                    self.engine.init(gender=PVRConfig.acesex,
                                        age=PVRConfig.aceage,
                                        product_key=PVRConfig.acekey,
                                        pause_delay=PVRConfig.videopausedelay)
                    logger.debug("AceClient inited")
                    if self.reqtype == 'pid':
                        self.engine.START(self.reqtype, {'content_id': self.path_unquoted, 'file_indexes': self.params[0]})
                    elif self.reqtype == 'torrent':
                        self.paramsdict = dict(zip(clients.acemessages.PVRConst.START_TORRENT, self.params))
                        self.paramsdict['url'] = self.path_unquoted
                        self.engine.START(self.reqtype, self.paramsdict)
                    logger.debug("START done")

                # Getting URL
                self.url = self.engine.getUrl(PVRConfig.videotimeout)

                # Rewriting host for remote Ace Stream Engine
                self.url = self.url.replace('127.0.0.1', PVRConfig.acehost)
            elif self.engine_type == 'sop':
                # Getting URL
                logger.debug("Getting the url ")
                self.url = self.engine.getUrl(PVRConfig.videotimeout)
            else:
                logger.error("Unknown engine: " + repr(e))
                PVRStuff.clientcounter.delete(self.client_id, self.clientip)
                self.dieWithError(502)  # 502 Bad Gateway
                return

            self.errorhappened = False
            logger.debug("Got url " + self.url)


            if PVRConfig.vlcuse and shouldcreateace:
                # (shouldcreateace or not PVRStuff.vlcclient.showBroadcast(self.vlcid).get('enabled', False)):  # or (PVRStuff.clientcounter.get(self.client_id) == 1):
                # If using VLC, add this url to VLC
                # Force ffmpeg demuxing if set in config
                if PVRConfig.vlcforceffmpeg:
                    self.vlcprefix = 'http/ffmpeg://'
                else:
                    self.vlcprefix = ''

                # Sleeping videodelay
                gevent.sleep(PVRConfig.videodelay)
                # Sleep a bit, because sometimes VLC doesn't open port in time
                gevent.sleep(1)
                PVRStuff.vlcclient.startBroadcast(self.vlcid, self.vlcprefix + self.url, PVRConfig.vlcmux, PVRConfig.vlcpreaccess)

            # Building new VLC url
            if PVRConfig.vlcuse:
                self.url = 'http://' + PVRConfig.vlchost + ':' + str(PVRConfig.vlcoutport) + '/' + self.vlcid
                logger.debug("VLC url " + self.url)
                # PVRStuff.vlcclient.showBroadcast(self.vlcid)

            # Sending client headers to video stream
            self.video = urllib2.Request(self.url)
            for key in self.headers.dict:
                self.video.add_header(key, self.headers.dict[key])

            self.video = urllib2.urlopen(self.video)

            # Sending video stream headers to client
            if not self.headerssent:
                self.send_response(self.video.getcode())
                if self.video.info().dict.has_key('connection'):
                    del self.video.info().dict['connection']
                if self.video.info().dict.has_key('server'):
                    del self.video.info().dict['server']
                if self.video.info().dict.has_key('transfer-encoding'):
                    del self.video.info().dict['transfer-encoding']
                if self.video.info().dict.has_key('keep-alive'):
                    del self.video.info().dict['keep-alive']

                for key in self.video.info().dict:
                    self.send_header(key, self.video.info().dict[key])
                # End headers. Next goes video data
                self.end_headers()
                logger.debug("Headers sent")

            if not PVRConfig.vlcuse:
                # Sleeping videodelay
                gevent.sleep(PVRConfig.videodelay)

            # Run proxyReadWrite
            self.proxyReadWrite()
            logger.debug("Proxy handler finished")
            self.requestgreenlet.kill()
            gevent.sleep()

            # Waiting until hangDetector is joined
            # self.hanggreenlet.join()
            # logger.debug("Request handler finished")

        except (clients.AceException, clients.SopException, vlcclient.VlcException, urllib2.URLError) as e:
            logger.error("Exception: " + repr(e))
            self.errorhappened = True
            self.dieWithError()
        except gevent.GreenletExit:
            # hangDetector told us about client disconnection
            pass
        except Exception as e:
            # Unknown exception
            logger.error("Unknown exception: " + repr(e))
            self.errorhappened = True
            self.dieWithError()
        finally:
            logger.debug("END REQUEST")
            PVRStuff.clientcounter.delete(self.client_id, self.clientip)
            if not self.errorhappened and not PVRStuff.clientcounter.get(self.client_id):
                logger.debug("Sleeping until a different URL or for max " + str(PVRConfig.videodestroydelay) + " seconds")
                for seconds in range(0, PVRConfig.videodestroydelay * 2):
                    gevent.sleep(0.5)
                    if PVRStuff.clientcounter.existsSameIP(self.client_id, self.clientip):
                        break
                # If no error happened and we are the only client
            if not PVRStuff.clientcounter.get(self.client_id):
                logger.debug("That was the last client, destroying the engine")
                if PVRConfig.vlcuse:
                    try:
                        PVRStuff.vlcclient.stopBroadcast(self.vlcid)
                    except:
                        pass
                PVRStuff.clientcounter.deleteEngine(self.client_id)
                self.engine.destroy()



class HTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):

    def handle_error(self, request, client_address):
        # Do not print HTTP tracebacks
        pass

class PVRStuff(object):
    '''
    Inter-class interaction class
    '''

# taken from http://stackoverflow.com/questions/2699907/dropping-root-permissions-in-python
def drop_privileges(uid_name, gid_name='nogroup'):

    # Get the uid/gid from the name
    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_uid_home = pwd.getpwnam(uid_name).pw_dir
    running_gid = grp.getgrnam(gid_name).gr_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    os.umask(077)

    if os.getuid() == running_uid and os.getgid() == running_gid:
        # could be useful
        os.environ['HOME'] = running_uid_home
        return True
    return False




'''
								Main program
'''


logging.basicConfig(filename=PVRConfig.logpath + 'pvrserver.log' if PVRConfig.loggingtoafile else None,
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s', datefmt='%d.%m.%Y %H:%M:%S', level=PVRConfig.debug)
logger = logging.getLogger('INIT')

# Loading plugins
# Trying to change dir (would fail in freezed state)
try:
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
except:
    pass
# Creating dict of handlers
PVRStuff.pluginshandlers = dict()
# And a list with plugin instances
PVRStuff.pluginlist = list()
pluginsmatch = glob.glob('plugins/*_plugin.py')
sys.path.insert(0, 'plugins')
pluginslist = [os.path.splitext(os.path.basename(x))[0] for x in pluginsmatch]
for i in pluginslist:
    plugin = __import__(i)
    plugname = i.split('_')[0].capitalize()
    try:
        plugininstance = getattr(plugin, plugname)(PVRConfig, PVRStuff)
    except Exception as e:
        logger.error("Cannot load plugin " + plugname + ": " + repr(e))
        continue
    logger.debug('Plugin loaded: ' + plugname)
    for j in plugininstance.handlers:
        PVRStuff.pluginshandlers[j] = plugininstance
    PVRStuff.pluginlist.append(plugininstance)

# Check whether we can bind to the defined port safely
if PVRConfig.osplatform != 'Windows' and os.getuid() != 0 and PVRConfig.httpport <= 1024:
    logger.error("Cannot bind to port " + str(PVRConfig.httpport) + " without root privileges")
    quit(1)

server = HTTPServer((PVRConfig.httphost, PVRConfig.httpport), HTTPHandler)
logger = logging.getLogger('HTTP')

# Dropping root privileges if needed
if PVRConfig.osplatform != 'Windows' and PVRConfig.pvruser and os.getuid() == 0:
    if drop_privileges(PVRConfig.pvruser):
        logger.info("Dropped privileges to user " + PVRConfig.pvruser)
    else:
        logger.error("Cannot drop privileges to user " + PVRConfig.pvruser)
        quit(1)

# Creating ClientCounter
PVRStuff.clientcounter = ClientCounter()

# We need gevent >= 1.0.0 to use gevent.subprocess
if PVRConfig.acespawn or PVRConfig.vlcspawn:
    try:
        gevent.monkey.patch_subprocess()
    except:
        logger.error("Cannot spawn anything without gevent 1.0.0 or higher.")
        quit(1)

if PVRConfig.vlcspawn or PVRConfig.acespawn:
    DEVNULL = open(os.devnull, 'wb')

# Spawning procedures
def spawnVLC(cmd, delay=0):
    try:
        PVRStuff.vlc = gevent.subprocess.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        gevent.sleep(delay)
        return True
    except:
        return False

def connectVLC():
    try:
        PVRStuff.vlcclient = vlcclient.VlcClient(host=PVRConfig.vlchost,
                                                 port=PVRConfig.vlcport,
                                                 password=PVRConfig.vlcpass,
                                                 out_port=PVRConfig.vlcoutport)
        return True
    except vlcclient.VlcException as e:
        print repr(e)
        return False

def spawnAce(cmd, delay=0):
    if PVRConfig.osplatform == 'Windows':
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        try:
            key = _winreg.OpenKey(reg, 'Software\AceStream')
        except:
            print "Can't find acestream!"
            quit(1)
        engine = _winreg.QueryValueEx(key, 'EnginePath')
        PVRStuff.acedir = os.path.dirname(engine[0])
        try:
            PVRConfig.aceport = int(open(PVRStuff.acedir + '\\acestream.port', 'r').read())
            logger.warning("Ace Stream is already running, disabling runtime checks")
            PVRConfig.acespawn = False
            return True
        except IOError:
            cmd = engine[0].split()
    try:
        PVRStuff.ace = gevent.subprocess.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        gevent.sleep(delay)
        return True
    except:
        return False

def isRunning(process):
    if process.poll() is not None:
        return False
    return True

def clean_proc():
    # Trying to close all spawned processes gracefully
    if PVRConfig.vlcspawn and isRunning(PVRStuff.vlc):
        PVRStuff.vlcclient.destroy()
        gevent.sleep(1)
        # by this moment vlc should be terminated if not, ask
        if isRunning(PVRStuff.vlc):
            PVRStuff.vlc.terminate()
            gevent.sleep(.5)
        # or not :)
        if isRunning(PVRStuff.vlc):
            PVRStuff.vlc.kill()
    if PVRConfig.acespawn and isRunning(PVRStuff.ace):
        PVRStuff.ace.terminate()
        gevent.sleep(1)
        if isRunning(PVRStuff.ace):
            PVRStuff.ace.kill()
        # for windows, subprocess.terminate() is just an alias for kill(), so we have to delete the acestream port file manually
        if PVRConfig.osplatform == 'Windows' and os.path.isfile(PVRStuff.acedir + '\\acestream.port'):
            os.remove(PVRStuff.acedir + '\\acestream.port')

# This is what we call to stop the server completely
def shutdown(signum=0, frame=0):
    logger.info("Stopping server...")
    # Closing all client connections
    for connection in server.RequestHandlerClass.requestlist:
        try:
            # Set errorhappened to prevent waiting for videodestroydelay
            connection.errorhappened = True
            connection.hanggreenlet.kill()
        except:
            logger.warning("Cannot kill a connection!")
    clean_proc()
    server.server_close()
    quit()

def _reloadconfig():
    '''
    Reload configuration file.
    SIGHUP handler.
    '''
    global PVRConfig

    logger = logging.getLogger('reloadconfig')
    reload(PVRConfig)
    logger.info('Config reloaded')

# setting signal handlers
try:
    gevent.signal(signal.SIGHUP, _reloadconfig)
    gevent.signal(signal.SIGTERM, shutdown)
except AttributeError:
    # not available on Windows
    pass

if PVRConfig.vlcuse:
    if PVRConfig.vlcspawn:
        PVRStuff.vlcProc = PVRConfig.vlccmd.split()
        if spawnVLC(PVRStuff.vlcProc, 1) and connectVLC():
            logger.info("VLC spawned with pid " + str(PVRStuff.vlc.pid))
        else:
            logger.error("Cannot spawn VLC!")
            quit(1)
    else:
        if not connectVLC():
            logger.error("vlc is not running")
            clean_proc()
            quit(1);

if PVRConfig.acespawn:
    if PVRConfig.osplatform == 'Windows':
        import _winreg
        import os.path
        PVRStuff.aceProc = ""
    else:
        PVRStuff.aceProc = PVRConfig.acecmd.split()
    if spawnAce(PVRStuff.aceProc, 1):
        # could be redefined internally
        if PVRConfig.acespawn:
            logger.info("Ace Stream spawned with pid " + str(PVRStuff.ace.pid))
    else:
        logger.error("Cannot spawn Ace Stream!")
        clean_proc()
        quit(1)


try:
    logger.info("Using gevent %s" % gevent.__version__)
    if PVRConfig.vlcuse:
        logger.info("%s" % PVRStuff.vlcclient._vlcver)
    logger.info("Server started.")
    while True:
        if PVRConfig.vlcspawn and PVRConfig.vlcuse:
            if not isRunning(PVRStuff.vlc):
                del PVRStuff.vlc
                if spawnVLC(PVRStuff.vlcProc, 1) and connectVLC():
                    logger.info("VLC died, respawned it with pid " + str(PVRStuff.vlc.pid))
                else:
                    logger.error("Cannot spawn VLC!")
                    clean_proc()
                    quit(1)
        if PVRConfig.acespawn:
            if not isRunning(PVRStuff.ace):
                del PVRStuff.ace
                if spawnAce(PVRStuff.aceProc, 1):
                    logger.info("Ace Stream died, respawned it with pid " + str(PVRStuff.ace.pid))
                else:
                    logger.error("Cannot spawn Ace Stream!")
                    clean_proc()
                    quit(1)
        # Return to our server tasks
        server.handle_request()
except (KeyboardInterrupt, SystemExit):
    shutdown()
