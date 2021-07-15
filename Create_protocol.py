# coding: utf-8

from Remote_control import Protocol_builder
from PyQt5.QtWidgets import QApplication
import sys

if __name__ == '__main__':

  app = QApplication(sys.argv)
  Protocol_builder(app)()
  sys.exit(app.exec_())

