# coding: utf-8

from time import time
from paho.mqtt.client import Client
from queue import Queue
from socket import timeout, gaierror
from pickle import loads, dumps, UnpicklingError
from ast import literal_eval
from typing import Tuple, List, AnyStr

from sys import argv, exit
from PyQt5.QtWidgets import QApplication
from ._Graphical_interface import Graphical_interface


class Client_loop:
  """Class managing the connection to the server, i.e. sending commands and
  receiving data."""

  def __init__(self,
               port: int,
               topic_out: str = 'Remote_control',
               topic_in: str = 'Server_status',
               topic_data: Tuple[str, ...] = ('t', 'pos'),
               topic_is_busy: Tuple[str, ...] = ('busy',),
               topic_protocol_out: str = 'Protocols_upload',
               topic_protocol_in: str = 'Protocols_download',
               topic_protocol_list: str = 'Protocols_list') -> None:
    """Checks the arguments validity, sets the server callbacks.

    Args:
      port: The server port to use.
      topic_out: The topic for sending commands to the server.
      topic_in: The topic for receiving messages from the server.
      topic_data: The topic for receiving data from the server.
      topic_is_busy: The topic for receiving the business status of the server.
      topic_protocol_out: The topic for uploading protocols to the server.
      topic_protocol_in: The topic for downloading protocols from the server.
      topic_protocol_list: The topic for receiving list of available protocols
        from the server.
    """

    if not isinstance(port, int):
      raise TypeError("port should be an integer")
    self._port = port
    if not isinstance(topic_in, str):
      raise TypeError("topic_in should be a string")
    if not isinstance(topic_out, str):
      raise TypeError("topic_out should be a string")
    if not isinstance(topic_data, tuple):
      raise TypeError("topic_data should be a tuple")
    if not isinstance(topic_is_busy, tuple):
      raise TypeError("topic_is_busy should be a tuple")
    if not isinstance(topic_protocol_in, str):
      raise TypeError("topic_protocol_in should be a string")
    if not isinstance(topic_protocol_out, str):
      raise TypeError("topic_protocol_out should be a string")
    if not isinstance(topic_protocol_list, str):
      raise TypeError("topic_protocol_list should be a string")

    # Creating the queues for receiving data
    self.answer_queue = Queue()
    self.data_queue = Queue()
    self.is_busy_queue = Queue()
    self.protocol_queue = Queue()
    self.protocol_list_queue = Queue()

    # Setting the topics
    self._topic_out = topic_out
    self._topic_data = topic_data
    self._topic_protocol_out = topic_protocol_out
    self._all_topics_in = {topic_in: self.answer_queue,
                           topic_is_busy: self.is_busy_queue,
                           topic_data: self.data_queue,
                           topic_protocol_in: self.protocol_queue,
                           topic_protocol_list: self.protocol_list_queue}

    # Setting the mqtt client
    self._client = Client(str(time()))
    self._client.on_connect = self._on_connect
    self._client.on_message = self._on_message
    self._client.on_disconnect = self._on_disconnect
    self._client.reconnect_delay_set(max_delay=10)

    # Setting the flags
    self.is_connected = False
    self._connected_once = False

  def __call__(self) -> None:
    """Simply displays the interface window, and disconnects from the server
    at exit."""

    try:
      self.app = QApplication(argv)
      Graphical_interface(self)()
      exit(self.app.exec_())
    finally:
      self._client.loop_stop()
      self._client.disconnect()

  def publish(self, message: str) -> int:
    """Wrapper for sending commands to the server.

    Args:
      message: The command to send.
    """

    return self._client.publish(topic=self._topic_out,
                                payload=dumps(message),
                                qos=2)[0]

  def upload_protocol(self, protocol: List[AnyStr]) -> int:
    """"""

    return self._client.publish(topic=self._topic_protocol_out,
                                payload=dumps(protocol),
                                qos=2)[0]

  def connect_to_broker(self, address: str) -> str:
    """Simply connects to the server.

    Manages the different connection issues that could occur.

    Args:
      address: The address to connect to.

    Returns:
      A text message to be displayed to the user in case connection failed.
    """

    try:
      if self._connected_once:
        # Reconnecting to the broker
        self._client.reconnect()
      else:
        # Connecting to the broker for the first time
        self._client.connect(host=address, port=self._port, keepalive=10)
      self.is_connected = True
      self._connected_once = True

    # The server took too long to reply
    except timeout:
      self.is_connected = False
      return "Address unreachable"

    # Couldn't get address info
    except gaierror:
      self.is_connected = False
      return "Address invalid"

    # The connection was refused
    except ConnectionRefusedError:
      self.is_connected = False
      return "Server not running or not allowed to connect"

    self._client.loop_start()
    return ""

  def _on_message(self, _, __, message) -> None:
    """Callback executed upon reception of a message or data from the
    server.

    The message or data is put in a queue, waiting to be processed by the
    graphical interface.
    """

    try:
      # Getting the topic as string or a tuple
      try:
        topic = literal_eval(message.topic)
      except ValueError:
        topic = message.topic

      # Putting the message in the right queue
      try:
        self._all_topics_in[topic].put_nowait(loads(message.payload))
      except KeyError:
        pass

    # The message hasn't been pickled before sending
    except UnpicklingError:
      pass

  def _on_connect(self, *_, **__) -> None:
    """Callback executed when connecting to the server.

    Simply subscribes to all the necessary topics.
    """

    # Subscribing to all the topics
    for topic in self._all_topics_in:
      self._client.subscribe(topic=str(topic),
                             qos=0 if topic == self._topic_data else 2)

    # Starting the loop
    self.is_connected = True
    self._client.loop_start()

  def _on_disconnect(self, *_, **__) -> None:
    """Sets the :attr:`is_connected` flag to :obj:`False`."""

    self.is_connected = False
