# coding: utf-8

from Remote_control import Stimulation_protocol

if __name__ == '__main__':

  new_prot = Stimulation_protocol()

  # First 24 hours resting phase
  new_prot.add_mechanical_rest(resting_position_mm=0,
                               rest_duration_hours=24)

  new_prot.add_electrical_rest(rest_duration_hours=24)

  # Continuous stretching only
  new_prot.add_continuous_stretching(travel_length_mm=2,
                                     resting_time_ratio=0.25,
                                     consecutive_stretch_duration_hours=1.5,
                                     total_duration_hours=4 * 24)

  new_prot.add_electrical_rest(rest_duration_hours=4 * 24)

  # 3 days resting phase
  new_prot.add_electrical_rest(rest_duration_hours=3 * 24)

  new_prot.add_mechanical_rest(rest_duration_hours=3 * 24,
                               resting_position_mm=2)

  # Beginning electrical stimulation and slowly increasing mechanical
  # stimulation
  for n in range(2 * 24 * 8):
    new_prot.add_cyclic_stretching(resting_position_mm=2,
                                   stretched_position_mm=2 + 2 * (n + 1) /
                                   (2 * 24 * 8),
                                   number_of_cycles=5,
                                   number_of_reps=3,
                                   time_to_reach_position_seconds=2,
                                   number_of_sets=1,
                                   rest_between_sets_minutes=28,
                                   rest_between_cycles_minutes=0.5)

  new_prot.add_electrical_stimulation(pulse_duration_seconds=0.01,
                                      delay_between_pulses_seconds=1,
                                      set_duration_minutes=60,
                                      rest_between_sets_minutes=5 * 60,
                                      number_of_sets=4 * 8)

  new_prot.save_protocol("Continuous_stretching")
