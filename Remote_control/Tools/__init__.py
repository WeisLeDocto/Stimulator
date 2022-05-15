# coding: utf-8

from typing import Optional
from pathlib import Path
from re import fullmatch

from ._Protocol_phases import Protocol_phases, Protocol_parameters
try:
  from ._Protocol_builder import Protocol_builder
except (ModuleNotFoundError, ImportError):
  pass


def get_protocol_name(file: Path) -> Optional[str]:
  """Returns the name of the protocol located in a given .py file if it matches
  the right syntax, else returns None."""

  match = fullmatch(r'Protocol_(?P<name>.+)\.py', file.name)
  return match.group('name') if match is not None else None
