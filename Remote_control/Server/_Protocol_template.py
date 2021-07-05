# coding: utf-8

import paho.mqtt.client as mqtt
import time
from pickle import dumps


class Position_sender:
  def __init__(self, address='localhost', port=1148):
    self._client = mqtt.Client(str(time.time()))
    self._client.reconnect_delay_set(max_delay=10)
    self._client.connect(host=address, port=port, keepalive=10)
    self._client.loop_start()

  def __call__(self):
    try:
      t = 0
      pos = 0
      while True:
        to_send = [[], []]
        for _ in range(5):
          to_send[0].append(t)
          to_send[1].append(pos)
          t += 0.1
          pos += 0.05
          time.sleep(0.1)
        busy = 0 if not t // 10 % 3 else 1 if not (t // 10 - 1) % 3 else 2
        self._client.publish(str(('t', 'pos')), dumps(to_send), qos=2)
        self._client.publish(str(('busy',)), dumps(busy), qos=2)
    except KeyboardInterrupt:
      self._client.loop_stop()
      self._client.disconnect()


if __name__ == "__main__":
  Position_sender()()
