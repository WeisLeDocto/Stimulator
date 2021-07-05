# coding: utf-8

from Remote_control import Daemon_run
import daemon
from os.path import dirname, abspath

if __name__ == "__main__":
  with daemon.DaemonContext(working_directory=dirname(abspath(__file__))):
    Daemon_run(1148)()
