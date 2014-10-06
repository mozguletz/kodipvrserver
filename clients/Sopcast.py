
import logging
import os.path
import popen2
import random
import signal
import sys
import threading
import time

import gevent

import clients


class Fork():
	logger = logging.getLogger('sopcast_fork')

	def __init__(self):
		self.command = ''
		self.args = ''
		self.pid = 0
		self.worker = ForkWorker()

	def launch_sop(self):
		DEVNULL = open(os.devnull, 'wb')
		args = "%s %s" % (self.command, self.args)
		self.child = gevent.subprocess.Popen(args.split(), stdout=DEVNULL, stderr=DEVNULL)

		time.sleep(1)

		self.pid = self.child.pid
		self.worker.set_pid(self.pid)
		self.worker.start()
		Fork.logger.info('Sopcast spawned with pid ' + str(self.pid))

	def kill(self):
		if self.is_running() == True:
			try:
				self.child.terminate()
				time.sleep(.5)
				if self.is_running() == True:
					self.child.kill()
			except OSError:
				pass
			try:
				if self.is_running() == True:
					self.child.kill()
			except OSError:
				pass

	def is_running(self):
		if self.child.poll() is not None:
			return False
		return True

class ForkWorker(threading.Thread):
	logger = logging.getLogger('sopcast_fork_worker')

	def __init__(self):
		threading.Thread.__init__(self)
		self.loop = True
		self.pid = 0
		self.nblockAvailable = -1
	def run(self):
		while self.loop:
			time.sleep(.1)
			try:
				os.waitpid(self.pid, os.WNOHANG)
			except OSError as e:
				self.loop = False
			except Exception as e:
				self.loop = False
				sys.stderr.write("ForkWorker.run() %s\n" % repr(e))
		# send terminate signal
		try:
			os.kill(self.pid, signal.SIGKILL)
			sys.stderr.write("Fork.run() Sent sigterm, waiting for result")
			os.wait()
		except Exception:
			pass
		finally:
			self.pid = 0

	def stop(self):
		self.loop = False

	def set_pid(self, pid=0):
		self.pid = pid

class SopcastProcess(clients.PVRClient):
	logger = logging.getLogger('SopcastEngine')

	def __init__(self):
		self.f = Fork()
		self.exe_name = None
		self.loop = True

	def __del__(self):
		self.destroy()

	def destroy(self):
		# Fork.logger.debug("Destroying client...")
		self.f.kill()

	def getUrl(self, timeout=40):
		# TODO the logic to retreive the url only when sopcast buffer is more then 10%
		# time.sleep(10)
		return self.url;

	def get_sp_sc_name(self):
		if self.exe_name == None:
			exe_names = ["sp-sc-auth", "sp-sc"]

			for name in exe_names:
				if any([os.path.exists(os.path.join(p, name)) for p in os.environ["PATH"].split(":")]):
					self.exe_name = name
					return self.exe_name

			if self.exe_name == None:
				raise Exception("ForkSOP", "Critical error, sp-sc-auth not found. Please install sp-auth!")
		else:
			return self.exe_name

	def fork_sop(self, sop_address, inbound_port, outbound_port):
		self.url = "http://127.0.0.1:%s/tv.asf" % str(outbound_port)
		self.f.command = self.get_sp_sc_name()

		if sop_address == None or inbound_port == None or outbound_port == None:
			Fork.logger.error("invalid call to fork_sop")
			raise RuntimeError('invalid call to fork_sop')
		else:
			self.f.args = '%s %s %s' % (sop_address, inbound_port, outbound_port)

		# Fork.logger.error("launching sopcast")
		self.f.launch_sop()

		SopcastProcess.logger.debug("Sopcast channel  url: " + sop_address)
		SopcastProcess.logger.debug("Sopcast video stream: " + self.url)


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
		time.sleep(random.uniform(.0, .2))
		return

