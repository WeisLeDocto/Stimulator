# coding: utf-8

import time
import paho.mqtt.client as mqtt
from queue import Queue, Empty
import socket
from pickle import loads, dumps, UnpicklingError

import sys
from functools import partial
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import QThread
from PyQt5.QtCore import QObject


class Timer(QObject):
  def __init__(self, gui):
    super().__init__()
    self._gui = gui
    self._stop = False

  def run(self):
    while not self._stop:
      self._gui._gui_loop()
      time.sleep(1)

  def stop(self):
    self._stop = True


class Graphical_interface(QMainWindow):
  def __init__(self, loop):
    super().__init__()
    self._loop = loop
    self._waiting_for_answer = False
    self._answer_timer = 0

  def __call__(self):
    self.setWindowTitle('Stimulator Interface')

    self._generalLayout = QVBoxLayout()
    self._centralWidget = QWidget(self)
    self.setCentralWidget(self._centralWidget)
    self._centralWidget.setLayout(self._generalLayout)

    self._connect_button = QPushButton("Connect to stimulator")
    self._generalLayout.addWidget(self._connect_button)

    self._is_connected_display = QLabel("")
    self._generalLayout.addWidget(self._is_connected_display)

    self._connection_status_display = QLabel("")
    self._generalLayout.addWidget(self._connection_status_display)

    self._status_button = QPushButton("Print status")
    self._generalLayout.addWidget(self._status_button)

    self._start_protocol_button = QPushButton("Start protocol")
    self._generalLayout.addWidget(self._start_protocol_button)

    self._stop_protocol_button = QPushButton("Stop protocol")
    self._generalLayout.addWidget(self._stop_protocol_button)

    self._stop_server_button = QPushButton("Stop server")
    self._generalLayout.addWidget(self._stop_server_button)

    self._status_display = QLabel("")
    self._generalLayout.addWidget(self._status_display)

    self._display_if_connected(self._loop._is_connected)
    self._disable_if_connected(self._loop._is_connected)

    self._connect_button.clicked.connect(self._try_connect)

    self._status_button.clicked.connect(
      partial(self._send_server, self._status_button.text()))

    self._start_protocol_button.clicked.connect(
      partial(self._send_server, self._start_protocol_button.text()))

    self._stop_protocol_button.clicked.connect(
      partial(self._send_server, self._stop_protocol_button.text()))

    self._stop_server_button.clicked.connect(
      partial(self._send_server, self._stop_server_button.text()))

    self.show()

    self._thread = QThread()
    self._timer = Timer(self)
    self._timer.moveToThread(self._thread)
    self._thread.started.connect(self._timer.run)
    self._thread.start()

  def _display_if_connected(self, bool_: bool) -> None:
    if bool_:
      self._is_connected_display.setText("Connected")
      self._display_connection_status("")
      self._is_connected_display.setStyleSheet("color: black;")
    else:
      self._is_connected_display.setText("Not connected")
      self._is_connected_display.setStyleSheet("color: red;")

  def _disable_if_connected(self, bool_: bool) -> None:
    self._connect_button.setEnabled(not bool_)
    self._status_button.setEnabled(bool_)
    self._start_protocol_button.setEnabled(bool_)
    self._stop_protocol_button.setEnabled(bool_)
    self._stop_server_button.setEnabled(bool_)

  def _disable_if_waiting(self) -> None:
    self._status_button.setEnabled(not self._waiting_for_answer)
    self._start_protocol_button.setEnabled(not self._waiting_for_answer)
    self._stop_protocol_button.setEnabled(not self._waiting_for_answer)
    self._stop_server_button.setEnabled(not self._waiting_for_answer)

  def _display_connection_status(self, status: str) -> None:
    self._connection_status_display.setText(status)

  def _display_status(self, status: str) -> None:
    self._status_display.setText(status)
    if status.startswith("Error !"):
      self._status_display.setStyleSheet("color: red;")
    else:
      self._status_display.setStyleSheet("color: black;")

  def _send_server(self, message: str) -> None:
    if not self._loop._publish(message):
      self._display_status("Command sent successfully, waiting for answer")
      self._waiting_for_answer = True
      self._disable_if_waiting()
    else:
      self._display_status("Error ! Command not sent")

  def _gui_loop(self) -> None:
    if not self._waiting_for_answer:
      self._display_if_connected(self._loop._is_connected)
      self._disable_if_connected(self._loop._is_connected)

      if not self._loop._queue.empty():
        try:
          message = self._loop._queue.get_nowait()
        except Empty:
          message = None

        if message is not None:
          self._display_status(message)
    else:
      if not self._loop._is_connected:
        self._display_status("Error ! Disconnected while waiting for an "
                             "answer")
        self._display_if_connected(self._loop._is_connected)
        self._disable_if_connected(self._loop._is_connected)
        self._waiting_for_answer = False
        self._answer_timer = 0
        self._disable_if_waiting()

      elif not self._loop._queue.empty():
        try:
          message = self._loop._queue.get_nowait()
        except Empty:
          message = None

        if message is not None:
          self._display_status(message)
          self._waiting_for_answer = False
          self._answer_timer = 0
          self._disable_if_waiting()
      else:
        self._answer_timer += 1
        if self._answer_timer > 30:
          self._display_status("Error ! No answer from the stimulator")
          self._waiting_for_answer = False
          self._answer_timer = 0
          self._disable_if_waiting()

  def _try_connect(self) -> None:
    self._display_connection_status(self._loop._connect_to_broker())
    self._display_if_connected(self._loop._is_connected)
    self._disable_if_connected(self._loop._is_connected)

  def _exit_thread(self):
    self._timer.stop()
    self._thread.exit()
    if self._thread.wait(5000):
      print("Stopped")

  def closeEvent(self, event) -> None:
    self._exit_thread()
    event.accept()


class Client_loop:
  def __init__(self,
               port: int,
               address: str = 'localhost',
               topic_out: str = 'Remote_control',
               topic_in: str = 'Server_status') -> None:
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

    self._topic_in = topic_in
    self._topic_out = topic_out
    self._queue = Queue()
    self._client = mqtt.Client(str(time.time()))
    self._client.on_connect = self._on_connect
    self._client.on_message = self._on_message
    self._client.on_disconnect = self._on_disconnect
    self._client.reconnect_delay_set(max_delay=10)

    self._is_connected = False
    self._connected_once = False

  def __call__(self):
    try:
      app = QApplication(sys.argv)
      Graphical_interface(self)()
      sys.exit(app.exec_())
    finally:
      self._client.disconnect()

  def _publish(self, message: str) -> None:
    return self._client.publish(topic=self._topic_out,
                                payload=dumps(message),
                                qos=2)[0]

  def _on_message(self, client, userdata, message) -> None:
    try:
      self._queue.put_nowait(loads(message.payload))
    except UnpicklingError:
      print("Warning ! Message raised UnpicklingError, ignoring it")
    print("Got message" + " : " + loads(message.payload))

  def _on_connect(self, client, userdata, flags, rc) -> None:
    self._client.subscribe(topic=self._topic_in, qos=2)
    print("Subscribed")
    self._is_connected = True
    self._client.loop_start()

  def _on_disconnect(self, client, userdata, rc) -> None:
    self._is_connected = False

  def _connect_to_broker(self) -> str:
    # Connecting to the broker
    try:
      if self._connected_once:
        self._client.reconnect()
      else:
        self._client.connect(host=self._address, port=self._port, keepalive=10)
      self._is_connected = True
      self._connected_once = True
    except socket.timeout:
      print("Impossible to reach the given address, aborting")
      self._is_connected = False
      return "Address unreachable"
    except socket.gaierror:
      print("Invalid address given, please check the spelling")
      self._is_connected = False
      return "Address invalid"
    except ConnectionRefusedError:
      print("Connection refused, the broker may not be running or you may "
            "not have the rights to connect")
      self._is_connected = False
      return "Server not running"

    self._client.loop_start()
    return ""


if __name__ == "__main__":
  Client_loop(1148)()
