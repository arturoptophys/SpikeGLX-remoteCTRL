import logging
import os
import shutil
import time
from ctypes import byref, c_bool
from pathlib import Path
from threading import Thread, Event

from socket_utils import SocketComm, SocketMessage, MessageType

log = logging.getLogger('controller')
log.setLevel(logging.DEBUG)

if os.sys.platform == "win32":
    DEVELOPMENT = False
else:
    DEVELOPMENT = True

if not DEVELOPMENT:
    import sglx as sglx

from config import *


class SpikeGLX_Controller:
    """
    This class uses the spikeGLX-api to control the SpikeGLX recorder. Needs to run on a windows computer due to only
    dlls being available.
    This application receives commands from the remote main TaskController via sockets
    Things like setting the session name, channelmap settings, recording parameters, start/stop recording,
    also should copy files upon receiving a path 2 copy
    """

    # TODO check if we are not on same machine then disable the copy functionality
    # if no main use some more descriptive console output
    def __init__(self, main=None):
        self.main = main  # reference to the main gui
        self.remote_thread_stop = Event()
        self.remote_thread = None
        self.files_copied = False
        self.session_path = None
        self.is_remote_ctr = False
        self.rec_start_time = None  # time when recording started
        self.hSglx = None  # handle to the spikeglx api connection
        self.is_recording = False  # bool whether currently recording
        self.is_viewing = False  # bool whether currently viewing
        self.session_id = None  # placeholder for the current session id
        self.recording_file = None
        self.log = logging.getLogger('SpikeGLXController')
        self.log.setLevel(logging.INFO)
        self.socket_comm = SocketComm('server', host=SPIKEGLX_HOST, port=SPIKEGLX_PORT)
        self.save_path = Path(PATH2DATA)
        self.last_t_socket = time.monotonic()  # last time we checked for a message from the remote controller
        self.check_interval = 1  # s check interval for messages

        if not DEVELOPMENT:
            self.connect_spikeglx()
            if self.hSglx is None:
                self.log.error("Error connecting to SpikeGLX")

    def connect_spikeglx(self):
        """create the connection handle to the SpikeGLX process"""
        if self.hSglx is None:
            self.log.debug("Calling connect to spikeGLX...")
            self.hSglx = sglx.c_sglx_createHandle()

            # Using default loopback address and port
            if sglx.c_sglx_connect(self.hSglx, "localhost".encode(), 4142):
                self.log.info(f"Connected to {sglx.c_sglx_getVersion(self.hSglx).decode()}")
            else:
                error = sglx.c_sglx_getError(self.hSglx).decode()
                if error == "sglx_connect: tcpConnect: Can't connect: No error (0)":
                    self.log.error("Cant establish SpikeGLX connection. is it running ?")
                self.hSglx = None

    def disconnect_spikeglx(self):
        """
        disconnect from the SpikeGLX and delete handle
        :return:
        """
        if self.hSglx:
            if self.ask_is_running() or self.ask_is_recording():
                self.stop_spikeglx()
            sglx.c_sglx_close(self.hSglx)
            sglx.c_sglx_destroyHandle(self.hSglx)
            self.hSglx = None
            self.log.debug("Closed connection to SpikeGLX")

    def ask_is_initialized(self):
        hid = c_bool()
        ok = sglx.c_sglx_isInitialized(byref(hid), self.hSglx)
        if ok:
            return bool(hid)
        else:
            error = sglx.c_sglx_getError(self.hSglx).decode()
            if error == "sglx_isInitialized: tcpConnect: Can't connect: No error (0)":
                self.log.error("SpikeGLX connection broken, try to reconnect")
                self.disconnect_spikeglx()
            else:
                self.log.error(error)
            return False

    def ask_is_running(self):
        hid = c_bool()
        ok = sglx.c_sglx_isRunning(byref(hid), self.hSglx)
        if ok:
            return bool(hid)
        else:
            error = sglx.c_sglx_getError(self.hSglx).decode()
            if error == "sglx_isRunning: tcpConnect: Can't connect: No error (0)":
                self.log.error("SpikeGLX connection broken, try to reconnect")
                self.disconnect_spikeglx()
            else:
                self.log.error(error)
            return False

    def ask_is_recording(self):
        hid = c_bool()
        ok = sglx.c_sglx_isSaving(byref(hid), self.hSglx)
        if ok:
            return bool(hid)
        else:
            self.log.error(f"{sglx.c_sglx_getError(self.hSglx)}")
            return False

    def start_recording(self):
        """
        Sends message to spikeGLX process to start recording.
        Before need to set parameters, save_path, session_id
        To call this spike GLX needs to be initialized and running
        """
        self.files_copied = False
        if self.ask_is_running():
            self.recording_file = (self.save_path / self.session_id)
            self.recording_file.mkdir(exist_ok=True)
            file_name = (self.recording_file / self.session_id).as_posix().encode()
            ok = sglx.c_sglx_setNextFileName(self.hSglx, file_name)
            if ok:
                ok = sglx.c_sglx_setRecordingEnable(self.hSglx, 1)
                if ok:
                    self.log.info(f"Started recording session {self.session_id}")
                    if self.socket_comm.connected:
                        self.socket_comm.send_json_message(SocketMessage.respond_recording)
                    self.is_recording = True
                    self.rec_start_time = time.monotonic()
                else:
                    self.log.error(f"{sglx.c_sglx_getError(self.hSglx)}")
                    self.send_socket_error()
            else:
                self.log.error(f"{sglx.c_sglx_getError(self.hSglx)}")
                self.send_socket_error()
        else:
            self.send_socket_error()
            self.log.error("SpikeGLX not running")

    def start_run(self):
        """
        Sends message to spikeGLX process to start viewing.
        Need to send some parameters beforehand
        """
        if self.ask_is_initialized():
            if self.session_id is None:
                self.session_id = f'MusterMausTest_{time.strftime("%Y%m%d_%H%M%S")}'
            ok = sglx.c_sglx_startRun(self.hSglx, self.session_id.encode())
            if ok:
                self.log.info(f"Started viewing session {self.session_id}")
                if self.socket_comm.connected:
                    self.socket_comm.send_json_message(SocketMessage.respond_viewing)
                self.is_viewing = True
                self.rec_start_time = time.monotonic()
            else:
                self.log.error(f"{sglx.c_sglx_getError(self.hSglx)}")
        else:
            self.send_socket_error()
            self.log.error("SpikeGLX not initialized")

    def start_run_record(self):
        """
        this combines the run and recording start into single function,
        not sure if needed probably manually start the run and then the recording via remote
        """
        ok = sglx.c_sglx_startRun(self.hSglx, self.session_id.encode())
        if ok:
            self.recording_file = (self.save_path / self.session_id)
            self.recording_file.mkdir(exist_ok=True)
            file_name = (self.recording_file / self.session_id).as_posix().encode()
            ok = sglx.c_sglx_setNextFileName(self.hSglx, file_name)
            ok = sglx.c_sglx_setRecordingEnable(self.hSglx, 1)
            if ok:
                self.log.info(f"Started recording session {self.session_id}")
                if self.socket_comm.connected:
                    self.socket_comm.send_json_message(SocketMessage.respond_recording)
                self.is_recording = True
                self.rec_start_time = time.monotonic()

    def stop_recording(self):
        """
        stops recording to file but continues viewing
        not sure if needed
        """
        if self.ask_is_recording():
            ok = sglx.c_sglx_setRecordingEnable(self.hSglx, 0)
            if ok:
                self.log.info(f"Stopped recording session {self.session_id} after "
                              f"{time.monotonic() - self.rec_start_time:.1f}s")
                if self.socket_comm.connected:
                    self.socket_comm.send_json_message(SocketMessage.respond_stop)
                self.is_recording = False
            else:
                self.log.error(f"{sglx.c_sglx_getError(self.hSglx)}")
                self.send_socket_error()

    def stop_spikeglx(self):
        """
        Sends message to spikeGLX process to stop recording or viewing
        """
        ok = sglx.c_sglx_stopRun(self.hSglx)
        if ok:
            if self.is_recording:
                self.log.info(f"Stopped recording session {self.session_id} after "
                              f"{time.monotonic() - self.rec_start_time:.1f}s")
                if self.socket_comm.connected:
                    self.socket_comm.send_json_message(SocketMessage.respond_stop)
            self.is_recording = False
            self.is_viewing = False
        else:
            self.log.error(f"{sglx.c_sglx_getError(self.hSglx)}")
            self.send_socket_error()

    def purge_recorded_file(self):
        """
        deletes the previously recorded files
        """
        if self.is_recording is False and self.recording_file is not None:
            self.log.info("Purging recorded files")
            shutil.rmtree(self.recording_file)
        self.recording_file = None

    def copy_recorded_file(self):
        """
        copies the recorded files to the session folder on the data server
        """
        if self.is_recording is False and not self.files_copied and self.recording_file is not None:
            # copy the recorded files to the session folder
            self.log.info(f"Copying folder {self.recording_file} to {self.session_path / NP_FOLDER}")
            try:
                if 'MusterMaus' in self.session_id:
                    shutil.copytree(self.recording_file, self.session_path)
                else:
                    if self.session_path.exists():
                        (self.session_path / NP_FOLDER).mkdir(exist_ok=True)  # make sure we have the ephys folder ready
                        # copy only the folder content not the folder itself
                        [shutil.copy2(file, self.session_path / NP_FOLDER) for file in self.recording_file.rglob('*')]
                        #shutil.copytree(self.recording_file, self.session_path / NP_FOLDER / self.recording_file.name)
                    else:
                        raise FileNotFoundError(f"Session path {self.session_path} doesnt exist")

            except (FileNotFoundError, IOError) as e:
                self.socket_comm.send_json_message(SocketMessage.respond_copy_fail)
                self.log.error(f"Error copying file {e}")
                return
            self.files_copied = True
            self.log.info(f"Finished copying files to {self.session_path / NP_FOLDER}")
            self.socket_comm.send_json_message(SocketMessage.respond_copy)

    def send_socket_error(self):
        """sends an error message to the remote main task controller"""
        if self.socket_comm.connected:
            self.socket_comm.send_json_message(SocketMessage.status_error)

    def enter_remote_mode(self):
        # rewerite using native python timer and not Qtimer
        # so probably a thread that checks for messages and then acts upon them
        self.remote_thread = Thread(target=self.check_and_parse_messages)
        self.remote_thread_stop.clear()
        self.remote_thread.start()
        self.is_remote_ctr = True
        self.socket_comm.send_json_message(SocketMessage.status_ready)

    def exit_remote_mode(self):
        self.remote_thread_stop.set()
        #self.remote_thread.join()
        self.socket_comm.close_socket()
        self.is_remote_ctr = False

    def check_and_parse_messages(self):
        while not self.remote_thread_stop.is_set():
            if self.last_t_socket + self.check_interval > time.monotonic():  # not enough time passed
                time.sleep(0.01)
            else:
                if not self.socket_comm.connected:
                    self.log.error("Client disconnected")
                    self.remote_thread_stop.set()
                    if self.main:
                        self.main.exit_remote_mode()
                    else:
                        self.exit_remote_mode()
                    return
                message = self.socket_comm.read_json_message_fast_linebreak()

                if message:
                    self.last_t_socket = time.monotonic()  # reset timer
                    if message['type'] == MessageType.start_video_rec.value \
                            or message['type'] == MessageType.start_video_view.value:
                        if self.is_recording and message['type'] == MessageType.start_video_rec.value:
                            # got record but we already are !
                            self.socket_comm.send_json_message(SocketMessage.status_error)
                            self.log.info("got message to start, but something is already running!")
                            return

                        self.session_id = message.get("session_id", 'MusterMaus')
                        if self.main:
                            self.main.SessionIDlineEdit.setText(self.session_id)

                        if message['type'] == MessageType.start_video_rec.value:
                            self.log.info("got message to start recording")
                            if self.main:
                                self.main.start_recording()
                            else:
                                self.start_recording()

                        elif message['type'] == MessageType.start_video_view.value:
                            self.log.info("got message to start viewing")
                            if self.main:
                                self.main.start_run()
                            else:
                                self.start_run()

                    elif message['type'] == MessageType.stop_video.value:
                        self.log.info("got message to stop")
                        #self.stop_spikeglx() # TODO not sure which one to use
                        if self.main:
                            self.main.stop_recording()
                        else:
                            self.stop_recording()


                    elif message['type'] == MessageType.poll_status.value:
                        if self.is_recording:
                            self.socket_comm.send_json_message(SocketMessage.status_recording)
                        elif self.is_viewing:
                            self.socket_comm.send_json_message(SocketMessage.status_viewing)
                        elif self.is_remote_ctr:
                            self.socket_comm.send_json_message(SocketMessage.status_ready)
                        else:
                            self.socket_comm.send_json_message(SocketMessage.status_error)

                    elif message['type'] == MessageType.disconnected.value:
                        self.log.info("got message that client disconnected")
                        if self.main:
                            self.main.exit_remote_mode()
                        else:
                            self.exit_remote_mode()

                    elif message['type'] == MessageType.copy_files.value:
                        self.log.debug('got message to copy files')
                        self.session_path = Path(message['session_path'])
                        if self.session_path:
                            self.copy_recorded_file()

                    elif message['type'] == MessageType.purge_files.value:
                        self.log.debug('got message to purge files')
                        self.purge_recorded_file()


if __name__ == '__main__':
    logging.info('Starting via __main__')
    controller = SpikeGLX_Controller()
    controller.socket_comm.threaded_accept_connection()
    while not controller.socket_comm.connected:
        time.sleep(0.5)
        #controller.log.info("waiting for remote connection")
    controller.enter_remote_mode()
