# coding: utf-8

from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.widgets import TextBox
from typing import List, Optional, Tuple, Any, Union, Dict
from dataclasses import dataclass, field
from collections import OrderedDict


cyclic_stretching_steady = {'rest_position_mm': float,
                            'stretched_position_mm': float,
                            'number_of_cycles': int,
                            'number_of_reps': int,
                            'number_of_sets': int,
                            'time_to_reach_position_seconds': float,
                            'rest_between_reps_minutes': float,
                            'rest_between_sets_minutes': float}

cyclic_stretching_progressive = {'rest_position_mm': float,
                                 'first_stretched_position_mm': float,
                                 'last_stretched_position_mm': float,
                                 'number_of_cycles': int,
                                 'number_of_reps': int,
                                 'number_of_sets': int,
                                 'time_to_reach_position_seconds': float,
                                 'rest_between_reps_minutes': float,
                                 'rest_between_sets_minutes': float}

mechanical_rest = {'rest_duration_hours': float,
                   'rest_position_mm': float}

electrical_rest = {'rest_duration_hours': float}

electrical_stimulation = {'pulse_duration_seconds': float,
                          'set_duration_minutes': float,
                          'delay_between_pulses_seconds': float,
                          'rest_between_sets_minutes': float,
                          'number_of_sets': int}


Protocol_parameters = {"Add cyclic stretching (steady)":
                       cyclic_stretching_steady,
                       "Add cyclic stretching (progressive)":
                       cyclic_stretching_progressive,
                       "Add mechanical rest": mechanical_rest,
                       "Add electrical rest": electrical_rest,
                       "Add electrical stimulation": electrical_stimulation}


@dataclass
class Data_vs_time:
  """"""

  timestamps: List[Union[datetime, float]] = field(default_factory=list)
  values: List[Any] = field(default_factory=list)

  _index: int = -1

  def __add__(self, other):
    return Data_vs_time(timestamps=self.timestamps + other.timestamps,
                        values=self.values + other.values)

  def __len__(self):
    return len(self.values)

  def parse_raw_data(self,
                     data: List[Tuple[float, Union[float, bool]]],
                     init: Optional[Union[float, bool]] = None) -> None:
    """"""

    if not data:
      return

    # Initializing the lists
    timestamps = [0.]
    values = [data[0][1]] if init is None else [init]

    # Filling the lists
    for (t, _), (_, value) in zip(data[:-1], data[1:]):
      last_t = timestamps[-1]
      timestamps.append(t + last_t)
      values.append(value)

    # Saving the list as the new data of the class
    self.timestamps = timestamps
    self.values = values

  def remove_redundant(self) -> None:
    """"""

    # Getting the indexes of the duplicate values
    to_remove = []
    for i, (value1, value2) in enumerate(zip(self.values[:-1],
                                             self.values[1:])):
      if value1 == value2:
        to_remove.append(i + 1)

    # Removing the values at the given indexes from the lists
    to_remove.reverse()
    for i in to_remove:
      del self.timestamps[i]
      del self.values[i]

  def make_curve(self, current_time: datetime):
    """"""

    if len(self) <= 1:
      return

    curve_data = Data_vs_time(
      timestamps=[current_time + timedelta(self.timestamps[0])],
      values=[self.values[0]])

    for t, val in zip(self.timestamps[1:], self.values[1:]):
      curve_data.timestamps.append(current_time + timedelta(seconds=t))
      curve_data.values.append(curve_data.values[-1])
      curve_data.timestamps.append(current_time + timedelta(seconds=t))
      curve_data.values.append(val)

    return curve_data


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

    self._step_mm: float = full_step_per_mm
    self._step_mode: int = step_mode
    self._time_orange_on_secs: float = time_orange_on_minutes * 60

    self._mecha_dicts: List[Dict[str, Any]] = list()
    self._elec_dicts: List[Dict[str, Any]] = list()
    self._mecha_stimu_on: List[Tuple[float, bool]] = list()
    self._elec_stimu_on: List[Tuple[float, bool]] = list()
    self._position: List[Tuple[float, float]] = list()

    self.py_file = ["# coding: utf-8" + "\n\n",
                    "from Remote_control.Tools import Protocol_phases\n\n",
                    "new_prot = Protocol_phases()\n\n"]

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
    consecutive_duration_seconds = consecutive_stretch_duration_hours * 60 * 60
    delay_between_steps = (
        total_duration_hours * 60 * 60 * (1 - resting_time_ratio) /
        self._step_mm / self._step_mode / abs(travel_length_mm))
    step_length = 1 / self._step_mm / self._step_mode
    number_of_steps = int(abs(travel_length_mm) *
                          self._step_mode * self._step_mm)

    # Adding positions step by step, and adding a resting phase when needed
    time_count = 0
    for i in range(number_of_steps):
      self._add_mecha(position=i * step_length,
                      delay=delay_between_steps,
                      is_active=True)
      time_count += delay_between_steps
      if time_count > consecutive_duration_seconds:
        time_count -= consecutive_duration_seconds
        self._add_mecha(position=i * step_length,
                        delay=round((1 / (1 - resting_time_ratio) - 1) *
                                    consecutive_duration_seconds),
                        is_active=False)

    self.py_file.extend(f"new_prot.add_continuous_stretching("
                        f"{travel_length_mm}, {resting_time_ratio}, "
                        f"{consecutive_stretch_duration_hours}, "
                        f"{total_duration_hours})\n\n")

  def add_cyclic_stretching_steady(self,
                                   rest_position_mm: float,
                                   stretched_position_mm: float,
                                   number_of_cycles: int,
                                   number_of_reps: int,
                                   number_of_sets: int,
                                   time_to_reach_position_seconds: float,
                                   rest_between_reps_minutes: float,
                                   rest_between_sets_minutes: float) -> None:
    """Adds a cyclic stretching phase, during which the muscle is being
    stretched in a cyclic way.

    The cyclic stretching is split in sets, separated by resting phases. Each
    set counts several reps, also separated by resting phases. And each rep
    consists in a given number of cycles, with no rest between cycles.

    Args:
      rest_position_mm: The position of the pin during resting phases.
      stretched_position_mm: The target position of the pin when muscle is
        stretched.
      number_of_cycles: The number of cycles during a rep.
      number_of_reps: The number of reps during a set.
      number_of_sets: The number of sets.
      time_to_reach_position_seconds: The delay between a command to go to
        stretched position and a command to return to resting position during a
        cycle. Depending on speed, the pin may not have time to reach the target
        position and the actual stretched position is then less than expected.
      rest_between_reps_minutes: The resting time between reps.
      rest_between_sets_minutes: The resting time between sets.
    """

    for _ in range(number_of_sets):
      for i in range(number_of_reps):
        for _ in range(number_of_cycles):
          self._add_mecha(position=stretched_position_mm,
                          delay=time_to_reach_position_seconds,
                          is_active=True)
          self._add_mecha(position=rest_position_mm,
                          delay=time_to_reach_position_seconds,
                          is_active=True)
        if i != number_of_reps - 1:
          self._add_mecha(position=rest_position_mm,
                          delay=rest_between_reps_minutes * 60,
                          is_active=False)
      self._add_mecha(position=rest_position_mm,
                      delay=rest_between_sets_minutes * 60,
                      is_active=False)

    self.py_file.extend(f"new_prot.add_cyclic_stretching_steady("
                        f"{rest_position_mm}, {stretched_position_mm}, "
                        f"{number_of_cycles}, {number_of_reps}, "
                        f"{time_to_reach_position_seconds}, {number_of_sets}, "
                        f"{rest_between_sets_minutes}, "
                        f"{rest_between_reps_minutes})\n\n")

  def add_cyclic_stretching_progressive(
      self,
      rest_position_mm: float,
      first_stretched_position_mm: float,
      last_stretched_position_mm: float,
      number_of_cycles: int,
      number_of_reps: int,
      number_of_sets: int,
      time_to_reach_position_seconds: float,
      rest_between_reps_minutes: float,
      rest_between_sets_minutes: float) -> None:
    """Adds a cyclic stretching phase, during which the muscle is being
    stretched in a cyclic way.

    The distance over which the movable pin is moving changes in a linear
    fashion from one set to the next, from the first value to the last. All the
    cycles of a given set move the pin by the same distance.

    The cyclic stretching is split in sets, separated by resting phases. Each
    set counts several reps, also separated by resting phases. And each rep
    consists in a given number of cycles, with no rest between cycles.

    Args:
      rest_position_mm: The position of the pin during resting phases.
      first_stretched_position_mm: The target position of the pin when muscle is
        stretched, at the beginning of the stretching cycle.
      last_stretched_position_mm: The target position of the pin when muscle is
        stretched, at the end of the stretching cycle.
      number_of_cycles: The number of cycles during a rep.
      number_of_reps: The number of reps during a set.
      number_of_sets: The number of sets.
      time_to_reach_position_seconds: The delay between a command to go to
        stretched position and a command to return to resting position during a
        cycle. Depending on speed, the pin may not have time to reach the target
        position and the actual stretched position is then less than expected.
      rest_between_reps_minutes: The resting time between cycles.
      rest_between_sets_minutes: The resting time between sets.
    """

    for j in range(number_of_sets):
      position = (first_stretched_position_mm + j *
                  (last_stretched_position_mm - first_stretched_position_mm)
                  / (number_of_sets - 1))
      for i in range(number_of_reps):
        for _ in range(number_of_cycles):
          self._add_mecha(position=position,
                          delay=time_to_reach_position_seconds,
                          is_active=True)
          self._add_mecha(position=rest_position_mm,
                          delay=time_to_reach_position_seconds,
                          is_active=True)
        if i != number_of_reps - 1:
          self._add_mecha(position=rest_position_mm,
                          delay=rest_between_reps_minutes * 60,
                          is_active=False)
      self._add_mecha(position=rest_position_mm,
                      delay=rest_between_sets_minutes * 60,
                      is_active=False)

    self.py_file.extend(f"new_prot.add_cyclic_stretching_progressive("
                        f"{rest_position_mm}, {first_stretched_position_mm}, "
                        f"{last_stretched_position_mm}, {number_of_cycles}, "
                        f"{number_of_reps}, {time_to_reach_position_seconds}, "
                        f"{number_of_sets}, {rest_between_sets_minutes}, "
                        f"{rest_between_reps_minutes})\n\n")

  def add_mechanical_rest(self,
                          rest_duration_hours: float,
                          rest_position_mm: float) -> None:
    """Adds a mechanical resting phase.

    Args:
      rest_duration_hours: The resting phase duration.
      rest_position_mm: The position to hold during the resting phase.
    """

    self._add_mecha(position=rest_position_mm,
                    delay=rest_duration_hours * 60 * 60,
                    is_active=False)

    self.py_file.extend(f"new_prot.add_mechanical_rest({rest_duration_hours}, "
                        f"{rest_position_mm})\n\n")

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
      pulse_duration_seconds: The duration of a pulse.
      set_duration_minutes: The duration of a set.
      delay_between_pulses_seconds: A pulse is sent once every this value
        seconds.
      rest_between_sets_minutes: The delay between two sets.
      number_of_sets: The number of sets.
    """

    pulses_per_set = round(set_duration_minutes * 60 /
                           delay_between_pulses_seconds)
    for _ in range(number_of_sets):
      self._elec_dicts.append(
        {'type': 'cyclic', 'value1': 0,
         'condition1':
         f'delay={delay_between_pulses_seconds - pulse_duration_seconds}',
         'value2': 1,
         'condition2': f'delay={pulse_duration_seconds}',
         'cycles': pulses_per_set})
      self._elec_stimu_on.append((set_duration_minutes * 60, True))
      self._elec_dicts.append(
        {'type': 'constant',
         'condition': f'delay={rest_between_sets_minutes * 60}',
         'value': 0})
      self._elec_stimu_on.append((rest_between_sets_minutes * 60, False))

    self.py_file.extend(f"new_prot.add_electrical_stimulation("
                        f"{pulse_duration_seconds}, {set_duration_minutes}, "
                        f"{delay_between_pulses_seconds}, "
                        f"{rest_between_sets_minutes}, {number_of_sets})\n\n")

  def add_electrical_rest(self, rest_duration_hours: float) -> None:
    """Adds an electrical resting phase, during which no current flows in the
    electrodes.

    Args:
      rest_duration_hours: The resting phase duration.
    """

    self._elec_dicts.append(
      {'type': 'constant',
       'condition': f'delay={rest_duration_hours * 60 * 60}',
       'value': 0})
    self._elec_stimu_on.append((rest_duration_hours * 60 * 60, False))

    self.py_file.extend(f"new_prot.add_electrical_rest("
                        f"{rest_duration_hours})\n\n")

  def reset_protocol(self) -> None:
    """Resets the lists containing the protocol details."""

    self._mecha_dicts.clear()
    self._elec_dicts.clear()
    self._mecha_stimu_on.clear()
    self._elec_stimu_on.clear()
    self._position.clear()

    self.py_file = ["# coding: utf-8" + "\n\n",
                    "from Remote_control.Tools import Protocol_phases\n\n",
                    "new_prot = Protocol_phases()\n\n"]

  def export(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
                            List[Dict[str, Any]]]:
    """Generates the lists the stimulation program takes as inputs, and returns
    them.

    Returns:
      The lists for driving the Crappy Generators.
    """

    _, _, is_active, _ = self._parse_protocols()
    list_led = self._build_led_list(is_active)
    return list_led, self._mecha_dicts, self._elec_dicts

  def plot_protocol(self) -> None:
    """Plots the movable pin position, the moments when the electrical and
    mechanical stimulation are on, and the moments when either of them is on."""

    plt.ioff()

    mecha_on, elec_on, is_active, position = self._parse_protocols()
    current_time = datetime.now()

    stimu_mecha_graph = mecha_on.make_curve(current_time)
    position_graph = position.make_curve(current_time)

    stimu_elec_graph = elec_on.make_curve(current_time)

    is_active_graph = is_active.make_curve(current_time)

    self._plot_curves(position_graph, stimu_mecha_graph,
                      stimu_elec_graph, is_active_graph)

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

    self._mecha_dicts.append({'type': 'constant',
                              'condition': f'delay={delay}',
                              'value': position})
    self._mecha_stimu_on.append((delay, is_active))
    self._position.append((delay, position))

  def _parse_protocols(self) -> Tuple[Data_vs_time, Data_vs_time,
                                      Data_vs_time, Data_vs_time]:
    """"""

    mecha_on = Data_vs_time()
    mecha_on.parse_raw_data(self._mecha_stimu_on)
    mecha_on.remove_redundant()

    elec_on = Data_vs_time()
    elec_on.parse_raw_data(self._elec_stimu_on)
    elec_on.remove_redundant()

    position = Data_vs_time()
    position.parse_raw_data(self._position, init=0)

    any_on = mecha_on + elec_on
    sorted_any_on = OrderedDict(sorted(zip(any_on.timestamps, any_on.values)))
    any_on.timestamps = list(sorted_any_on.keys())
    any_on.values = list(sorted_any_on.values())

    return mecha_on, elec_on, any_on, position

  def _build_led_list(self, is_active: Data_vs_time) -> List[Dict[str, Any]]:
    """"""

    # Building the list of dictionaries for driving the LED
    list_led = []
    for val, t1, t2 in zip(is_active.values[:-1], is_active.timestamps[:-1],
                           is_active.timestamps[1:]):
      if not val and ((t2 - t1) > self._time_orange_on_secs):
        list_led.append(
          {'type': 'constant',
           'condition': f'delay={(t2 - t1) - self._time_orange_on_secs}',
           'value': 0})
        list_led.append(
          {'type': 'constant',
           'condition': f'delay={self._time_orange_on_secs}',
           'value': 1})
      else:
        list_led.append(
          {'type': 'constant',
           'condition': f'delay={t2 - t1}',
           'value': 2})

    return list_led

  @staticmethod
  def _plot_curves(position: Optional[Data_vs_time],
                   mecha: Optional[Data_vs_time],
                   elec: Optional[Data_vs_time],
                   is_active: Optional[Data_vs_time]) -> None:
    """"""

    fig = plt.figure(0)
    if elec is not None and mecha is not None:
      plt.subplot(211)
      plt.title("Movable pin position")
      plt.ylabel("Position (mm)")
      plt.plot(position.timestamps, position.values)

      plt.subplot(212)
      plt.title("Stimulation active")
      plt.ylabel("1 stimulating, 0 resting")
      plt.plot(mecha.timestamps, mecha.values)
      plt.plot(elec.timestamps, elec.values)
      plt.legend(['Mechanical', 'Electrical'])

    elif elec is not None:
      plt.title("Electrical stimulation")
      plt.plot(elec.timestamps, elec.values)

    elif mecha is not None:
      plt.title("Mechanical stimulation")
      plt.plot(position.timestamps, position.values)
      plt.plot(mecha.timestamps, mecha.values)
      plt.legend(['Position', 'Activity'])

    else:
      plt.subplot()
      ax = fig.axes[0]
      TextBox(ax, '', 'Cannot display the protocol, it is only resting...')
      plt.show()
      return

    plt.figure(1)
    plt.title("Overview of medium refreshment times")
    plt.ylabel("1 stimulating, 0 resting")
    plt.plot(is_active.timestamps, is_active.values)

    plt.show()
