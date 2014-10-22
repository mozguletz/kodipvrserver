import logging
import os.path
import random
import re
import socket
import threading
import time

import gevent

import clients


class SopException(Exception):
	'''
    Exception from SopClient
	'''
	pass


class Fork():
	logger = logging.getLogger('Sopcast_Fork')

	def __init__(self):
		self.command = ''
		self.args = ''
		self.port = 0

	def launch_sop(self):
		DEVNULL = open(os.devnull, 'wb')
		args = "%s %s" % (self.command, self.args)
		self.child = gevent.subprocess.Popen(args.split(), stdout=DEVNULL, stderr=DEVNULL)

		self.monitor = SopMonitor(self.port)
		self.monitor.start()
		Fork.logger.info('Sopcast spawned with pid ' + str(self.child.pid))

	def kill(self):
		if self.is_running() == True:
			try:
				self.monitor.requestStop()
				self.child.terminate()
			except OSError:
				pass

			time.sleep(1)

			try:
				if self.is_running() == True:
					self.child.kill()
			except OSError:
				pass

	def is_running(self):
		if self.child.poll() is not None:
			return False
		return True

	def buffer_loaded_progress(self):
		return self.monitor.buffer_loaded_progress

class SopMonitor(threading.Thread):
	logger = logging.getLogger('SopMonitor')
	INIT = "state\n\n\n\n\n\ns"
	STATUS = "s\n"
	CLOSE = "k\n"

	def __init__(self, port):
		threading.Thread.__init__(self)
		self.port = port
		self.loop = True
		self.connected = False
		self.buffer_loaded_progress = 0

	def run(self):
		BUFFERSIZE = 128
		while self.loop:
			if not self.connected:
				try:
					self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					self.sock.connect(('127.0.0.1', self.port))
					self.connected = True
					SopMonitor.logger.debug("Connected to Sopcast")
					self.sock.send(SopMonitor.INIT)
					self.sock.recv(BUFFERSIZE)
				except:
					self.connected = False

			time.sleep(.5)

			if self.connected:
				try:
					if self.sock.send(SopMonitor.STATUS) == 0:
						raise
					msg = ''
					while msg.count("\n") == 0:
						chunk = self.sock.recv(BUFFERSIZE)
						if not chunk:
							raise
						msg = msg + chunk

					stat = re.split('\\s+', msg)
					if len(stat) > 0:
						self.buffer_loaded_progress = int(stat[0])
					time.sleep(1)
				except:
					self.buffer_loaded_progress = 0
			else:
				# Not connected
				self.buffer_loaded_progress = -1
		self.sock.close()

	def requestStop(self):
		self.loop = False


class SopcastProcess(clients.PVRClient):
	ENGINE_TYPE = 'sop'

	logger = logging.getLogger('SopcastEngine')

	def __init__(self, vlc_client):
		self.f = Fork()
		self.vlc_client = vlc_client
		self.exe_name = None

	def __del__(self):
		self.destroy()

	def destroy(self):
		# Fork.logger.debug("Destroying client...")
		self.vlc_client.stopBroadcast(self.stream_name)
		self.f.kill()
	def getType(self):
		return SopcastProcess.ENGINE_TYPE

	def getUrl(self, timeout=40):
		seconds = timeout
		while seconds > 0:
			time.sleep(1)
			seconds = seconds - 1

			buff = self.f.buffer_loaded_progress()
			if buff > 20:
				return self.url;
			elif buff == -1:
				if not self.is_running():
					raise SopException("Invalid channel. Sopcast process terminated.")
				SopcastProcess.logger.debug("Not connected")
		raise SopException("getURL timeout!")


	def get_sp_sc_name(self):
		if self.exe_name == None:
			exe_names = ["sp-sc-auth", "sp-sc"]

			for name in exe_names:
				if any([os.path.exists(os.path.join(p, name)) for p in os.environ["PATH"].split(":")]):
					self.exe_name = name
					return self.exe_name

			if self.exe_name == None:
				raise SopException("ForkSOP", "Critical error, sp-sc-auth not found. Please install sp-auth!")
		else:
			return self.exe_name

	def init(self, stream_name, sop_address, inbound_port, outbound_port):
		self.url = "http://127.0.0.1:%s/tv.asf" % str(outbound_port)
		self.f.command = self.get_sp_sc_name()
		self.stream_name = stream_name
		if sop_address == None or inbound_port == None or outbound_port == None:
			SopcastProcess.logger.error("invalid call to fork_sop")
			raise SopException('invalid call to fork_sop')
		else:
			self.f.args = '%s %s %s' % (sop_address, inbound_port, outbound_port)
			self.f.port = outbound_port

		# SopcastProcess.logger.error("launching sopcast")
		self.f.launch_sop()

		SopcastProcess.logger.debug("Sopcast url: " + sop_address + "  video stream: " + self.url)


	def quit_sop(self):
		self.f.stop()
		# self.f.join();

	def kill_sop(self):
		self.f.kill()
		# self.f.join();

	def is_running(self):
		return self.f.is_running()

	def getPlayEvent(self, timeout=None):
		# self._resumeevent.wait(timeout=timeout)
		# TODO
		time.sleep(random.uniform(.0, .2))
		return

	def buffer_loaded_progress(self):
		return self.f.buffer_loaded_progress()

