# coding: utf-8

import datetime
import matplotlib
import matplotlib.pyplot as plt
import os


class Protocol_phases:
  """Class implementing methods for building a stimulation protocol."""

  def __init__(self,
               full_step_per_mm=252,
               step_mode=128,
               time_orange_on_minutes: float = 10) -> None:
    """Sets the instance attributes.

    Args:
      full_step_per_mm: Gain of the motor in step/mm when driving in full step
        mode.
      step_mode: The step mode to use for driving the motor.
      time_orange_on_minutes: The orange light warns the user that a stimulation
        will restart soon. How long before should the light switch from green to
        orange ?
    """

    self._full_step_per_mm = full_step_per_mm
    self._step_mode = step_mode
    self._time_orange_on_minutes = time_orange_on_minutes

    self._mecha_stimu = []
    self._elec_stimu = []
    self._mecha_stimu_on = [(0., False)]
    self._elec_stimu_on = [(0., False)]
    self._position = [(0., 0.)]

    self._py_file = ["# coding: utf-8" + "\n",
                     "\n",
                     "from ..Tools import Protocol_phases" + "\n",
                     "\n",
                     ]

  def add_continuous_stretching(self,
                                travel_length_mm: float,
                                resting_time_ratio: float,
                                consecutive_stretch_duration_hours: float,
                                total_duration_hours: float) -> None:
    """Adds a continuous stretching phase, during which the muscle is being
    slowly stretched.

    Increases the position step by step. So should only be used for really slow
    paces.

    Args:
      travel_length_mm: The total distance the muscle should be stretched by.
      resting_time_ratio: Ratio of the time spent resting over the total
        duration.
      consecutive_stretch_duration_hours: How long should the muscle be
        stretched before a resting period starts ?
      total_duration_hours: Total duration of the continuous stretching phase.
    """

    # Calculating parameters
    delay_between_steps = total_duration_hours * 60 * 60 * (
        1 - resting_time_ratio) / self._full_step_per_mm / self._step_mode / \
        abs(travel_length_mm)
    step_length = 1 / self._full_step_per_mm / self._step_mode
    number_of_steps = int(abs(travel_length_mm) * self._step_mode *
                          self._full_step_per_mm)

    # Adding positions step by step, and adding a resting phase when needed
    time_count = 0
    for i in range(number_of_steps):
      self._add_mecha(position=i * step_length,
                      delay=delay_between_steps,
                      is_active=True)
      time_count += delay_between_steps
      if time_count > consecutive_stretch_duration_hours * 60 * 60:
        time_count -= consecutive_stretch_duration_hours * 60 * 60
        self._add_mecha(position=i * step_length,
                        delay=round((1 / (1 - resting_time_ratio) - 1) *
                                    consecutive_stretch_duration_hours *
                                    60 * 60),
                        is_active=False)

  def add_cyclic_stretching(self,
                            resting_position_mm: float,
                            stretched_position_mm: float,
                            number_of_cycles: int,
                            number_of_reps: int,
                            time_to_reach_position_seconds: float,
                            number_of_sets: int,
                            rest_between_sets_minutes: float,
                            rest_between_reps_minutes: float) -> None:
    """Adds a cyclic stretching phase, during which the muscle is being
    stretched in a cyclic way.

    The cyclic stretching is split in sets, separated by resting phases. Each
    set counts several reps, also separated by resting phases. And each rep
    consists in a given number of cycles, with no rest between cycles.

    Args:
      resting_position_mm: The position of the pin during resting phases.
      stretched_position_mm: The target position of the pin when muscle is
        stretched.
      number_of_cycles: The number of cycles during a rep.
      number_of_reps: The number of reps during a set.
      time_to_reach_position_seconds: The delay between a command to go to
        stretched position and a command to return to resting position during a
        cycle. Depending on speed, the pin may not have time to reach the target
        position and the actual stretched position is then less than expected.
      number_of_sets: The number of sets.
      rest_between_sets_minutes: The resting time between sets.
      rest_between_reps_minutes: The resting time between cycles.
    """

    for _ in range(number_of_sets):
      for i in range(number_of_reps):
        for _ in range(number_of_cycles):
          self._add_mecha(position=stretched_position_mm,
                          delay=time_to_reach_position_seconds,
                          is_active=True)
          self._add_mecha(position=resting_position_mm,
                          delay=time_to_reach_position_seconds,
                          is_active=True)
        if i != number_of_reps - 1:
          self._add_mecha(position=resting_position_mm,
                          delay=rest_between_reps_minutes * 60,
                          is_active=False)
      self._add_mecha(position=resting_position_mm,
                      delay=rest_between_sets_minutes * 60,
                      is_active=False)

  def add_mechanical_rest(self,
                          rest_duration_hours: float,
                          resting_position_mm: float) -> None:
    """Adds a mechanical resting phase.

    Args:
      rest_duration_hours: The resting phase duration.
      resting_position_mm: The position to hold during the resting phase.
    """

    self._add_mecha(position=resting_position_mm,
                    delay=rest_duration_hours * 60 * 60,
                    is_active=False)

  def add_electrical_stimulation(self,
                                 pulse_duration_seconds: float,
                                 set_duration_minutes: float,
                                 delay_between_pulses_seconds: float,
                                 rest_between_sets_minutes: float,
                                 number_of_sets: int) -> None:
    """Adds an electrical stimulation phase, during which electrical pulses are
    sent to the muscles.

    The stimulation is split in sets, of given duration and separated by a
    resting time. During a set, the muscle is continuously being stimulated.

    Args:
      pulse_duration_seconds: The duration of an pulse.
      set_duration_minutes: The duration of a set.
      delay_between_pulses_seconds: A pulse is sent once every this value
        seconds.
      rest_between_sets_minutes: The delay between two sets.
      number_of_sets: The number of sets.
    """

    pulses_per_set = round(set_duration_minutes * 60 /
                           delay_between_pulses_seconds)
    for _ in range(number_of_sets):
      self._elec_stimu.append(
        {'type': 'cyclic',
         'value1': 1, 'condition1': 'delay={}'.format(
          delay_between_pulses_seconds - pulse_duration_seconds),
         'value2': 0,
         'condition2': 'delay={}'.format(pulse_duration_seconds),
         'cycles': pulses_per_set})
      self._elec_stimu_on.append((set_duration_minutes * 60, True))
      self._elec_stimu.append(
        {'type': 'constant',
         'condition': 'delay={}'.format(rest_between_sets_minutes * 60),
         'value': 1})
      self._elec_stimu_on.append((rest_between_sets_minutes * 60, False))

  def add_electrical_rest(self,
                          rest_duration_hours: float) -> None:
    """Adds an electrical resting phase, during which no current flows in the
    electrodes.

    Args:
      rest_duration_hours: The resting phase duration.
    """

    self._elec_stimu.append(
      {'type': 'constant',
       'condition': 'delay={}'.format(rest_duration_hours * 60 * 60),
       'value': 1})
    self._elec_stimu_on.append((rest_duration_hours * 60 * 60, False))

  def save_protocol(self, name: str) -> None:
    """saves the protocol as a `.py` file in the Protocols/ directory.

    Before saving, displays the graphs summarizing the protocol and asks the
    user for confirmation.

    Args:
      name: The name of the protocol to save.
    """

    self._plot_protocol(*self._build_led_list())

    print("Do you want to save the current protocol ?")
    while True:
      answer = input("Yes / No :   ")
      if answer in ["Yes", "yes"]:

        path = os.path.dirname(os.path.abspath(__file__))
        path = path.replace("/Tools", "")

        if not os.path.exists(path + "/Protocols/"):
          os.mkdir(path + "/Protocols/")
          with open(path + "/Protocols/" + "__init__.py", 'w') as init_file:
            init_file.write("# coding: utf-8" + "\n")
            init_file.write("\n")
            init_file.write(
              "from .Protocol_" + name + " import Led, Mecha, Elec"
              + "\n")

        with open(path.replace("/Remote_control", "") +
                  "/Create_protocol.py", 'r') as file:
          with open(path + "/Protocols/" + "Protocol_" + name +
                    ".py", 'w') as exported_file:

            for line in self._py_file:
              exported_file.write(line)

            copy = False
            for line in file:
              if line.strip() == "if __name__ == '__main__':":
                copy = True
                continue
              if "save" in line.strip():
                copy = False
              if copy:
                exported_file.write(line[2:])
            exported_file.write("Led, Mecha, Elec = new_prot.export()" + "\n")

        print("Protocol saved !")
        break
      elif answer in ["No", "no"]:
        print("Protocol not saved")
        break
      else:
        print("Please answer Yes or No !")

  def export(self) -> tuple:
    """Generates the lists the stimulation program takes as inputs, and returns
    them.

    Returns:
      The lists for driving the Crappy Generators.
    """

    self._build_led_list()
    return self._list_led, self._mecha_stimu, self._elec_stimu

  def _add_mecha(self,
                 position: float,
                 delay: float,
                 is_active: bool) -> None:
    """Wrapper for generating a :obj:`dict` containing all Crappy Generator
    relevant information and adding it to the :obj:`list` of dictionaries.

    Args:
      position: The position to reach
      delay: The delay for reaching/holding this position.
      is_active: :obj:`True` if this command is part of a stimulation phase,
        :obj:`False` if it is part of a resting phase.
    """

    self._mecha_stimu.append(
      {'type': 'constant',
       'condition': 'delay={}'.format(delay),
       'value': position})
    self._mecha_stimu_on.append((delay, is_active))
    self._position.append((delay, position))

  def _build_led_list(self) -> tuple:
    """Builds the three :obj:`list` of :obj:`dict` necessary for starting the
    protocol, and returns them.

    Returns:
      The lists for driving the Crappy Generators.
    """

    # Building lists of tuples
    # The first value is the timestamp, the second tells whether the stimulation
    # is on or off from this timestamp to the next one
    self._mecha_stimu_on[0] = (0.,
                               self._mecha_stimu and self._mecha_stimu_on[1][1])
    self._elec_stimu_on[0] = (0.,
                              self._elec_stimu and self._elec_stimu_on[1][1])

    stimu_mecha_timestamps = [self._mecha_stimu_on[0]]
    position_timestamps = [self._position[0]]
    stimu_elec_timestamps = [self._elec_stimu_on[0]]
    if self._mecha_stimu:
      for ((t, _), (_, value)) in zip(self._mecha_stimu_on[1:-1],
                                      self._mecha_stimu_on[2:]):
        stimu_mecha_timestamps.append(
          (t + stimu_mecha_timestamps[-1][0], value))

      for ((t, _), (_, value)) in zip(self._position[1:-1], self._position[2:]):
        position_timestamps.append((t + position_timestamps[-1][0], value))

    if self._elec_stimu:
      for ((t, _), (_, value)) in zip(self._elec_stimu_on[1:-1],
                                      self._elec_stimu_on[2:]):
        stimu_elec_timestamps.append((t + stimu_elec_timestamps[-1][0], value))

    # Simplifying the timestamps lists to remove redundant elements
    if self._mecha_stimu:
      to_remove_mecha = []
      for index, (tuple1, tuple2) in enumerate(
          zip(stimu_mecha_timestamps[:-1],
              stimu_mecha_timestamps[1:])):
        if tuple1[1] == tuple2[1]:
          to_remove_mecha.append(index + 1)
      if to_remove_mecha:
        to_remove_mecha.reverse()
        for index in to_remove_mecha:
          del stimu_mecha_timestamps[index]

    if self._elec_stimu:
      to_remove_elec = []
      for index, (tuple1, tuple2) in enumerate(zip(stimu_elec_timestamps[:-1],
                                                   stimu_elec_timestamps[1:])):
        if tuple1[1] == tuple2[1]:
          to_remove_elec.append(index + 1)
      if to_remove_elec:
        to_remove_elec.reverse()
        for index in to_remove_elec:
          del stimu_elec_timestamps[index]

    # Building another timestamp list to know if any stimulation is on
    is_active_timestamps = []
    index_elec = 0
    index_mecha = 0
    while True:
      if stimu_mecha_timestamps[index_mecha][0] > \
             stimu_elec_timestamps[index_elec][0]:
        is_active_timestamps.append((stimu_mecha_timestamps[index_mecha][0],
                                     stimu_mecha_timestamps[index_mecha][1] or
                                     stimu_elec_timestamps[index_elec][1]))
      elif stimu_mecha_timestamps[index_mecha][0] < \
              stimu_elec_timestamps[index_elec][0]:
        is_active_timestamps.append((stimu_elec_timestamps[index_elec][0],
                                     stimu_mecha_timestamps[index_mecha][1] or
                                     stimu_elec_timestamps[index_elec][1]))
      else:
        is_active_timestamps.append((stimu_mecha_timestamps[index_mecha][0],
                                     stimu_mecha_timestamps[index_mecha][1] or
                                     stimu_elec_timestamps[index_elec][1]))

      try:
        next_mecha_ts = stimu_mecha_timestamps[index_mecha + 1][0]
      except IndexError:
        next_mecha_ts = None
      try:
        next_elec_ts = stimu_elec_timestamps[index_elec + 1][0]
      except IndexError:
        next_elec_ts = None

      # Particular situation at the end of the protocol
      if next_mecha_ts is None and next_elec_ts is None:
        break
      elif next_mecha_ts is None:
        is_active_timestamps.extend(stimu_elec_timestamps[index_elec + 1:])
        break
      elif next_elec_ts is None:
        is_active_timestamps.extend(stimu_mecha_timestamps[index_mecha + 1:])
        break

      # Moving on to the next timestamp
      if next_mecha_ts > next_elec_ts:
        index_elec += 1
      elif next_elec_ts > next_mecha_ts:
        index_mecha += 1
      else:
        index_elec += 1
        index_mecha += 1

    # Building the list of dictionaries for driving the LED
    self._list_led = []
    for tuple1, tuple2 in zip(is_active_timestamps[:-1],
                              is_active_timestamps[1:]):
      if not tuple1[1] and (
           (tuple2[0] - tuple1[0]) > self._time_orange_on_minutes * 60):
        self._list_led.append(
          {'type': 'constant',
           'condition': 'delay={}'.format((tuple2[0] - tuple1[0]) -
                                          self._time_orange_on_minutes * 60),
           'value': 0})
        self._list_led.append(
          {'type': 'constant',
           'condition': 'delay={}'.format(self._time_orange_on_minutes * 60),
           'value': 1})
      else:
        self._list_led.append(
          {'type': 'constant',
           'condition': 'delay={}'.format(tuple2[0] - tuple1[0]),
           'value': 2})

    return stimu_mecha_timestamps, stimu_elec_timestamps, \
        is_active_timestamps, position_timestamps

  def _plot_protocol(self,
                     stimu_mecha_timestamps: list,
                     stimu_elec_timestamps: list,
                     is_active_timestamps: list,
                     position_timestamps: list) -> None:
    """

    Args:
      stimu_mecha_timestamps: The timestamps indicating when the mechanical
        stimulation is active.
      stimu_elec_timestamps: The timestamps indicating when the electrical
        stimulation is active.
      is_active_timestamps: The timestamps indicating when at least one of the
        stimulation is active.
      position_timestamps: The positions of the movable pin and their
        timestamps.
    """

    matplotlib.use('TkAgg')
    current_time = datetime.datetime.now()

    stimu_mecha_graph = [[current_time +
                          datetime.timedelta(stimu_mecha_timestamps[0][0])],
                         [stimu_mecha_timestamps[0][1]]]
    position_graph = [[current_time +
                       datetime.timedelta(position_timestamps[0][0])],
                      [position_timestamps[0][1]]]
    stimu_elec_graph = [[current_time +
                         datetime.timedelta(stimu_elec_timestamps[0][0])],
                        [stimu_elec_timestamps[0][1]]]

    if self._mecha_stimu:
      for t, value in stimu_mecha_timestamps[1:]:
        stimu_mecha_graph[0].append(current_time +
                                    datetime.timedelta(seconds=t - 0.001))
        stimu_mecha_graph[0].append(current_time +
                                    datetime.timedelta(seconds=t))
        stimu_mecha_graph[1].append(stimu_mecha_graph[1][-1])
        stimu_mecha_graph[1].append(value)

      for t, value in position_timestamps[1:]:
        position_graph[0].append(current_time +
                                 datetime.timedelta(seconds=t - 0.001))
        position_graph[0].append(current_time + datetime.timedelta(seconds=t))
        position_graph[1].append(position_graph[1][-1])
        position_graph[1].append(value)

    if self._elec_stimu:
      for t, value in stimu_elec_timestamps[1:]:
        stimu_elec_graph[0].append(current_time +
                                   datetime.timedelta(seconds=t - 0.001))
        stimu_elec_graph[0].append(current_time +
                                   datetime.timedelta(seconds=t))
        stimu_elec_graph[1].append(stimu_elec_graph[1][-1])
        stimu_elec_graph[1].append(value)

    is_active_graph = [[current_time +
                        datetime.timedelta(is_active_timestamps[0][0])],
                       [is_active_timestamps[0][1]]]
    for t, value in is_active_timestamps[1:]:
      is_active_graph[0].append(current_time +
                                datetime.timedelta(seconds=t - 0.001))
      is_active_graph[0].append(current_time + datetime.timedelta(seconds=t))
      is_active_graph[1].append(is_active_graph[1][-1])
      is_active_graph[1].append(value)

    plt.figure()
    if self._elec_stimu and self._mecha_stimu:
      plt.subplot(211)
      plt.title("Movable pin position")
      plt.ylabel("Position (mm)")
      plt.plot(position_graph[0], position_graph[1])
      plt.subplot(212)
      plt.title("Stimulation active")
      plt.ylabel("1 stimulating, 0 resting")
      plt.plot(stimu_mecha_graph[0], stimu_mecha_graph[1])
      plt.plot(stimu_elec_graph[0], stimu_elec_graph[1])
      plt.legend(['Mechanical',
                  'Electrical'])
    elif self._elec_stimu:
      plt.plot(stimu_elec_graph[0], stimu_elec_graph[1])
      plt.title("Electrical stimulation")
    else:
      plt.title("Mechanical stimulation")
      plt.plot(position_graph[0], position_graph[1])
      plt.plot(stimu_mecha_graph[0], stimu_mecha_graph[1])
      plt.legend(['Position', 'Activity'])

    plt.figure()
    plt.title("Overview of medium refreshment times")
    plt.ylabel("1 stimulating, 0 resting")
    plt.plot(is_active_graph[0], is_active_graph[1])

    plt.show()
