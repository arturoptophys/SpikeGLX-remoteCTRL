import os
import sys
import time
from pathlib import Path
from queue import Queue
import logging
from spikeGLX_remote.GUI_utils import RemoteConnDialog
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QTableWidgetItem
from PyQt6.QtCore import Qt, QTimer
from PyQt6 import uic, QtGui

from spikeGLX_remote.spikeGLXremote_ctrl import SpikeGLX_Controller

log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

VERSION = "0.7.0"

if os.sys.platform == "win32":
    DEVELOPMENT = False
else:
    DEVELOPMENT = True

from config import COPY_DIRECT

class SpikeGLX_ControllerGUI(QMainWindow):
    """
    GUI wrapper for SpikeGLX_Controller
    """

    def __init__(self):
        super(SpikeGLX_ControllerGUI, self).__init__()
        self.rec_timer = None
        self._path2file = Path(__file__)
        uic.loadUi(self._path2file.parent / 'GUI' / 'spikeglx_remote.ui', self)  # get the gui design via uic
        self.setWindowTitle('SpikeGLXController v.%s' % VERSION)
        self.log = logging.getLogger('SpikeGLXController-GUI')
        self._handler = None
        self.consoleOutput.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.console_queue = Queue()
        # manage the console output across threads
        self.console_timer = QTimer()
        self.console_timer.timeout.connect(self._poll_console_queue)
        self.console_timer.start(50)  # units are milliseconds
        self.enable_console_logging()
        self.spikeglx_ctrl = SpikeGLX_Controller(self)
        self.set_Icons()
        self.ConnectSignals()
        self.set_save_path(self.spikeglx_ctrl.save_path)
        if not DEVELOPMENT:
            self.connect_spikeglx()
            if self.spikeglx_ctrl.hSglx is None:
                self.RECButton.setEnabled(False)
                self.RUNButton.setEnabled(False)
                self.RemoteModeButton.setEnabled(False)
                self.spikeGLXConnectB.setEnabled(True)
            else:
                self.RECButton.setEnabled(True)
                self.RUNButton.setEnabled(True)
                self.spikeGLXConnectB.setEnabled(False)
        if COPY_DIRECT:
            self.CopyButton.setEnabled(False)
            self.clearCopyButton.setEnabled(False)

    def connect_spikeglx(self):
        """Calls controller to create the connection handle to the SpikeGLX process"""
        self.spikeglx_ctrl.connect_spikeglx()

    def disconnect_spikeglx(self):
        """
        Calls controller to disconnect from the SpikeGLX and delete handle
        :return:
        """
        self.spikeglx_ctrl.disconnect_spikeglx()

    def start_recording(self):
        """
        Calls controller to start recording
        Starts recording timer
        """
        self.spikeglx_ctrl.start_recording()
        if self.spikeglx_ctrl.is_recording:
            self.start_rec_timer()
            if not self.spikeglx_ctrl.is_remote_ctr:
                self.RUNButton.setEnabled(False)
                self.RECButton.setEnabled(False)
                self.STOPButton.setEnabled(True)

    def start_run(self):
        """
        Calls controller to start running
        Starts recording timer
        """
        self.spikeglx_ctrl.start_run()
        if self.spikeglx_ctrl.is_viewing:
            self.start_rec_timer()
            self.SessionIDlineEdit.setText(self.spikeglx_ctrl.session_id)
            if not self.spikeglx_ctrl.is_remote_ctr:
                self.RUNButton.setEnabled(False)
                self.STOPButton.setEnabled(True)

    def start_run_record(self):
        """
        this combines the run and recording start into single function,
        not sure if needed probably manually start the run and then the recording via remote
        """
        self.spikeglx_ctrl.start_run_record()
        if self.spikeglx_ctrl.is_recording:
            self.start_rec_timer()
            if not self.spikeglx_ctrl.is_remote_ctr:
                self.RUNButton.setEnabled(False)
                self.RECButton.setEnabled(False)
                self.STOPButton.setEnabled(True)

    def stop_recording(self):
        """
        stops recording to file but continues viewing
        not sure if needed
        """
        self.spikeglx_ctrl.stop_recording()
        if self.spikeglx_ctrl.is_recording is False:
            self.stop_rec_timer()

    def stop_spikeglx(self):
        """
        Sends message to spikeGLX process to stop recording or viewing
        """
        self.spikeglx_ctrl.stop_spikeglx()
        if not self.spikeglx_ctrl.is_recording and not self.spikeglx_ctrl.is_viewing:
            self.stop_rec_timer()
            if not self.spikeglx_ctrl.is_remote_ctr:
                self.RECButton.setEnabled(True)
                self.RUNButton.setEnabled(True)
                self.STOPButton.setEnabled(False)

    def start_rec_button(self):
        """proxy for starting recording using the button"""
        if not self.spikeglx_ctrl.is_remote_ctr:
            self.spikeglx_ctrl.session_id = self.SessionIDlineEdit.text()
            if len(self.spikeglx_ctrl.session_id) == 0:  # if empty, generate a session id
                self.spikeglx_ctrl.session_id = f'MusterMausTest_{time.strftime("%Y%m%d_%H%M%S")}'
            if self.spikeglx_ctrl.ask_is_running():  # if already running
                self.spikeglx_ctrl.start_recording()
            else:
                self.spikeglx_ctrl.start_run_record()
            if self.spikeglx_ctrl.is_recording:
                self.STOPButton.setEnabled(True)
                self.RECButton.setEnabled(False)
                self.RUNButton.setEnabled(False)
        else:
            self.log.warning('Not allowed in remote mode.')

    def update_copy_view(self):
        """
        updates copy_tableWidget with the files to be copied
        """
        self.copy_tableWidget.setRowCount(len(self.spikeglx_ctrl.files_list2copy))
        self.copy_tableWidget.setColumnCount(2)
        self.copy_tableWidget.setHorizontalHeaderLabels(['Session', 'Path on server'])
        for row, sess in enumerate(self.spikeglx_ctrl.files_list2copy):
            self.copy_tableWidget.setItem(row, 0, QTableWidgetItem(sess['session']))
            self.copy_tableWidget.setItem(row, 1, QTableWidgetItem(str(sess['directory'])))
        self.copy_tableWidget.horizontalHeader().setStretchLastSection(True)

    def copy_file_list(self):
        """
        calls the controller to copy the files in the copy list
        """
        self.spikeglx_ctrl.copy_file_list()
        self.update_copy_view()

    def clear_copy_list(self):
        """
        clears the copy list
        """
        self.spikeglx_ctrl.clear_copy_list()
        self.update_copy_view()

    def ConnectSignals(self):
        """connects events to actions"""
        self.Save_pathButton.clicked.connect(self.set_save_path)
        self.RemoteModeButton.clicked.connect(self.remote_mode)
        self.RECButton.clicked.connect(self.start_rec_button)
        self.STOPButton.clicked.connect(self.stop_spikeglx)
        self.RUNButton.clicked.connect(self.start_run)
        self.EmergencyStopTaskB.clicked.connect(self.stop_spikeglx)  # will not reenable buttons if remote-ctl
        self.spikeGLXConnectB.clicked.connect(self.connect_spikeglx)
        self.CopyButton.clicked.connect(self.copy_file_list)
        self.clearCopyButton.clicked.connect(self.clear_copy_list)

    def set_save_path(self, save_path: (str, Path, None) = None):
        """
        Set the path where to save the recordings
        """
        if save_path is None or not save_path:
            save_path = QFileDialog.getExistingDirectory(self, "Select Directory where SpikeGLX-data should be saved")
        if save_path:
            self.spikeglx_ctrl.save_path = Path(save_path)
            self.log.debug(f'Save path set to {save_path}')
            self.SavePath_label.setText(f'Save path:\n{save_path}')

    def set_Icons(self):
        """sets icons to button etc."""
        self.RemoteModeButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/Signal.svg")))
        self.RUNButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/play.svg")))
        self.RECButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/record.svg")))
        self.STOPButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/stop.svg")))
        self.Save_pathButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/folder.svg")))
        self.EmergencyStopTaskB.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/HandRaised.svg")))

    def _poll_console_queue(self):
        """Write any queued console text to the console text area from the main thread."""
        while not self.console_queue.empty():
            string = str(self.console_queue.get())
            stripped = string.rstrip()
            errorFormat = '<span style="color:red;">{}</span>'
            warningFormat = '<span style="color:orange;">{}</span>'
            validFormat = '<span style="color:green;">{}</span>'
            normalFormat = '<span style="color:black;">{}</span>'

            if stripped != "":
                mess_type = stripped.split(":")[0]
                if mess_type == 'INFO':
                    self.consoleOutput.append(normalFormat.format(stripped))
                elif mess_type == 'ERROR':
                    self.consoleOutput.append(errorFormat.format(stripped))
                elif mess_type == 'WARNING':
                    self.consoleOutput.append(warningFormat.format(stripped))
                self.consoleOutput.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def write(self, string):
        """Write output to the console text area in a thread-safe way.  Qt only allows
        calls from the main thread, but the service routines run on separate threads."""
        self.console_queue.put(string)

    def enable_console_logging(self):
        """enables logging of messages to the console output in the gui. Debug messages are not output.
        puts message into queue using handler write function, another thread handles the rest"""
        # get the root logger to receive all logging traffic
        logger = logging.getLogger()
        # create a logging handler which writes to the console window via self.write
        handler = logging.StreamHandler(self)
        handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        handler.setLevel(logging.INFO)
        self._handler = handler

    def disable_console_logging(self):
        """disables the logging to the text widget"""
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None

    def remote_mode(self):
        if not self.spikeglx_ctrl.socket_comm.connected:
            self.spikeglx_ctrl.socket_comm.threaded_accept_connection()
            remote_dialog = RemoteConnDialog(self.spikeglx_ctrl.socket_comm, self)
            remote_dialog.exec()

            if not self.spikeglx_ctrl.socket_comm.connected:
                self.log.debug('Aborted remote connection')
            else:
                self.log.debug('Connected')
                self.enter_remote_mode()
        else:
            # self.abort_remoteconnection()
            self.exit_remote_mode()

    def enter_remote_mode(self):
        self.spikeglx_ctrl.enter_remote_mode()
        self.Client_label.setText(f"Connected to Client:\n{self.spikeglx_ctrl.socket_comm.addr}")
        self.RemoteModeButton.setText("EXIT\nREMOTE-mode")
        self.RemoteModeButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' / "icons/SignalSlash.svg")))
        self.RUNButton.setEnabled(False)
        self.RECButton.setEnabled(False)
        self.Save_pathButton.setEnabled(False)
        self.SessionIDlineEdit.setEnabled(False)

    def exit_remote_mode(self):
        self.spikeglx_ctrl.exit_remote_mode()
        self.Client_label.setText("disconnected")
        self.RemoteModeButton.setText("Enable\nREMOTE-mode")
        self.RemoteModeButton.setIcon(QtGui.QIcon(str(self._path2file.parent / 'GUI' /"icons/Signal.svg")))

        # enable all buttons
        self.RUNButton.setEnabled(True)
        self.RECButton.setEnabled(True)
        self.Save_pathButton.setEnabled(True)
        self.SessionIDlineEdit.setEnabled(True)
        self.SessionIDlineEdit.setText("")

    def start_rec_timer(self):
        """start the recording timer, updates the label every second"""
        self.rec_timer = QTimer()
        self.rec_timer.timeout.connect(self.update_rec_timer)
        self.rec_timer.start(1000)

    def stop_rec_timer(self):
        """stop the recording timer"""
        if self.rec_timer:
            self.rec_timer.stop()
        self.rec_timer = None

    def update_rec_timer(self):
        """update the recording timer label upon every call. is called from timed functions"""
        current_run_time = time.monotonic() - self.spikeglx_ctrl.rec_start_time
        if current_run_time >= 60:
            self.recording_duration_label.setText(f"{(current_run_time // 60):.0f}m:{(current_run_time % 60):2.0f}s")
        else:
            self.recording_duration_label.setText(f"{current_run_time:.0f}s")

    def app_is_exiting(self):
        """routine at closing of program, disconnects from sockets etc."""
        self.disconnect_spikeglx()
        if self.spikeglx_ctrl.socket_comm:
            self.spikeglx_ctrl.socket_comm.close_socket()
        self.disable_console_logging()

    def closeEvent(self, event):
        """
        callback to closing event. call app is exiting. Here we decide whether should actually exit.
        :param event:
        :return:
        """
        self.log.info("Received window close event.")
        if self.spikeglx_ctrl.is_recording or self.spikeglx_ctrl.is_viewing or self.spikeglx_ctrl.is_remote_ctr:
            message_text = "Recording still running. Abort ?" if self.spikeglx_ctrl.is_recording \
                else "Remote mode is active. Abort ?"

            message = QMessageBox.information(self,
                                              "Really quit?",
                                              message_text,
                                              buttons=QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes)
            if message == QMessageBox.StandardButton.No or message == QMessageBox.StandardButton.Abort:
                event.ignore()
                return
            elif message == QMessageBox.StandardButton.Yes:
                self.log.info('Exiting')
        self.app_is_exiting()
        super(SpikeGLX_ControllerGUI, self).closeEvent(event)


def start_gui():
    """
    starts the GUI application
    :return:
    """
    app = QApplication([])
    win = SpikeGLX_ControllerGUI()
    win.show()
    app.exec()


if __name__ == '__main__':
    logging.info('Starting via __main__')
    sys.exit(start_gui())
