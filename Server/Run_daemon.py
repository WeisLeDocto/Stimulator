# coding: utf-8

from os.path import abspath, dirname
import daemon
from _Daemon import Daemon_run

if __name__ == "__main__":
  # with daemon.DaemonContext(working_directory=dirname(abspath(__file__))):
  Daemon_run(1148)()
