# coding: utf-8

from Remote_control import Daemon_run
from daemon import DaemonContext
from pathlib import Path

if __name__ == "__main__":
  with DaemonContext(working_directory=Path.cwd()):
    Daemon_run(1148)()
