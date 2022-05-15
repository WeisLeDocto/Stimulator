# coding: utf-8

from socket import timeout, gaierror
from paho.mqtt.client import Client
from queue import Queue, Empty
from pickle import loads, dumps, UnpicklingError
from time import time, sleep
from subprocess import Popen, TimeoutExpired, check_output
from pathlib import Path
from signal import SIGINT
from psutil import Process, AccessDenied
from sys import path
from importlib import reload
from re import compile

from ..__paths__ import base_path, protocols_path
from ..Tools import get_protocol_name

# Preparing the import of the Protocols module
path.append(str(base_path.parent))

# Creating the module if it does not already exist
if not Path.exists(protocols_path) or not Path.exists(
      protocols_path / "__init__.py"):

  # First create the folder
  Path.mkdir(protocols_path, exist_ok=True)

  # Then create the __init__.py file
  with open(protocols_path / "__init__.py", 'w') as init_file:
    init_file.write("# coding: utf-8\n")

# Finally, importing the module
import Protocols

msg_templates = {"Return list": compile(r'Return\sprotocol\slist'),
                 "Print status": compile(r'Print\sstatus'),
                 "Upload protocol": compile(r'Upload\sprotocol\s'
                                            r'(?P<name>\S+)\s(?P<p_word>.+)'),
                 "Download protocol": compile(r'Download\sprotocol\s'
                                              r'(?P<name>.+)'),
                 "Start protocol": compile(r'Start\sprotocol\s(?P<name>.+)'),
                 "Stop protocol": compile(r'Stop\sprotocol'),
                 "Stop server": compile(r'Stop\sserver')}


class DaemonStop(Exception):
  """Exception raised for stopping the daemon thread."""


class Daemon_run:
  """A class for managing the stimulation protocols.

  It allows to start and stop the protocols safely as a separate process. Can
  also return the status of the protocol, receive uploaded protocols from the
  clients, send downloaded protocols to the clients, and send the clients a list
  of available protocols.
  """

  def __init__(self,
               port: int,
               manage_broker: bool,
               address: str = 'localhost',
               topic_in: str = 'Remote_control',
               topic_out: str = 'Server_status',
               topic_protocol_in: str = 'Protocols_upload',
               topic_protocol_out: str = 'Protocols_download',
               topic_protocol_list: str = 'Protocols_list') -> None:
    """Checks the arguments validity, starts the broker and connects to it.

    Args:
      port: The network port the broker should listen to.
      manage_broker: If :obj:`True`, starts the Mosquitto Broker.
      address: The network address of the broker.
      topic_in: The topic for receiving commands from clients.
      topic_out: The topic for sending messages to the clients.
      topic_protocol_in: The topic for receiving protocols from the clients.
      topic_protocol_out: The topic for sending protocols to the clients.
      topic_protocol_list: The topic for sending the list of available
        protocols.
    """

    if not isinstance(port, int):
      raise TypeError("port should be an integer")
    if not isinstance(manage_broker, bool):
      raise TypeError("broker should be a bool")
    if not isinstance(topic_in, str):
      raise TypeError("topic_in should be a string")
    if not isinstance(topic_out, str):
      raise TypeError("topic_out should be a string")
    if not isinstance(topic_protocol_in, str):
      raise TypeError("topic_protocol_in should be a string")
    if not isinstance(topic_protocol_out, str):
      raise TypeError("topic_protocol_out should be a string")
    if not isinstance(topic_protocol_list, str):
      raise TypeError("topic_protocol_list should be a string")

    self._manage_broker = manage_broker

    # Setting the MQTT topics
    self._topic_in = topic_in
    self._topic_out = topic_out
    self._topic_protocol_in = topic_protocol_in
    self._topic_protocol_out = topic_protocol_out
    self._topic_protocol_list = topic_protocol_list

    self._msg_to_meth = {'Return list': self._send_protocol_list,
                         'Print status': self._send_protocol_status,
                         'Upload protocol': self._save_protocol,
                         'Download protocol': self._send_protocol,
                         'Start protocol': self._start_protocol,
                         'Stop protocol': self._stop_protocol,
                         'Stop server': self._stop_server}

    # Queues for receiving commands
    self._message_queue = Queue()
    self._protocol_queue = Queue()

    # Setting the MQTT client
    self._client = Client(str(time()))
    self._client.on_connect = self._on_connect
    self._client.on_message = self._on_message
    self._client.reconnect_delay_set(max_delay=10)

    # Protocol-related attributes
    self._protocol_path = base_path.parent / "Protocol.py"
    self._protocol = None

    # Starting the mosquitto broker if required
    if self._manage_broker:
      self._launch_mosquitto(port)
      sleep(5)

    # Loop for ensuring the connection to the broker is well established
    try_count = 15
    while True:
      try:
        self._client.connect(host=address, port=port, keepalive=10)
        break
      except timeout:
        raise
      except gaierror:
        raise
      except ConnectionRefusedError:
        try_count -= 1
        if try_count == 0:
          raise
        sleep(1)

    self._client.loop_start()

  def __call__(self) -> None:
    """Starts the protocol manager, and manages the exit of the program.

    When exiting stops any running protocol and then stops the broker.
    """

    # Runs the main loop
    try:
      self._protocol_manager()

    # Tells the clients that the sever is stopping
    except DaemonStop:
      self._publish("Stopping the server and the MQTT broker")
      # Allowing time for the broker to send the exit message
      sleep(1)

    finally:
      # Stopping the client loop
      self._client.loop_stop()
      self._client.disconnect()

      # If we started the broker process, terminating it
      if self._manage_broker:
        try:
          self._mosquitto.terminate()
          self._mosquitto.wait(timeout=15)
        except TimeoutExpired:
          self._mosquitto.kill()

      # Also try to terminate it anyway if we didn't start it
      else:
        pid_list = map(int, check_output(['pidof', 'mosquitto']).split())
        for pid in pid_list:
          process = Process(pid)
          try:
            process.send_signal(SIGINT)
          except AccessDenied:
            pass

  def _launch_mosquitto(self, port: int) -> None:
    """Starts the mosquitto broker in a separate process.

    Args:
      port: The network port over which the broker communicates.
    """

    try:
      self._mosquitto = Popen(['mosquitto', '-p', str(port)])
    except FileNotFoundError:
      raise

  def _on_message(self, _, __, message) -> None:
    """Callback executed upon reception of a message from the clients.

    Simply puts the message in a queue.
    """

    try:
      # Topic for regular communication
      if message.topic == self._topic_in:
        self._message_queue.put_nowait(loads(message.payload))
      # Topic for receiving protocol files
      elif message.topic == self._topic_protocol_in:
        self._protocol_queue.put_nowait(loads(message.payload))

    # Happens if the received message was not pickled
    except UnpicklingError:
      self._publish("Warning ! Message raised UnpicklingError, ignoring it")

  def _on_connect(self, *_, **__) -> None:
    """Callback executed when connecting to the broker.

    Simply subscribes to the topic.
    """

    self._client.subscribe(topic=self._topic_in, qos=2)
    self._client.subscribe(topic=self._topic_protocol_in, qos=2)
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

    is_active = False
    while True:

      # If the protocol ended, tell the clients
      if is_active and not self._is_protocol_active:
        is_active = False

        # Sending the results to the clients
        if self._protocol.poll() == 0:
          self._publish("Protocol terminated gracefully")
        else:
          self._publish("Protocol terminated with an error")

      # Check if the protocol started during the last loop
      elif self._is_protocol_active and not is_active:
        is_active = True

      # Getting the command message and executing the associated action
      if not self._message_queue.empty():
        try:
          message = self._message_queue.get_nowait()
        except Empty:
          continue

        # Handling the incoming message
        matched = False
        for msg, method in self._msg_to_meth.items():
          # Parsing the message to know which action to perform and get the args
          match = msg_templates[msg].fullmatch(message)
          if match is not None:
            # Calling the right method with the right args
            method(**match.groupdict())
            matched = True
            break

        # In case the message has an unknown syntax, tell the client
        if not matched:
          self._publish("Error ! Invalid command message")

      sleep(1)

  def _send_protocol_status(self) -> None:
    """Sends the protocol status to the clients."""

    if self._protocol is None:
      self._publish("No protocol started yet")

    elif self._is_protocol_active:
      self._publish("Protocol running")

    elif self._protocol.poll() == 0:
      self._publish("Last protocol terminated gracefully")

    else:
      self._publish("Last protocol terminated with an error")

  def _send_protocol_list(self) -> None:
    """Sends the clients the list of protocols in the Protocols/ folder"""

    try:
      # Getting the list of files in the Protocols folder
      protocol_list = Path.iterdir(protocols_path)

      # Keeping only the name of the files that are actually protocols
      protocols = [get_protocol_name(protocol) for protocol in protocol_list if
                   get_protocol_name(protocol) is not None]

    # In case the Protocols modules does not exist
    except FileNotFoundError:
      protocols = []

    # Sending the list to the clients
    self._client.publish(topic=self._topic_protocol_list,
                         payload=dumps(protocols),
                         qos=2)
    self._publish("Received list of protocols")

  def _send_protocol(self, name: str) -> None:
    """Sends the clients a protocol from the Protocols/ folder.

    It is transferred as a :obj:`list`, each element being a :obj:`str` of a
    line in the corresponding `.py`  file.

    Args:
      name: The name of the protocol to send.
    """

    # Getting the protocol as text
    with open(protocols_path / f"Protocol_{name}.py", 'r') as protocol_file:
      protocol = list(protocol_file)

    # Sending it
    if self._client.publish(topic=self._topic_protocol_out,
                            payload=dumps(protocol),
                            qos=2).is_published():
      self._publish("Protocol successfully downloaded")

    # Checking it was successfully sent
    else:
      self._publish("Error ! Protocol not properly sent")

  def _save_protocol(self, name: str, p_word: str) -> None:
    """Saves a protocol uploaded by a client in the Protocols/ folder.

    The protocol is received as a :obj:`list` of :obj:`str`, representing each a
    line o the `.py` document.

    Args:
      name: The name of the protocol to write.
      p_word: A password the user has to provide in order to write to the
        server.
    """

    # Checking that the password given is correct
    with open(base_path / "password.txt", 'r') as password_file:
      password = password_file.read()
    if p_word != password:
      self._publish("Error ! Wrong password")
      return

    try:
      # Getting the protocol from the client
      protocol = self._protocol_queue.get(timeout=5)

      # Writing it in the local Protocols module
      with open(protocols_path / f"Protocol_{name}.py", 'w') as protocol_file:
        for line in protocol:
          protocol_file.write(line)

      # Telling the client it was successful
      self._publish("Protocol successfully uploaded")

    # Case when the client didn't send a protocol
    except Empty:
      self._publish("Error ! No protocol received")

  @ staticmethod
  def _choose_protocol(protocol: str) -> None:
    """Chooses the right protocol to start.

    Overwrites the ``__init__.py`` file in the Protocols/ folder so that the
    generator lists are imported from the right files.

    Args:
      protocol: The name of the protocol to choose.
    """

    with open(protocols_path / "__init__.py", 'w') as init:
      init.write("# coding: utf-8" + "\n\n")
      init.write(f"from .Protocol_{protocol} import Led, Mecha, Elec\n")

  def _write_protocol(self):
    """Writes the ``Protocol.py`` file using the generator lists and the
    ``_Protocol_template.py`` file."""

    reload(Protocols)
    from Protocols import Led, Mecha, Elec

    with open(self._protocol_path, 'w') as executable_file:
      executable_file.write("# coding: utf-8\n\n")

      executable_file.write("Led = [\n")
      for dic in Led:
        executable_file.write(f"{dic},\n")
      executable_file.write("]" + "\n")

      executable_file.write("Mecha = [\n")
      for dic in Mecha:
        executable_file.write(f"{dic},\n")
      executable_file.write("]\n")

      executable_file.write("Elec = [\n")
      for dic in Elec:
        executable_file.write(f"{dic},\n")
      executable_file.write("]\n")

      with open(base_path / "Server" / "_Protocol_template.py",
                'r') as template:
        for line in template:
          if "#" not in line:
            executable_file.write(line)

  def _start_protocol(self, name: str) -> None:
    """Starts a new protocol, if no other protocol is currently running.

    first writes a few files in  order for the right protocol to run. Also
    checks after a few seconds if the protocol indeed started or if it just
    crashed.

    Args:
      name: The protocol to start.
    """

    if not self._is_protocol_active:
      # Rewrites the __init__.py file of the Protocols module
      self._choose_protocol(name)
      # Rewrites the Protocol.py file
      self._write_protocol()
      # Starts the process
      self._protocol = Popen(['python3', self._protocol_path])

      # Makes sure the protocol has started
      try:
        self._protocol.wait(5)
        try:
          self._protocol.wait(5)
          self._publish("Error ! Protocol crashed at starting")
        except TimeoutExpired:
          self._publish("Protocol started")
      except TimeoutExpired:
        self._publish("Protocol started")

    # A protocol is already running
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
      self._publish("No protocol currently running !")

    else:
      # Trying to get the protocol to stop itself
      self._protocol.send_signal(SIGINT)
      # Check if the protocol actually stopped
      try:
        self._protocol.wait(10)

      except TimeoutExpired:
        try:
          # The protocol didn't stop after 10 seconds, trying to terminate it
          self._protocol.terminate()
          self._protocol.wait(10)

        except TimeoutExpired:
          # The protocol still didn't stop, killing it
          self._protocol.kill()
          self._protocol.wait(10)

      # Sending the logs to the clients
      if self._protocol.poll() is None:
        self._publish("Error ! Could not stop the protocol")
        return 1

      elif self._protocol.poll() == 0:
        self._publish("Protocol terminated gracefully")

      else:
        self._publish("Protocol terminated with an error")

    return 0

  def _stop_server(self) -> None:
    """"""

    if self._is_protocol_active:
      if self._stop_protocol():
        self._publish("Error ! Could not stop the current protocol, "
                      "server not stopped")
        return
    raise DaemonStop

  @property
  def _is_protocol_active(self) -> bool:
    """Returns True is there is currently an active protocol running."""

    return self._protocol is not None and self._protocol.poll() is None
