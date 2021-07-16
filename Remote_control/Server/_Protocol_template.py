# coding: utf-8

import crappy

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

led = crappy.blocks.Generator(Led, freq=10)
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
