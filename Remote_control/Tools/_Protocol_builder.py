# coding: utf-8

from ._Protocol_phases import Protocol_phases, Protocol_parameters
from functools import partial
from pathlib import Path
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QListWidget
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QStyle
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QDialogButtonBox
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QSpinBox
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QMessageBox

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QDoubleValidator


class Show_param_dialog(QDialog):
  """Class for displaying the characteristics of a protocol phase when
  double-clicking on it."""

  def __init__(self, parent, text, values) -> None:
    """Sets the layout and displays the window.

    Args:
      parent: The parent widget.
      text: The text of the button clicked for creating this phase. Used for
        retrieving the fields names.
      values: The list of the fields values, in the right order.
    """

    super().__init__(parent=parent)
    self.setWindowTitle("Phase description")
    main_layout = QVBoxLayout()
    self.setLayout(main_layout)

    display = QLabel("Parameters for the selected phase :")
    display.setStyleSheet("font-weight: bold")
    main_layout.addWidget(display)

    fields_layout = QHBoxLayout()

    # Parameter name on the left, value on the right
    left_layout = QVBoxLayout()
    right_layout = QVBoxLayout()

    # Rearranging the name for a nicer display
    for (param, typ), value in zip(Protocol_parameters[text].items(), values):
      text_list = param.capitalize().replace('_', ' ').split()
      text_str = ' '.join(text_list[:-1] + ['(' + text_list[-1] + ')']
                          if typ is float else text_list)
      left_layout.addWidget(QLabel(text_str + " :"))
      right_layout.addWidget(QLabel(str(value)))

    fields_layout.addLayout(left_layout)
    fields_layout.addLayout(right_layout)

    main_layout.addLayout(fields_layout)

    # Button for exiting
    button = QDialogButtonBox(
      QDialogButtonBox.StandardButton(QDialogButtonBox.Ok))

    button.accepted.connect(self.accept)

    main_layout.addWidget(button)

    self.exec_()


class Param_dialog(QDialog):
  """A class for displaying a window allowing the user to choose the parameters
  for a given protocol phase."""

  def __init__(self, parent, text) -> None:
    """Sets the layout and displays the window.

    Args:
      parent: The parent widget.
      text: The text of the button clicked for creating this phase. Used for
        retrieving the fields names and types.
    """

    super().__init__(parent=parent)
    self.setWindowTitle("Phase parameters")
    main_layout = QVBoxLayout()
    self.setLayout(main_layout)

    self.field_list = []
    self.validation_list = []

    double_validator = QDoubleValidator(0, 10000000, 100)

    display = QLabel("Please enter the phase parameters :")
    display.setStyleSheet("font-weight: bold")
    main_layout.addWidget(display)

    fields_layout = QHBoxLayout()

    # Parameter name on the left, value in the middle, warning message on the
    # right
    left_layout = QVBoxLayout()
    center_layout = QVBoxLayout()
    right_layout = QVBoxLayout()

    # Rearranging the name for a nicer display
    for param, typ in Protocol_parameters[text].items():
      text_list = param.capitalize().replace('_', ' ').split()
      text_str = ' '.join(text_list[:-1] + ['(' + text_list[-1] + ')']
                          if typ is float else text_list)
      left_layout.addWidget(QLabel(text_str + " :"))
      self.field_list.append(QLineEdit() if typ is float else QSpinBox())
      self.validation_list.append(QLabel(""))
      if isinstance(self.field_list[-1], QLineEdit):
        self.field_list[-1].setValidator(double_validator)
      center_layout.addWidget(self.field_list[-1])
      right_layout.addWidget(self.validation_list[-1])

    fields_layout.addLayout(left_layout)
    fields_layout.addLayout(center_layout)
    fields_layout.addLayout(right_layout)

    main_layout.addLayout(fields_layout)

    # Button for exiting and validating
    buttons = QDialogButtonBox(
      QDialogButtonBox.StandardButton(QDialogButtonBox.Save |
                                      QDialogButtonBox.Cancel))

    buttons.accepted.connect(self.check_acceptability)
    buttons.rejected.connect(self.reject)

    main_layout.addWidget(buttons)

  def return_values(self) -> list:
    """Gets the parameter values.

    Returns:
      The list of the parameter values, in the right order.
    """

    # Replacing , by . in case the system separator is a ,
    return [field.value() if isinstance(field, QSpinBox)
            else float(field.text().replace(',', '.'))
            for field in self.field_list]

  def check_acceptability(self) -> None:
    """Checks if all the fields have been filled out, and with appropriate
    values. If not, displays a warning message."""

    # using a flag rather than a break because we want all the warning messages
    # to be displayed
    valid = True
    for i, field in enumerate(self.field_list):
      if isinstance(field, QLineEdit) and \
            field.validator().validate(field.text(), 0)[0] != 2:
        self.validation_list[i].setText("Invalid input !")
        self.validation_list[i].setStyleSheet("color: red;")
        valid = False
      elif isinstance(field, QSpinBox) and field.value() == 0:
        self.validation_list[i].setText("Invalid input !")
        self.validation_list[i].setStyleSheet("color: red;")
        valid = False
      else:
        self.validation_list[i].setText("")
        self.validation_list[i].setStyleSheet("color: black;")
    if valid:
      self.accept()


class Phase(QListWidgetItem):
  """Subclass of QListWidgetItem with the extra attributes values and txt."""

  def __init__(self, text, values) -> None:
    super().__init__()
    self.setText(text.replace('Add ', '').capitalize())
    self.values = values
    self.txt = text


class Protocol_builder(QMainWindow):
  """Class for displaying a graphical interface in which the user can create and
  visualize stimulation protocols."""

  def __init__(self, app) -> None:
    """Sets instance attributes.

    Args:
      app: The parent QApplication.
    """

    super().__init__()
    self._app = app
    self._protocol = Protocol_phases()

  def __call__(self) -> None:
    """Sets the layout and shows the interface."""

    self._set_layout()

    self._set_connections()

    # Places the window in the center of the screen
    delta_x = int((self._app.desktop().availableGeometry().width() -
                   self.width()) / 2)
    delta_y = int((self._app.desktop().availableGeometry().height() -
                   self.height()) / 2)
    self.move(delta_x, delta_y)
    self.show()

  def _set_layout(self) -> None:
    """Creates the widgets and places them in the main window."""

    self.setWindowTitle('Protocol builder')

    # General layout
    self._generalLayout = QVBoxLayout()
    self._centralWidget = QWidget(self)
    self.setCentralWidget(self._centralWidget)
    self._centralWidget.setLayout(self._generalLayout)

    self._gap = QLabel("")

    self._fields_layout = QHBoxLayout()

    self._mecha_layout = QVBoxLayout()

    # Mechanical protocol phases
    self._mecha_title = QLabel("Mechanical stimulation")
    self._mecha_title.setAlignment(Qt.AlignCenter)
    self._mecha_title.setStyleSheet("font-weight: bold")
    self._mecha_layout.addWidget(self._mecha_title)

    self._list_mecha = QListWidget()
    self._mecha_layout.addWidget(self._list_mecha)

    self._add_mecha_resting = QPushButton("Add mechanical rest")
    self._mecha_layout.addWidget(self._add_mecha_resting)

    self._add_mecha_cyclic_progressive = QPushButton("Add cyclic stretching "
                                                     "(progressive)")
    self._mecha_layout.addWidget(self._add_mecha_cyclic_progressive)

    self._add_mecha_cyclic_steady = QPushButton("Add cyclic stretching "
                                                "(steady)")
    self._mecha_layout.addWidget(self._add_mecha_cyclic_steady)

    self._mecha_layout.addWidget(self._gap)

    # Mechanical list organization
    self._remove_mecha = QPushButton("Remove item")
    self._mecha_layout.addWidget(self._remove_mecha)
    self._remove_mecha.setIcon(self.style().standardIcon(
      QStyle.SP_BrowserStop))
    self._remove_mecha.setIconSize(QSize(12, 12))

    self._move_up_mecha = QPushButton("Move item up")
    self._mecha_layout.addWidget(self._move_up_mecha)
    self._move_up_mecha.setIcon(self.style().standardIcon(
      QStyle.SP_ArrowUp))
    self._move_up_mecha.setIconSize(QSize(12, 12))

    self._move_down_mecha = QPushButton("Move item down")
    self._mecha_layout.addWidget(self._move_down_mecha)
    self._move_down_mecha.setIcon(self.style().standardIcon(
      QStyle.SP_ArrowDown))
    self._move_down_mecha.setIconSize(QSize(12, 12))

    # Electrical protocol phases
    self._elec_layout = QVBoxLayout()

    self._elec_title = QLabel("Electrical stimulation")
    self._elec_title.setAlignment(Qt.AlignCenter)
    self._elec_title.setStyleSheet("font-weight: bold")
    self._elec_layout.addWidget(self._elec_title)

    self._list_elec = QListWidget()
    self._elec_layout.addWidget(self._list_elec)

    self._add_elec_resting = QPushButton("Add electrical rest")
    self._elec_layout.addWidget(self._add_elec_resting)

    self._add_elec_stimu = QPushButton("Add electrical stimulation")
    self._elec_layout.addWidget(self._add_elec_stimu)

    self._elec_layout.addWidget(self._gap)

    # Electrical list organization
    self._remove_elec = QPushButton("Remove item")
    self._elec_layout.addWidget(self._remove_elec)
    self._remove_elec.setIcon(self.style().standardIcon(
      QStyle.SP_BrowserStop))
    self._remove_elec.setIconSize(QSize(12, 12))

    self._move_up_elec = QPushButton("Move item up")
    self._elec_layout.addWidget(self._move_up_elec)
    self._move_up_elec.setIcon(self.style().standardIcon(
      QStyle.SP_ArrowUp))
    self._move_up_elec.setIconSize(QSize(12, 12))

    self._move_down_elec = QPushButton("Move item down")
    self._elec_layout.addWidget(self._move_down_elec)
    self._move_down_elec.setIcon(self.style().standardIcon(
      QStyle.SP_ArrowDown))
    self._move_down_elec.setIconSize(QSize(12, 12))

    self._fields_layout.addLayout(self._mecha_layout)
    self._fields_layout.addLayout(self._elec_layout)

    # Buttons for exiting, validating and displaying
    self._buttons = QDialogButtonBox(
      QDialogButtonBox.StandardButton(QDialogButtonBox.Save |
                                      QDialogButtonBox.Cancel))
    self._buttons.addButton("Show protocol", QDialogButtonBox.HelpRole)

    self._generalLayout.addLayout(self._fields_layout)
    self._generalLayout.addWidget(self._buttons)

  def _set_connections(self) -> None:
    """Sets the actions to perform when interacting with the widgets."""

    self._add_elec_resting.clicked.connect(
      partial(self._add_item, self._list_elec, self._add_elec_resting.text()))

    self._add_elec_stimu.clicked.connect(
      partial(self._add_item, self._list_elec, self._add_elec_stimu.text()))

    self._remove_elec.clicked.connect(
      partial(self._remove_item, self._list_elec))

    self._move_down_elec.clicked.connect(
      partial(self._move_item, 1, self._list_elec))

    self._move_up_elec.clicked.connect(
      partial(self._move_item, -1, self._list_elec))

    self._add_mecha_resting.clicked.connect(
      partial(self._add_item, self._list_mecha, self._add_mecha_resting.text()))

    self._add_mecha_cyclic_progressive.clicked.connect(
      partial(self._add_item, self._list_mecha,
              self._add_mecha_cyclic_progressive.text()))

    self._add_mecha_cyclic_steady.clicked.connect(
      partial(self._add_item, self._list_mecha,
              self._add_mecha_cyclic_steady.text()))

    self._remove_mecha.clicked.connect(
      partial(self._remove_item, self._list_mecha))

    self._move_down_mecha.clicked.connect(
      partial(self._move_item, 1, self._list_mecha))

    self._move_up_mecha.clicked.connect(
      partial(self._move_item, -1, self._list_mecha))

    self._list_elec.itemDoubleClicked.connect(
      partial(self._show_item, self._list_elec))

    self._list_mecha.itemDoubleClicked.connect(
      partial(self._show_item, self._list_mecha))

    self._buttons.rejected.connect(self.close)
    self._buttons.accepted.connect(self._save_protocol)
    self._buttons.helpRequested.connect(self._show_graphs)

  def _show_graphs(self) -> None:
    """Displays graphs for visualizing the current protocol."""

    # Aborting if there's nothing to display
    if self._list_elec.count() == 0 and self._list_mecha.count() == 0:
      mes_box = QMessageBox(QMessageBox.Warning,
                            "Warning !",
                            "The protocol is empty !")
      mes_box.setStandardButtons(QMessageBox.Ok)
      mes_box.exec()
      return

    # Rebuilds the internal protocol lists
    self._protocol.reset_protocol()

    for i in range(self._list_elec.count()):
      phase = self._list_elec.item(i)
      txt = phase.txt.lower().replace('(', '').replace(')', '')\
          .replace(' ', '_')
      meth = getattr(self._protocol, txt)
      meth(*phase.values)

    for i in range(self._list_mecha.count()):
      phase = self._list_mecha.item(i)
      txt = phase.txt.lower().replace('(', '').replace(')', '')\
          .replace(' ', '_')
      meth = getattr(self._protocol, txt)
      meth(*phase.values)

    self._protocol.plot_protocol()

  def _save_protocol(self):
    """Saves the current protocol to the Protocols/ directory."""

    # Aborting if there's nothing to save
    if self._list_elec.count() == 0 and self._list_mecha.count() == 0:
      mes_box = QMessageBox(QMessageBox.Warning,
                            "Warning !",
                            "The protocol is empty !")
      mes_box.setStandardButtons(QMessageBox.Ok)
      mes_box.exec()
      return

    # Rebuilds the internal protocol lists
    self._protocol.reset_protocol()

    for i in range(self._list_elec.count()):
      phase = self._list_elec.item(i)
      txt = phase.txt.lower().replace('(', '').replace(')', '') \
          .replace(' ', '_')
      meth = getattr(self._protocol, txt)
      meth(*phase.values)

    for i in range(self._list_mecha.count()):
      phase = self._list_mecha.item(i)
      txt = phase.txt.lower().replace('(', '').replace(')', '') \
          .replace(' ', '_')
      meth = getattr(self._protocol, txt)
      meth(*phase.values)

    # Setting a name for the protocol
    name, ok = QInputDialog.getText(self,
                                    "Protocol name",
                                    "Please enter the name of the protocol :")
    name = name.replace(' ', '_')

    # Actually writing the protocol .py file
    if ok:
      path = Path.cwd().parent

      if not Path.exists(path / "Protocols"):
        Path.mkdir(path / "Protocols")
        with open(path / "Protocols" / "__init__.py", 'w') as init_file:
          init_file.write("# coding: utf-8" + "\n")
          init_file.write("\n")
          init_file.write(
            "from .Protocol_" + name + " import Led, Mecha, Elec"
            + "\n")

      with open(path / "Protocols" / ("Protocol_" + name +
                                      ".py"), 'w') as exported_file:
        for line in self._protocol.py_file:
          exported_file.write(line)

        exported_file.write("Led, Mecha, Elec = new_prot.export()" + "\n")

  def _add_item(self, list_, text) -> None:
    """Adds an protocol phase to the list of phases.

    First displays an interface for choosing the parameters of the phase.

    Args:
      list_: Either the mechanical or electrical list of phases.
      text: The text of the button clicked.
    """

    dialog = Param_dialog(self, text)
    if dialog.exec_():
      values = dialog.return_values()
      row = list_.currentRow()
      if row >= 0:
        list_.insertItem(row + 1, Phase(text, values))
        list_.setCurrentRow(row + 1)
      else:
        list_.addItem(Phase(text, values))

  def _show_item(self, list_) -> None:
    """Shows a window listing the selected protocol phase parameters.

    Args:
      list_: Either the mechanical or electrical list of phases.
    """

    Show_param_dialog(self,
                      list_.currentItem().txt,
                      list_.currentItem().values)

  @staticmethod
  def _remove_item(list_) -> None:
    """Removes a phase from the current protocol.

    Args:
      list_: Either the mechanical or electrical list of phases.
    """

    row = list_.currentRow()
    if row >= 0:
      list_.takeItem(row)

  @staticmethod
  def _move_item(position, list_) -> None:
    """Moves a phase up or down in the list of phases.

    Args:
      position: 1 for moving the item down, -1 for moving it up.
      list_: Either the mechanical or electrical list of phases.
    """

    prev_row = list_.currentRow()
    if prev_row >= 0:
      list_.insertItem(list_.currentRow() + position,
                       list_.takeItem(list_.currentRow()))
      list_.setCurrentRow(prev_row + position)
