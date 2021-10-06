# coding: utf-8

import crappy
import RPi.GPIO as GPIO


class Led_drive(crappy.inout.InOut):

  def __init__(self, pin_green: int, pin_orange: int, pin_red: int) -> None:
    super().__init__()
    for pin in [pin_green, pin_orange, pin_red]:
      if pin not in range(2, 28):
        raise ValueError('pin {} should be an integer between '
                         '2 and 28'.format(pin))
    self.pin_green = pin_green
    self.pin_orange = pin_orange
    self.pin_red = pin_red

  def open(self) -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(self.pin_green, GPIO.OUT)
    GPIO.setup(self.pin_orange, GPIO.OUT)
    GPIO.setup(self.pin_red, GPIO.OUT)

  def set_cmd(self, cmd: int) -> None:
    if cmd not in [0, 1, 2]:
      cmd = 2
    if cmd == 0:
      GPIO.output(self.pin_green, GPIO.HIGH)
      GPIO.output(self.pin_orange, GPIO.LOW)
      GPIO.output(self.pin_red, GPIO.LOW)
    elif cmd == 1:
      GPIO.output(self.pin_green, GPIO.LOW)
      GPIO.output(self.pin_orange, GPIO.HIGH)
      GPIO.output(self.pin_red, GPIO.LOW)
    elif cmd == 2:
      GPIO.output(self.pin_green, GPIO.LOW)
      GPIO.output(self.pin_orange, GPIO.LOW)
      GPIO.output(self.pin_red, GPIO.HIGH)

  @staticmethod
  def close() -> None:
    GPIO.cleanup()


labels = []
to_send = []

if Elec:
  gen_elec = crappy.blocks.Generator(Elec)
  mosfet = crappy.blocks.IOBlock('Gpio_switch', cmd_labels=['cmd'], pin_out=18)
  crappy.link(gen_elec, mosfet)

if Mecha:
  gen_mecha = crappy.blocks.Generator(Mecha, freq=10)
  machine = crappy.blocks.Machine([{'type': 'Pololu_tic',
                                    'steps_per_mm': 252,
                                    'current_limit': 2000,
                                    'step_mode': 128,
                                    't_shutoff': 1,
                                    'backend': 'ticcmd',
                                    'mode': 'position',
                                    'pos_label': 'pos_mot',
                                    'cmd': 'cmd'}])
  crappy.link(gen_mecha, machine)

  ads_1115 = crappy.blocks.IOBlock('Ads1115', backend='Pi4', sample_rate=8,
                                   v_range=4.096, gain=29.9587,
                                   labels=['t(s)', 'pos_ads'])

  sink = crappy.blocks.Sink()
  crappy.link(ads_1115, sink)

  labels += [('t(s)', 'pos_mot')]
  to_send += [('t', 'pos')]

led = crappy.blocks.Generator(Led, freq=10, spam=True)
light = crappy.blocks.IOBlock('Led_drive',
                              pin_green=25,
                              pin_orange=24,
                              pin_red=23,
                              cmd_labels=['cmd'])
crappy.link(led, light)

labels += [('cmd',)]
to_send += [('busy',)]

server = crappy.blocks.Client_server(cmd_labels=labels,
                                     labels_to_send=to_send)

crappy.link(led, server)
if Mecha:
  crappy.link(machine, server)

crappy.start()
