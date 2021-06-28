# coding: utf-8

import socket
import daemon
from threading import Thread
import paho.mqtt.client as mqtt
from queue import Queue, Empty
from pickle import loads, dumps, UnpicklingError
import time
from subprocess import Popen, TimeoutExpired, PIPE, STDOUT
from os.path import abspath, dirname
from signal import SIGINT


class DaemonStop(Exception):
  pass


class Daemon_run:
  def __init__(self,
               port: int,
               address: str = 'localhost',
               topic_in: str = 'Remote_control',
               topic_out: str = 'Server_status') -> None:
    if not isinstance(port, int):
      raise TypeError("port should be an integer")
    if not isinstance(topic_in, str):
      raise TypeError("topic_in should be a string")
    if not isinstance(topic_out, str):
      raise TypeError("topic_out should be a string")

    self._topic_in = topic_in
    self._topic_out = topic_out
    self._queue = Queue()
    self._client = mqtt.Client(str(time.time()))
    self._client.on_connect = self._on_connect
    self._client.on_message = self._on_message
    self._client.reconnect_delay_set(max_delay=10)

    self._protocol = None
    self._is_protocol_active = False
    self._last_return_code = None

    self._launch_mosquitto(port)
    time.sleep(5)

    try_count = 15
    while True:
      try:
        self._client.connect(host=address, port=port, keepalive=10)
        break
      except socket.timeout:
        raise
      except socket.gaierror:
        raise
      except ConnectionRefusedError:
        try_count -= 1
        if try_count == 0:
          raise
        time.sleep(1)

    self._client.loop_start()
    print("Started Mosquitto")

  def __call__(self) -> None:
    try:
      print("Starting manager")
      self._protocol_manager()
    except DaemonStop:
      self._publish("Stopping the server and the MQTT broker")
      time.sleep(3)
    finally:
      print("Finishing")
      self._client.loop_stop()
      self._client.disconnect()
      try:
        self._mosquitto.terminate()
        self._mosquitto.wait(timeout=15)
        print("Finished OK")
      except TimeoutExpired:
        self._mosquitto.kill()
        print("Finished NOK")

  def _launch_mosquitto(self, port: int) -> None:
    try:
      self._mosquitto = Popen(['mosquitto', '-p', str(port)])
    except FileNotFoundError:
      raise

  def _on_message(self, client, userdata, message) -> None:
    try:
      self._queue.put_nowait(loads(message.payload))
    except UnpicklingError:
      self._publish("Warning ! Message raised UnpicklingError, ignoring it")
    print("Got message")

  def _on_connect(self, client, userdata, flags, rc) -> None:
    self._client.subscribe(topic=self._topic_in, qos=2)
    print("Subscribed")
    self._client.loop_start()

  def _publish(self, message: str) -> None:
    self._client.publish(topic=self._topic_out,
                         payload=dumps(message),
                         qos=2)

  def _protocol_manager(self):
    while True:
      # Checking if the protocol is still running
      if self._is_protocol_active:
        if self._protocol.poll() is not None:
          self._is_protocol_active = False
          self._last_return_code = self._protocol.poll()

      # Getting the command message and executing the associated action
      if not self._queue.empty():
        try:
          message = self._queue.get_nowait()
        except Empty:
          message = None

        if message == "Print status":
          print("Print status")
          self._protocol_status()

        elif message == "Start protocol":
          print("Start protocol")
          self._start_protocol()

        elif message == "Stop protocol":
          print("Stop protocol")
          self._stop_protocol()

        elif message == "Stop server":
          if self._is_protocol_active:
            if self._stop_protocol():
              self._publish("Error ! Could not stop the current protocol, "
                            "server not stopped")
              continue
          raise DaemonStop

        else:
          self._publish("Error ! Invalid command message")

      time.sleep(1)

  def _protocol_status(self) -> None:
    if self._is_protocol_active:
      self._publish("Protocol running")
    elif self._last_return_code == 0:
      self._publish("Protocol terminated gracefully")
    elif self._last_return_code is not None:
      self._publish("Protocol terminated with an error")
    else:
      self._publish("No protocol started yet")

  def _start_protocol(self) -> None:
    if not self._is_protocol_active:
      self._protocol = Popen(['python3', 'Protocol.py'])
      try:
        self._protocol.wait(10)
        self._publish("Error ! Protocol crashed at starting")
      except TimeoutExpired:
        self._is_protocol_active = True
        self._publish("Protocol started")
    else:
      self._publish("Protocol already running, stop it before starting new "
                    "one")

  def _stop_protocol(self) -> int:
    if not self._is_protocol_active:
      print("No protocol currently running !")
      self._publish("No protocol currently running !")
    else:
      self._protocol.send_signal(SIGINT)
      try:
        self._last_return_code = self._protocol.wait(10)
      except TimeoutExpired:
        try:
          self._protocol.terminate()
          self._last_return_code = self._protocol.wait(10)
        except TimeoutExpired:
          self._protocol.kill()
          self._last_return_code = self._protocol.wait(10)
      if self._last_return_code is None:
        print("Error ! Could not stop the protocol")
        self._publish("Error ! Could not stop the protocol")
        self._is_protocol_active = True
        return 1
      elif self._last_return_code == 0:
        print("Protocol terminated gracefully")
        self._publish("Protocol terminated gracefully")
        self._is_protocol_active = False
      else:
        print("Protocol terminated with an error")
        self._publish("Protocol terminated with an error")
        self._is_protocol_active = False
    return 0


if __name__ == "__main__":
  # with daemon.DaemonContext(working_directory=dirname(abspath(__file__))):
  Daemon_run(1148)()
