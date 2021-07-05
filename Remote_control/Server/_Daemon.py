# coding: utf-8

import socket
import paho.mqtt.client as mqtt
from queue import Queue, Empty
from pickle import loads, dumps, UnpicklingError
import time
from subprocess import Popen, TimeoutExpired
from os.path import abspath, dirname, exists
from os import mkdir
from signal import SIGINT


class DaemonStop(Exception):
  """Exception raised for stopping the daemon thread."""

  pass


class Daemon_run:
  """A class for managing the stimulation protocols.

  It allows to start and stop the protocols safely as a separate process. Can
  also return the status of the protocol, and end itself.
  """

  def __init__(self,
               port: int,
               address: str = 'localhost',
               topic_in: str = 'Remote_control',
               topic_out: str = 'Server_status',
               topic_protocol_in: str = 'Protocols_upload',
               topic_protocol_out: str = 'Protocols_download') -> None:
    """Checks the arguments validity, starts the broker and connects to it.

    Args:
      port: The network port the broker should listen to.
      address: The network address of the broker.
      topic_in: The topic for receiving commands from clients.
      topic_out: The topic for sending messages to the clients.
      topic_protocol_in: The topic for receiving protocols from the clients.
      topic_protocol_out: The topic for sending protocols to the clients.
    """

    if not isinstance(port, int):
      raise TypeError("port should be an integer")
    if not isinstance(topic_in, str):
      raise TypeError("topic_in should be a string")
    if not isinstance(topic_out, str):
      raise TypeError("topic_out should be a string")
    if not isinstance(topic_protocol_in, str):
      raise TypeError("topic_protocol_in should be a string")
    if not isinstance(topic_protocol_out, str):
      raise TypeError("topic_protocol_out should be a string")

    # Setting the topics and the queue
    self._topic_in = topic_in
    self._topic_out = topic_out
    self._topic_protocol_in = topic_protocol_in
    self._topic_protocol_out = topic_protocol_out
    self._message_queue = Queue()
    self._protocol_queue = Queue()

    # Setting the mqtt client
    self._client = mqtt.Client(str(time.time()))
    self._client.on_connect = self._on_connect
    self._client.on_message = self._on_message
    self._client.reconnect_delay_set(max_delay=10)

    # Setting the flags
    self._protocol = None
    self._is_protocol_active = False
    self._last_return_code = None

    # Starting the mosquitto broker
    self._launch_mosquitto(port)
    time.sleep(5)

    # Loop for ensuring the connection to the broker is well established
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
    """Starts the protocol manager, ad manages the exit of the program.

    When exiting stops any running protocol and then stops the broker.
    """

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
    """Starts the mosquitto broker in a separate process.

    Args:
      port: The network port over which the broker communicates.
    """

    try:
      self._mosquitto = Popen(['mosquitto', '-p', str(port)])
    except FileNotFoundError:
      raise

  def _on_message(self, client, userdata, message) -> None:
    """Callback executed upon reception of a message from the clients.

    Simply puts the message in a queue.
    """

    try:
      if message.topic == self._topic_in:
        self._message_queue.put_nowait(loads(message.payload))
      elif message.topic == self._topic_protocol_in:
        self._protocol_queue.put_nowait(loads(message.payload))
    except UnpicklingError:
      self._publish("Warning ! Message raised UnpicklingError, ignoring it")
    print("Got message")

  def _on_connect(self, client, userdata, flags, rc) -> None:
    """Callback executed when connecting to the broker.

    Simply subscribes to the topic.
    """

    self._client.subscribe(topic=self._topic_in, qos=2)
    self._client.subscribe(topic=self._topic_protocol_in, qos=2)
    print("Subscribed")
    self._client.loop_start()

  def _publish(self, message: str) -> None:
    """Wrapper for sending messages to the clients.

    Args:
      message: The message to send to the clients.
    """

    self._client.publish(topic=self._topic_out,
                         payload=dumps(message),
                         qos=2)

  def _protocol_manager(self) -> None:
    """Method handling commands from the client.

    It calls the right method according to the command received. Can also stop
    the server if asked to, and automatically detects if the protocol has
    stopped.
    """

    while True:
      # Checking if the protocol is still running
      if self._is_protocol_active:
        if self._protocol.poll() is not None:
          self._is_protocol_active = False
          self._last_return_code = self._protocol.poll()

      # Getting the command message and executing the associated action
      if not self._message_queue.empty():
        try:
          message = self._message_queue.get_nowait()
        except Empty:
          message = None

        if message == "Print status":
          print("Print status")
          self._protocol_status()

        elif "Upload protocol" in message:
          print("Save protocol")
          self._save_protocol(message.replace("Upload protocol ", ""))

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
    """Sends the protocol status to the clients."""

    if self._is_protocol_active:
      self._publish("Protocol running")
    elif self._last_return_code == 0:
      self._publish("Protocol terminated gracefully")
    elif self._last_return_code is not None:
      self._publish("Protocol terminated with an error")
    else:
      self._publish("No protocol started yet")

  def _save_protocol(self, name: str) -> None:
    try:
      protocol = self._protocol_queue.get(timeout=5)

      path = dirname(abspath(__file__))
      path = path.replace("/Server", "")
      if not exists(path + "/Protocols/"):
        mkdir(path + "/Protocols/")
        with open(path + "/Protocols/" + "__init__.py", 'w') as init_file:
          init_file.write("# coding: utf-8" + "\n")
          init_file.write("\n")
          init_file.write("from .Protocol_" + name + " import Led, Mecha, Elec"
                          + "\n")

      with open(path + "/Protocols/Protocol_" + name + ".py", 'w') as \
           protocol_file:
        for line in protocol:
          protocol_file.write(line)
      self._publish("Protocol successfully uploaded")
    except Empty:
      self._publish("Error ! No protocol received")

  def _write_protocol(self):
    from ..Protocols import Led, Mecha, Elec
    path = dirname(abspath(__file__)).replace("/Remote_control/Server", "")
    with open(path + "/Protocol.py", 'w') as executable_file:
      executable_file.write('# coding: utf-8' + "\n")
      executable_file.write("\n")

      executable_file.write("Led = [" + "\n")
      for dic in Led:
        executable_file.write(str(dic) + "," + "\n")
      executable_file.write("]" + "\n")

      executable_file.write("Mecha = [" + "\n")
      for dic in Mecha:
        executable_file.write(str(dic) + "," + "\n")
      executable_file.write("]" + "\n")

      executable_file.write("Elec = [" + "\n")
      for dic in Elec:
        executable_file.write(str(dic) + "," + "\n")
      executable_file.write("]" + "\n")

      with open(path + "/Remote_control/Server/_Protocol_template.py", 'r') \
           as template:
        for line in template:
          if "#" not in line:
            executable_file.write(line)

  def _start_protocol(self) -> None:
    """Starts a new protocol, if no other protocol is currently running.

    Also checks after a few seconds if the protocol indeed started or if it
    just crashed.
    """

    if not self._is_protocol_active:
      self._write_protocol()
      self._protocol = Popen(['python3', 'Protocol.py'])
      try:
        self._protocol.wait(5)
        try:
          self._protocol.wait(5)
          self._publish("Error ! Protocol crashed at starting")
        except TimeoutExpired:
          self._is_protocol_active = True
          self._publish("Protocol started")
      except TimeoutExpired:
        self._is_protocol_active = True
        self._publish("Protocol started")
    else:
      self._publish("Protocol already running, stop it before starting new "
                    "one")

  def _stop_protocol(self) -> int:
    """Stops the protocol, if one is currently running.

    It sends a SIGINT to the protocol, raising a :exc:`KeyboardInterrupt` in
    its Python code. Sends a message to the client indicating whether the
    protocol was successfully stopped or not.

    Returns:
      `1` if the protocol couldn't be stopped, else `0`.
    """

    if not self._is_protocol_active:
      print("No protocol currently running !")
      self._publish("No protocol currently running !")
    else:
      # Trying to get the protocol to stop itself
      self._protocol.send_signal(SIGINT)
      try:
        self._last_return_code = self._protocol.wait(10)
      except TimeoutExpired:
        try:
          # If not successful, asking the process to stop
          self._protocol.terminate()
          self._last_return_code = self._protocol.wait(10)
        except TimeoutExpired:
          # If still not successful, abruptly killing the process
          self._protocol.kill()
          self._last_return_code = self._protocol.wait(10)

      # Sending the results to the clients
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
