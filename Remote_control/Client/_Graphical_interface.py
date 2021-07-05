# coding: utf-8

import os
import time
from queue import Empty

from functools import partial
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
      try:
        path = os.path.dirname(os.path.abspath(__file__))
        path = path.replace("/Client", "")
        protocol_list = os.listdir(path + "/Protocols/")
      except FileNotFoundError:
        self._display_status("Error ! No protocol found. Please create one")
        return
      protocol_list.remove("__init__.py")
      items = [protocol.replace("Protocol_", "").replace(".py", "")
               for protocol in protocol_list]
      item, ok = QInputDialog.getItem(self,
                                      "Protocol selection",
                                      "Please select the protocol to upload",
                                      items,
                                      0,
                                      False)
      if not ok:
        return
      message += " " + item

      protocol = []
      with open(path + "/Protocols/Protocol_" + item + ".py", 'r') \
           as protocol_file:
        for line in protocol_file:
          protocol.append(line)

      if self._loop.upload_protocol(protocol):
        self._display_status("Error ! Protocol not sent")
        return

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