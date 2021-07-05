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
from queue import Queue, Empty
import socket
from pickle import loads, dumps, UnpicklingError
from ast import literal_eval

import sys
from functools import partial
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QStyle
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtCore import QThread
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QSize

from pyqtgraph import PlotWidget
from pyqtgraph import mkPen
from pyqtgraph import AxisItem


class Timer(QObject):
  """Object that is actually living in the separate thread for updating the
  display."""

  def __init__(self, gui, delay) -> None:
    """Initializes the parent class and sets the flags.

    Args:
      gui: The main window object that will be updated by the thread.
      delay: The time between two display updates in seconds.
    """

    super().__init__()
    self._gui = gui
    self._stop = False
    self._delay = delay

  def run(self) -> None:
    """Runs an infinite loop for refreshing the display."""

    while not self._stop:
      self._gui.gui_loop()
      time.sleep(self._delay)

  def stop(self) -> None:
    """Sets the :attr:`_stop` flag to :obj:`False`."""
    self._stop = True


class Graphical_interface(QMainWindow):
  """Class for building and displaying the graphical user interface."""

  def __init__(self, loop) -> None:
    """Initializes the main window and sets the flags.

    Args:
      loop: The Client_loop instance used to communicate with the server.
    """

    super().__init__()
    self._loop = loop
    self._waiting_for_answer = False
    self._answer_timer = 0
    self._busy = None
    self._stopped = False

  def __call__(self) -> None:
    """Creates and displays the interface."""

    self._set_layout()

    self._display_if_connected(self._loop.is_connected)
    self._disable_if_connected(self._loop.is_connected)

    self._set_connections()

    self._x_data = []
    self._y_data = []
    self._curve = self._graph.plot(self._x_data, self._y_data, pen=mkPen('k'))

    delta_x = int((self._loop.app.desktop().availableGeometry().width() -
                  self.width()) / 2)
    delta_y = int((self._loop.app.desktop().availableGeometry().height() -
                  self.height()) / 2)
    self.move(delta_x, delta_y)
    self.show()

    self._start_thread()

  def _set_layout(self) -> None:
    """Creates the widgets and places them in the main window."""

    self.setWindowTitle('Stimulator Interface')

    # General layout
    self.setGeometry(550, 150, 300, 650)
    self._generalLayout = QVBoxLayout()
    self._centralWidget = QWidget(self)
    self.setCentralWidget(self._centralWidget)
    self._centralWidget.setLayout(self._generalLayout)

    # Buttons and labels for managing the connection to the server
    self._connect_button = QPushButton("Connect to stimulator")
    self._generalLayout.addWidget(self._connect_button)
    self._connect_button.setIcon(self.style().standardIcon(
      QStyle.SP_CommandLink))
    self._connect_button.setIconSize(QSize(12, 12))

    self._is_connected_display = QLabel("")
    self._generalLayout.addWidget(self._is_connected_display)

    self._connection_status_display = QLabel("")
    self._generalLayout.addWidget(self._connection_status_display)

    # Buttons for managing protocols
    self._upload_protocol_button = QPushButton("Upload protocol")
    self._generalLayout.addWidget(self._upload_protocol_button)
    self._upload_protocol_button.setIcon(self.style().standardIcon(
      QStyle.SP_FileDialogToParent))
    self._upload_protocol_button.setIconSize(QSize(12, 12))

    self._download_protocol_button = QPushButton("Download protocol")
    self._generalLayout.addWidget(self._download_protocol_button)
    self._download_protocol_button.setIcon(self.style().standardIcon(
      QStyle.SP_ArrowDown))
    self._download_protocol_button.setIconSize(QSize(12, 12))

    self._protocol_status_display = QLabel("")
    self._generalLayout.addWidget(self._protocol_status_display)

    # Buttons and labels for managing commands to the server
    self._status_button = QPushButton("Print status")
    self._generalLayout.addWidget(self._status_button)
    self._status_button.setIcon(self.style().standardIcon(
      QStyle.SP_MessageBoxInformation))
    self._status_button.setIconSize(QSize(12, 12))

    self._start_protocol_button = QPushButton("Start protocol")
    self._generalLayout.addWidget(self._start_protocol_button)
    self._start_protocol_button.setIcon(self.style().standardIcon(
      QStyle.SP_MediaPlay))
    self._start_protocol_button.setIconSize(QSize(12, 12))

    self._stop_protocol_button = QPushButton("Stop protocol")
    self._generalLayout.addWidget(self._stop_protocol_button)
    self._stop_protocol_button.setIcon(self.style().standardIcon(
      QStyle.SP_MediaStop))
    self._stop_protocol_button.setIconSize(QSize(12, 12))

    self._stop_server_button = QPushButton("Stop server")
    self._generalLayout.addWidget(self._stop_server_button)
    self._stop_server_button.setIcon(self.style().standardIcon(
      QStyle.SP_BrowserStop))
    self._stop_server_button.setIconSize(QSize(12, 12))

    # Graphs
    self._status_display = QLabel("")
    self._generalLayout.addWidget(self._status_display)

    self._x_axis = AxisItem(orientation='bottom', pen=mkPen('k'),
                            textPen=mkPen('k'))
    self._y_axis = AxisItem(orientation='left', pen=mkPen('k'),
                            textPen=mkPen('k'))
    self._graph = PlotWidget(parent=self._centralWidget, background=None,
                             axisItems={'bottom': self._x_axis,
                                        'left': self._y_axis},
                             labels={'bottom': 't(s)',
                                     'left': 'position (mm)'},
                             title='Movable pin position')
    self._generalLayout.addWidget(self._graph)

    self._is_busy_header = QLabel("Stimulator busy :")
    self._generalLayout.addWidget(self._is_busy_header)

    self._is_busy_status_display = QLabel("")
    self._generalLayout.addWidget(self._is_busy_status_display)

  def _set_connections(self) -> None:
    """Sets the actions to perform when interacting with the widgets."""

    self._connect_button.clicked.connect(self._try_connect)

    self._upload_protocol_button.clicked.connect(
      partial(self._send_server, self._upload_protocol_button.text()))

    self._download_protocol_button.clicked.connect(
      partial(self._send_server, self._download_protocol_button.text()))

    self._status_button.clicked.connect(
      partial(self._send_server, self._status_button.text()))

    self._start_protocol_button.clicked.connect(
      partial(self._send_server, self._start_protocol_button.text()))

    self._stop_protocol_button.clicked.connect(
      partial(self._send_server, self._stop_protocol_button.text()))

    self._stop_server_button.clicked.connect(
      partial(self._send_server, self._stop_server_button.text()))

  def _display_if_connected(self, bool_: bool) -> None:
    """Displays the connection status.

    Args:
      bool_: :obj:`True` if connected to the server, else :obj:`False`.
    """

    if bool_:
      self._is_connected_display.setText("Connected")
      self._connection_status_display.setText("")
      self._is_connected_display.setStyleSheet("color: black;")
    else:
      self._is_connected_display.setText("Not connected")
      self._is_connected_display.setStyleSheet("color: red;")

  def _disable_if_connected(self, bool_: bool) -> None:
    """Disables the interaction buttons when not connected to the client.

    Args:
      bool_: :obj:`True` if connected to the server, else :obj:`False`.
    """

    self._connect_button.setEnabled(not bool_)
    self._upload_protocol_button.setEnabled(bool_)
    self._download_protocol_button.setEnabled(bool_)
    self._status_button.setEnabled(bool_)
    self._start_protocol_button.setEnabled(bool_)
    self._stop_protocol_button.setEnabled(bool_)
    self._stop_server_button.setEnabled(bool_)
    self._is_busy_header.setEnabled(bool_)
    self._is_busy_status_display.setEnabled(bool_)

  def _disable_if_waiting(self) -> None:
    """Disables the interaction buttons when waiting for an answer from the
    client"""

    self._upload_protocol_button.setEnabled(not self._waiting_for_answer)
    self._download_protocol_button.setEnabled(not self._waiting_for_answer)
    self._status_button.setEnabled(not self._waiting_for_answer)
    self._start_protocol_button.setEnabled(not self._waiting_for_answer)
    self._stop_protocol_button.setEnabled(not self._waiting_for_answer)
    self._stop_server_button.setEnabled(not self._waiting_for_answer)

  def _display_status(self, status: str) -> None:
    """Displays messages received from the server.

    Args:
      status: Message to display.
    """

    self._status_display.setText(status)
    if status.startswith("Error !"):
      self._status_display.setStyleSheet("color: red;")
    else:
      self._status_display.setStyleSheet("color: black;")

  def _display_busy(self, status: int) -> None:
    """Displays whether the Stimulator is currently performing stimulation.

    It displays a warning message 10 minutes before the next stimulation phase
    starts.

    Args:
      status: Index specifying what message to display.
    """

    if status == 0:
      self._is_busy_status_display.setText("Not currently stimulating")
      self._is_busy_status_display.setStyleSheet("color: green;")
    elif status == 1:
      self._is_busy_status_display.setText("Stimulation starting soon !")
      self._is_busy_status_display.setStyleSheet("color: orange;")
    elif status == 2:
      self._is_busy_status_display.setText("Stimulating ! Do not unplug")
      self._is_busy_status_display.setStyleSheet("color: red;")
    elif status == -1:
      self._is_busy_status_display.setText("")
      self._is_busy_status_display.setStyleSheet("color: black;")
    else:
      self._is_busy_status_display.setText("Error ! Wrong status value "
                                           "received")
      self._is_busy_status_display.setStyleSheet("color: red;")

  def _send_server(self, message: str) -> None:
    """Sends command to the server and displays the corresponding status.

    Args:
      message: The command to send.
    """

    if message == "Stop server":
      mes_box = QMessageBox(QMessageBox.Warning,
                            "Warning !",
                            "Do you really want to stop the server ?\n"
                            "It will stop any running protocol, and "
                            "permanently disable the remote control of the "
                            "Stimulator.\n"
                            "The server cannot be restarted from this "
                            "interface then.")
      mes_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
      ret = mes_box.exec()

      if ret != QMessageBox.Yes:
        return

    elif message == "Upload protocol":
      items = ['a', 'b']
      item, ok = QInputDialog.getItem(self,
                                      "Protocol selection",
                                      "Please select the protocol to upload",
                                      items,
                                      0,
                                      False)
      if not ok:
        return
      message += [" " + item]

    if not self._loop.publish(message):
      self._display_status("Command sent successfully, waiting for answer")
      self._waiting_for_answer = True
      self._disable_if_waiting()
    else:
      self._display_status("Error ! Command not sent")

  def gui_loop(self) -> None:
    """Loop for updating the display on a regular basis.

    Used for updating the connection status in case the client gets
    disconnected from the server. Also manages the messages from the server
    when the interface is waiting for an answer after a command has bee issued.
    And also updates the real-time graphs with the last received data.
    """

    # Updating the graph
    while not self._loop.data_queue.empty():
      try:
        data = self._loop.data_queue.get_nowait()
      except Empty:
        data = None

      if data is not None:
        self._x_data.extend(data[0])
        self._y_data.extend(data[1])
    self._curve.setData(self._x_data, self._y_data)

    # Updating the business status
    while not self._loop.is_busy_queue.empty():
      try:
        busy = self._loop.is_busy_queue.get_nowait()
      except Empty:
        busy = None

      if busy is not None and busy != self._busy:
        self._busy = busy
        self._display_busy(busy)

    if not self._waiting_for_answer:
      # Checking if disconnected
      self._display_if_connected(self._loop.is_connected)
      self._disable_if_connected(self._loop.is_connected)
      if not self._loop.is_connected:
        self._x_data.clear()
        self._y_data.clear()
        self._display_busy(-1)

      # Getting new messages from the server
      if not self._loop.answer_queue.empty():
        try:
          message = self._loop.answer_queue.get_nowait()
        except Empty:
          message = None

        if message is not None:
          self._display_status(message)
    else:
      # Checking if disconnected
      if not self._loop.is_connected:
        self._display_status("Error ! Disconnected while waiting for an "
                             "answer")
        self._display_if_connected(self._loop.is_connected)
        self._disable_if_connected(self._loop.is_connected)
        if not self._loop.is_connected:
          self._x_data.clear()
          self._y_data.clear()
          self._display_busy(-1)
        self._waiting_for_answer = False
        self._answer_timer = 0
        self._disable_if_waiting()

      # Getting new messages from the server
      elif not self._loop.answer_queue.empty():
        try:
          message = self._loop.answer_queue.get_nowait()
        except Empty:
          message = None

        # Exiting the waiting mode
        if message is not None:
          self._display_status(message)
          if message in ["Protocol terminated gracefully",
                         "Stopping the server and the MQTT broker"]:
            self._display_busy(-1)
            self._x_data.clear()
            self._y_data.clear()
          self._waiting_for_answer = False
          self._answer_timer = 0
          self._disable_if_waiting()
      else:
        # Staying in waiting mode and incrementing timer
        self._answer_timer += 1
        if self._answer_timer > 30:
          # Considering that the connection has timed out
          self._display_status("Error ! No answer from the stimulator")
          self._waiting_for_answer = False
          self._answer_timer = 0
          self._disable_if_waiting()

  def _try_connect(self) -> None:
    """Tries to connect to the server."""

    self._connection_status_display.setText(self._loop.connect_to_broker())
    self._display_if_connected(self._loop.is_connected)
    self._disable_if_connected(self._loop.is_connected)

  def _start_thread(self) -> None:
    """Starts the :meth:`_gui_loop` in a thread, so that the update of the
    display can be performed independently from interaction with
    the interface."""

    self._thread = QThread()
    self._timer = Timer(gui=self, delay=1)
    self._timer.moveToThread(self._thread)
    self._thread.started.connect(self._timer.run)
    self._thread.start()

  def _exit_thread(self) -> None:
    """Exits the :meth:`_gui_loop` thread when closing the interface window."""

    self._timer.stop()
    self._thread.exit()
    if not self._thread.wait(5000):
      print("Forcing thread to stop")
      self._thread.terminate()
    else:
      print("thread terminated gracefully")

  def closeEvent(self, event) -> None:
    """Re-writing the ``closeEvent`` handling so that it also stops the
    :meth:`_gui_loop` thread."""

    self._exit_thread()
    event.accept()


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


if __name__ == "__main__":
  Client_loop(1148)()
