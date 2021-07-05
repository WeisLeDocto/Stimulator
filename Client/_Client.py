# coding: utf-8

# TODO:
# Password for connecting to the broker
# One or two servers ?
# Limit display to a certain amount of information
# Split the files and reorganize them
# Make protocol transferable in Python
# Test for protocol consistency
# Possibility to choose among several protocols
# Possibility to choose which protocol to write
# Possibility to name the protocols
# Possibility to download the protocols and see what they look like
# Interface for building protocols ?

# Multi-protocol management:
# On connect, the client asks for the available protocols and the servers sends
# The client stores the list of available protocols
# When uploading a protocol, it actually sends a dict
# The server writes it in a file according to the name
# The client asks again for the list of available protocols
# The client can ask the server to send the dict of a given protocol
# The client can plot the locally available protocols from the interface

# The program that builds a protocol actually just writes the dict in a file
# Possibility to visualize the protocol before writing it

import time
import paho.mqtt.client as mqtt
from queue import Queue
import socket
from pickle import loads, dumps, UnpicklingError
from ast import literal_eval

import sys
from PyQt5.QtWidgets import QApplication
from _Graphical_interface import Graphical_interface


class Client_loop:
  """Class managing the connection to the server, i.e. sending commands and
  receiving data."""

  def __init__(self,
               port: int,
               address: str = 'localhost',
               topic_out: str = 'Remote_control',
               topic_in: str = 'Server_status',
               topic_data: tuple = ('t', 'pos'),
               topic_is_busy: tuple = ('busy',)) -> None:
    """Checks the arguments validity, sets the server callbacks.

    Args:
      port: The server port to use.
      address: The server network address.
      topic_out: The topic for sending commands to the server.
      topic_in: The topic for receiving messages from the server.
      topic_data: The topic for receiving data from the server.
      topic_is_busy: The topic for receiving the business status of the server.
    """

    if not isinstance(port, int):
      raise TypeError("port should be an integer")
    self._port = port
    if not isinstance(address, str):
      raise TypeError("address should be an string")
    self._address = address
    if not isinstance(topic_in, str):
      raise TypeError("topic_in should be a string")
    if not isinstance(topic_out, str):
      raise TypeError("topic_out should be a string")
    if not isinstance(topic_data, tuple):
      raise TypeError("topic_data should be a tuple")
    if not isinstance(topic_is_busy, tuple):
      raise TypeError("topic_is_busy should be a tuple")

    # Setting the topics and the queues
    self._topic_in = topic_in
    self._topic_out = topic_out
    self._topic_is_busy = topic_is_busy
    self._topic_data = topic_data
    self.answer_queue = Queue()
    self.data_queue = Queue()
    self.is_busy_queue = Queue()

    # Setting the mqtt client
    self._client = mqtt.Client(str(time.time()))
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
      self.app = QApplication(sys.argv)
      Graphical_interface(self)()
      sys.exit(self.app.exec_())
    finally:
      self._client.loop_stop()
      self._client.disconnect()

  def publish(self, message: str) -> None:
    """Wrapper for sending commands to the server.

    Args:
      message: The command to send.
    """

    return self._client.publish(topic=self._topic_out,
                                payload=dumps(message),
                                qos=2)[0]

  def _on_message(self, client, userdata, message) -> None:
    """Callback executed upon reception of a message or data from the
    server.

    The message or data is put in a queue, waiting to be processed by the
    graphical interface.
    """

    try:
      # If the message contains data
      if literal_eval(message.topic) == self._topic_data:
        self.data_queue.put_nowait(loads(message.payload))
      elif literal_eval(message.topic) == self._topic_is_busy:
        self.is_busy_queue.put_nowait(loads(message.payload))
    except ValueError:
      # If the message contains text
      self.answer_queue.put_nowait(loads(message.payload))
      print("Got message" + " : " + loads(message.payload))
    except UnpicklingError:
      # If the message hasn't been pickled before sending
      print("Warning ! Message raised UnpicklingError, ignoring it")

  def _on_connect(self, client, userdata, flags, rc) -> None:
    """Callback executed when connecting to the server.

    Simply subscribes to all the necessary topics.
    """

    self._client.subscribe(topic=self._topic_in, qos=2)
    self._client.subscribe(topic=str(self._topic_data), qos=0)
    self._client.subscribe(topic=str(self._topic_is_busy), qos=2)
    print("Subscribed")
    self.is_connected = True
    self._client.loop_start()

  def _on_disconnect(self, client, userdata, rc) -> None:
    """Sets the :attr:`is_connected` flag to :obj:`False`."""

    self.is_connected = False

  def connect_to_broker(self) -> str:
    """Simply connects to the server.

    Manages the different connection issues that could occur.

    Returns:
      A text message to be displayed to the user in case connection failed.
    """

    # Connecting to the broker
    try:
      if self._connected_once:
        self._client.reconnect()
      else:
        self._client.connect(host=self._address, port=self._port, keepalive=10)
      self.is_connected = True
      self._connected_once = True
    except socket.timeout:
      print("Impossible to reach the given address, aborting")
      self.is_connected = False
      return "Address unreachable"
    except socket.gaierror:
      print("Invalid address given, please check the spelling")
      self.is_connected = False
      return "Address invalid"
    except ConnectionRefusedError:
      print("Connection refused, the broker may not be running or you may "
            "not have the rights to connect")
      self.is_connected = False
      return "Server not running"

    self._client.loop_start()
    return ""
