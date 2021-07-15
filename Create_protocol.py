# coding: utf-8

from Remote_control import Protocol_builder
try:
  from PyQt5.QtWidgets import QApplication
except ModuleNotFoundError:
  pass
import sys

if __name__ == '__main__':

  app = QApplication(sys.argv)
  Protocol_builder(app)()
  sys.exit(app.exec_())

