# coding: utf-8

from pathlib import Path
from time import sleep
from queue import Empty
from typing import Optional, List, Tuple

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

try:
  from pyqtgraph import PlotWidget
  from pyqtgraph import mkPen
  from pyqtgraph import AxisItem
except (Exception,):
  graph_flag = False
else:
  graph_flag = True

from ..__paths__ import protocols_path
from ..Tools import get_protocol_name


devices = {'Green Stimulator': '10.36.184.1',
           'Beige Stimulator': '10.36.191.44',
           'Local Stimulator': '127.0.0.1'}

index_to_status = {-1: "",
                   0: "Not currently stimulating",
                   1: "Stimulation starting soon !",
                   2: "Stimulating ! Do not unplug"}

index_to_color = {-1: "black",
                  0: "green",
                  1: "orange",
                  2: "red"}


class Timer(QObject):
  """Object that is actually living in the separate thread for updating the
  display."""

  def __init__(self, gui: QMainWindow, delay: float) -> None:
    """Initializes the parent class and sets the flags.

    Args:
      gui: The main window object that will be updated by the thread.
      delay: The time between two display updates in seconds.
    """

    super().__init__()
    self._gui = gui
    self._stop = False
    self.delay = delay

  def run(self) -> None:
    """Runs an infinite loop for refreshing the display."""

    while not self._stop:
      self._gui.gui_loop()
      sleep(self.delay)

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

    self._answer_timer = 0
    self._wfa = False
    self._protocol_to_download = None

    self._protocol_list = []

    # The address and name of the server to connect to
    self._address = None
    self._device = None

    self._parse_message = {'Upload protocol': self._upload_protocol,
                           'Download protocol': self._download_protocol,
                           'Start protocol': self._start_protocol,
                           'Stop server': self._stop_server}

    self._display_graph = graph_flag
    if self._display_graph:
      self._x_data = []
      self._y_data = []

  def __call__(self) -> None:
    """Creates and displays the interface."""

    # Creating the window and the layout
    self._set_layout()
    self._all_sending_buttons = (self._upload_protocol_button,
                                 self._download_protocol_button,
                                 self._status_button,
                                 self._start_protocol_button,
                                 self._stop_protocol_button,
                                 self._stop_server_button)
    self._set_connections()

    # Displaying the window and starting the event loop
    self.show()
    self._update_display(self._loop.is_connected)
    self._start_thread()

  def closeEvent(self, event) -> None:
    """Re-writing the ``closeEvent`` handling so that it also stops the
    :meth:`_gui_loop` thread."""

    self._exit_thread()
    event.accept()

  def gui_loop(self) -> None:
    """Loop for updating the display on a regular basis.

    Used for updating the connection status in case the client gets
    disconnected from the server. Also manages the messages from the server
    when the interface is waiting for an answer after a command has bee issued.
    And also updates the real-time graphs with the last received data.
    """

    # Getting the data waiting in the queues
    data, busy, protocol_list, protocol, message = self._poll_queues()

    # Updating the graph
    self._update_graph(data)

    # Updating the business status
    if busy is not None:
      self._display_busy(busy[0][-1])

    # Updating the protocol list
    if protocol_list is not None:
      self._protocol_list = protocol_list

    # Saving any received protocol
    if protocol is not None and self._protocol_to_download is not None:
      self._save_protocol(protocol, self._protocol_to_download)
      self._protocol_to_download = None

    # Checking if the client is still connected
    connected = self._loop.is_connected
    self._update_display(connected)

    if not connected:
      # Emptying the graph and resetting the protocol list
      self._on_disconnect()
      self._protocol_list = []

      # Specific actions to take if the client was waiting for an answer
      if self._waiting_for_answer:
        self._display_status("Error ! Disconnected while waiting for an answer")
        self._waiting_for_answer = False

    # A message was received and the client is still connected
    elif message is not None:
      # First, displaying the message
      self._display_status(message)
      # If a message was received, we're not waiting for an answer anymore
      self._waiting_for_answer = False

      # The following messages indicate that the protocol has stopped
      if message in ["Protocol terminated gracefully",
                     "Stopping the server and the MQTT broker",
                     "Protocol terminated with an error"]:
        self._on_disconnect()

        # In case the server stopped, there's no use keeping the client alive
        if message == "Stopping the server and the MQTT broker":
          sleep(2)
          self._display_status("This interface will now stop !")
          sleep(2)
          self.close()

    # In case we're still waiting for an answer, incrementing the timer
    if self._waiting_for_answer:
      self._answer_timer += 1
      # If the client waited too long, considering the connection has timed out
      if self._answer_timer > 10:
        self._display_status("Error ! No answer from the stimulator")
        self._waiting_for_answer = False

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

    # Label displaying the incoming messages
    self._status_display = QLabel("")
    self._generalLayout.addWidget(self._status_display)

    # Plotting the graph of real-time position
    if self._display_graph:
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

      self._curve = self._graph.plot(self._x_data, self._y_data, pen=mkPen('k'))

    # Label displaying whether the stimulator is busy or not
    self._is_busy_header = QLabel("Stimulator busy :")
    self._generalLayout.addWidget(self._is_busy_header)

    self._is_busy_status_display = QLabel("")
    self._generalLayout.addWidget(self._is_busy_status_display)

    # Centering the GUI on the screen
    delta_x = int((self._loop.app.desktop().availableGeometry().width() -
                   self.width()) / 2)
    delta_y = int((self._loop.app.desktop().availableGeometry().height() -
                   self.height()) / 2)
    self.move(delta_x, delta_y)

  def _set_connections(self) -> None:
    """Sets the actions to perform when interacting with the widgets."""

    self._connect_button.clicked.connect(self._try_connect)

    # Except for the connect button, all others send their own text
    for button in self._all_sending_buttons:
      button.clicked.connect(partial(self._send_server, button.text()))

  def _update_display(self, connected: bool) -> None:
    """Displays the connection status.

    Args:
      connected: :obj:`True` if connected to the server, else :obj:`False`.
    """

    if connected:
      self._is_connected_display.setText(f'Connected to the {self._device}')
      self._connection_status_display.setText("")
      self._is_connected_display.setStyleSheet("color: black;")

    else:
      self._is_connected_display.setText("Not connected")
      self._is_connected_display.setStyleSheet("color: red;")

    # Disables or enables the buttons according to the connection status
    self._connect_button.setEnabled(not connected)
    for button in self._all_sending_buttons:
      button.setEnabled(connected)
    self._is_busy_header.setEnabled(connected)
    self._is_busy_status_display.setEnabled(connected)

  def _poll_queues(self) -> Tuple[Optional[List[List[float]]],
                                  Optional[List[List[int]]],
                                  Optional[List[str]],
                                  Optional[List[str]],
                                  Optional[str]]:
    """"""

    ret = tuple()

    # Getting all the data to plot
    for queue in (self._loop.data_queue,):
      to_get = [[], []]
      while not queue.empty():
        try:
          data = queue.get_nowait()
        except Empty:
          data = None

        if data is not None:
          to_get[0].extend(data[0])
          to_get[1].extend(data[1])

      if not to_get[0]:
        to_get = None
      ret += (to_get,)

    # Getting the last received elements
    for queue in (self._loop.is_busy_queue, self._loop.protocol_list_queue,
                  self._loop.protocol_queue):
      to_get = None
      while not queue.empty():
        try:
          to_get = queue.get_nowait()
        except Empty:
          break
      ret += (to_get,)

    # Getting only the next element waiting in the queue
    for queue in (self._loop.answer_queue,):
      to_get = None
      if not queue.empty():
        try:
          to_get = queue.get_nowait()
        except Empty:
          break
      ret += (to_get,)

    return ret

  def _update_graph(self, data: Optional[List[list]]) -> None:
    """"""

    if data is not None and self._display_graph:
      # Store the data in memory
      self._x_data.extend(data[0])
      self._y_data.extend(data[1])

      # Trim data to keep only the latest
      if len(self._x_data) > 1000:
        self._x_data = self._x_data[-1000:]
        self._y_data = self._y_data[-1000:]

      # Update the display
      self._curve.setData(self._x_data, self._y_data)

  def _on_disconnect(self) -> None:
    """"""

    # Stop displaying the business status
    self._display_busy(-1)

    # Empty the graph
    if self._display_graph:
      self._x_data.clear()
      self._y_data.clear()
      self._curve.setData(self._x_data, self._y_data)

  @property
  def _waiting_for_answer(self) -> bool:
    """"""

    return self._wfa

  @_waiting_for_answer.setter
  def _waiting_for_answer(self, waiting: bool) -> None:
    self._wfa = waiting
    for button in self._all_sending_buttons:
      button.setEnabled(not waiting)
    self._answer_timer = 0

  def _display_status(self, status: str) -> None:
    """Displays messages received from the server.

    Args:
      status: Message to display.
    """

    self._status_display.setText(status)
    self._status_display.setStyleSheet(
      f'color: {"red" if status.startswith("Error !") else "black"};')

  def _display_busy(self, status: int) -> None:
    """Displays whether the Stimulator is currently performing stimulation.

    It displays a warning message 10 minutes before the next stimulation phase
    starts.

    Args:
      status: Index specifying what message to display.
    """

    text = index_to_status.get(status, "Error ! Wrong status value received")
    color = index_to_color.get(status, 'red')
    self._is_busy_status_display.setText(text)
    self._is_busy_status_display.setStyleSheet(f"color: {color};")

  @ staticmethod
  def _save_protocol(protocol: List[str], name: str) -> None:
    """Saves a protocol received from the server in the Protocols/ directory.

    Args:
      protocol: A :obj:`list` of :obj:`str`, each element representing a line of
        a `.py` document containing the protocol code.
      name: The name of the protocol.
    """

    if not Path.exists(protocols_path):
      Path.mkdir(protocols_path)

      with open(protocols_path / "__init__.py", 'w') as init_file:
        init_file.write("# coding: utf-8\n\n")
        init_file.write(f"from .Protocol_{name} import Led, Mecha, Elec\n")

    with open(protocols_path / f"Protocol_{name}.py", 'w') as protocol_file:
      for line in protocol:
        protocol_file.write(line)

  def _send_server(self, message: str) -> None:
    """Sends command to the server and displays the corresponding status.

    Args:
      message: The command to send.
    """

    # Parsing the message in case more info needs to be added to it
    message = self._parse_message.get(message, lambda: message)()

    # If the message is None, the user aborted the operation
    if message is None:
      return

    # Sending the message and starting to wait for the answer
    if not self._loop.publish(message):
      self._display_status("Command sent successfully, waiting for answer")
      self._waiting_for_answer = True
    else:
      self._display_status("Error ! Command not sent")

  @staticmethod
  def _stop_server() -> Optional[str]:
    """"""

    mes_box = QMessageBox(QMessageBox.Warning,
                          "Warning !",
                          "Do you really want to stop the server ?\n"
                          "It will stop any running protocol, and "
                          "permanently disable the remote control of the "
                          "Stimulator.\n"
                          "The server cannot be restarted from this "
                          "interface then.")
    mes_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    if mes_box.exec() != QMessageBox.Yes:
      return

    return "Stop server"

  def _upload_protocol(self) -> Optional[str]:
    """"""

    # Getting the list of the existing protocols
    try:
      protocol_list = Path.iterdir(protocols_path)
    except FileNotFoundError:
      self._display_status("Error ! No protocol found. Please create one")
      return

    items = [get_protocol_name(protocol) for protocol in protocol_list
             if get_protocol_name(protocol) is not None]

    # Asking the user which protocol to upload
    item, ok = QInputDialog.getItem(
      self,
      "Protocol selection",
      "Please select the protocol to upload",
      items,
      current=0,
      editable=False)

    if not ok:
      return

    # Asking the user for the password for uploading protocols
    password, ok = QInputDialog.getText(self,
                                        "Password",
                                        "Please enter the password for "
                                        "uploading files :")
    if not ok:
      return
    message = f"Upload protocol {item} {password}"

    # Sending the protocol to the server
    protocol = []
    with open(protocols_path / f"Protocol_{item}.py", 'r') as protocol_file:
      for line in protocol_file:
        protocol.append(line)

    if self._loop.upload_protocol(protocol):
      self._display_status("Error ! Protocol not sent")
      return

    # Ask the server to send the protocol list again
    self._send_server("Return protocol list")

    return message

  def _start_protocol(self) -> Optional[str]:
    """"""

    # Checking that there are protocols to start
    if not self._protocol_list:
      self._display_status("Error ! No protocol to start. Please upload one.")
      return

    # Asking the user which protocol to start
    item, ok = QInputDialog.getItem(
      self,
      "Protocol selection",
      "Please select the protocol to run",
      self._protocol_list,
      current=0,
      editable=False)
    if not ok:
      return

    return f"Start protocol {item}"

  def _download_protocol(self) -> Optional[str]:
    """"""

    # Checking that there are protocols to download
    if not self._protocol_list:
      self._display_status("Error ! No protocol to download")
      return

    # Asking the user which protocol to download
    item, ok = QInputDialog.getItem(
      self,
      "Protocol selection",
      "Please select the protocol to download",
      self._protocol_list,
      current=0,
      editable=False)
    if not ok:
      return

    self._protocol_to_download = item
    return f"Download protocol {item}"

  def _try_connect(self) -> None:
    """Tries to connect to the server."""

    # Asking the user for the stimulator to connect to
    if self._address is None:
      item, ok = QInputDialog.getItem(
        self,
        "Stimulator selection",
        "Please select the stimulator to connect to :",
        devices.keys(),
        current=0,
        editable=False)

      if not ok:
        return

      self._address = devices[item]
      self._device = item

    # Actually trying to connect
    self._connection_status_display.setText(
        self._loop.connect_to_broker(address=self._address))
    self._update_display(self._loop.is_connected)

    # Asking the server for the available protocols
    if self._loop.is_connected:
      self._send_server("Return protocol list")

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

    delay = self._timer.delay
    self._timer.stop()
    self._thread.exit()
    sleep(delay + 0.1)
    if not self._thread.isFinished():
      self._thread.terminate()
