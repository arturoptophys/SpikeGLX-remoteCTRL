from PyQt6 import QtWidgets, QtCore
from PyQt6.QtWidgets import QMessageBox
from PyQt6 import QtGui


class InfoDialog(QMessageBox):
    """
    Error Dialog
    """

    def __init__(self, message):
        super().__init__()
        replace_messagebox = QMessageBox.information(
            self,
            "Info",
            "%s" % message,
            buttons=QMessageBox.StandardButton.Ok)


class RemoteConnDialog(QtWidgets.QDialog):
    """
    Dialog to wait for remote connection, with abort button
    """

    def __init__(self, socket_comm, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.socket_comm = socket_comm
        self.setWindowTitle('Remote Connection')
        self.abort_button = QtWidgets.QPushButton("Abort")
        self.abort_button.clicked.connect(self.stopwaiting)
        self.abort_button.setIcon(QtGui.QIcon("./GUI/icons/HandRaised.svg"))
        self.label = QtWidgets.QLabel("waiting for remote connection...")
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.abort_button)
        self.setLayout(layout)

        self.connectio_time = QtCore.QTimer()
        self.connectio_time.timeout.connect(self.check_connection)
        self.connectio_time.start(500)
        self.aborted = False

    def check_connection(self):
        """
        Check if connection is established, if so close dialog, called regularly by timer
        """
        if self.socket_comm.connected:
            self.close()

    def stopwaiting(self):
        """
        Stop waiting for connection, called by abort button
        """
        self.socket_comm.stop_waiting_for_connection()
        self.aborted = True
        self.close()

    def closeEvent(self, event):
        # If the user closes the dialog, kill the process
        self.stopwaiting()
        self.aborted = True
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    dialog = InfoDialog("Test")
    dialog.exec()
    dialog.show()
    app.exec()
