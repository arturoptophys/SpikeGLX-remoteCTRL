import logging
import os
import shutil
import time
from ctypes import byref, c_bool
from pathlib import Path
from threading import Thread, Event
import numpy as np

from mtscomp import compress as mtscompress

from spikeGLX_remote.sglx_utils import get_num_saved_channels, get_sample_rate, read_meta
from spikeGLX_remote.socket_utils import SocketComm, SocketMessage, MessageType

log = logging.getLogger('controller')
log.setLevel(logging.DEBUG)

if os.sys.platform == "win32":
    DEVELOPMENT = False
else:
    DEVELOPMENT = True

# if not DEVELOPMENT:
import spikeGLX_remote.sglx as sglx

from config import *


class SpikeGLX_Controller:
    """
    This class uses the spikeGLX-api to control the SpikeGLX recorder. Needs to run on a windows computer due to only
    dlls being available.
    This application receives commands from the remote main TaskController via sockets, it can receive the session name
    for the recording, start/stop recording, start viewing, copy files to the data server, purge files.

    :param main: reference to the main GUI
    :type main: GUI_utils.MainWindow

    :parameter remote_thread_stop: Event to stop the remote thread
    :type remote_thread_stop: threading.Event
    :parameter remote_thread: thread to check for remote messages
    :type remote_thread: threading.Thread
    :parameter files_copied: flag if files were copied
    :type files_copied: bool
    :parameter session_path: path to copy the files to
    :type session_path: Path
    :parameter is_remote_ctr: flag if in remote control mode
    :type is_remote_ctr: bool
    :parameter rec_start_time: time when recording started
    :type rec_start_time: float
    :parameter hSglx: handle to the spikeglx api connection
    :type hSglx: ctypes.c_void_p
    :parameter is_recording: flag whether currently recording
    :type is_recording: bool
    :parameter is_viewing: flag whether currently viewing
    :type is_viewing: bool
    :parameter session_id: placeholder for the current session id
    :type session_id: str
    :parameter recording_file: placeholder for the recording file
    :type recording_file: Path
    :parameter log: logger object
    :type log: logging.Logger
    :parameter socket_comm: socket communication object
    :type socket_comm: SocketComm
    :parameter _save_path: path to save the recorded files
    :type _save_path: Path
    :parameter last_t_socket: last time we checked for a message from the remote controller
    :type last_t_socket: float
    :parameter check_interval: check interval for messages
    :type check_interval: int
    :parameter can_copy: flag if files can be copied
    :type can_copy: bool
    """

    # TODO if no main use some more descriptive console output
    def __init__(self, main=None):
        self.main = main  # reference to the main gui
        self.remote_thread_stop = Event()  # event to stop the remote thread
        self.remote_thread = None  # thread to check for remote messages
        self.files_copied = False  # bool if files were copied
        self.session_path = None  # path to copy the files to
        self.is_remote_ctr = False  # bool if in remote control mode
        self.rec_start_time = None  # time when recording started
        self.hSglx = None  # handle to the spikeglx api connection
        self.is_recording = False  # bool whether currently recording
        self.is_viewing = False  # bool whether currently viewing
        self.session_id = None  # placeholder for the current session id
        self.recording_file = None  # placeholder for the recording file
        self.log = logging.getLogger('SpikeGLXController')
        self.log.setLevel(logging.INFO)
        self.socket_comm = SocketComm('server', host=REMOTE_HOST, port=REMOTE_PORT)
        self._save_path = Path(PATH2DATA)
        self.last_t_socket = time.monotonic()  # last time we checked for a message from the remote controller
        self.check_interval = 1  # s check interval for messages
        self.can_copy = True if SPIKEGLX_COMPUTER == 'localhost' else False  # cant copy files if not on same machine
        self.files_list2copy = []  # list of files to copy
        if not DEVELOPMENT:  # switch off spikeGLX if in development mode (not on windows)
            self.connect_spikeglx()
            if self.hSglx is None:
                self.log.error("Error connecting to SpikeGLX")

    @property
    def save_path(self):
        return self._save_path

    @save_path.setter
    def save_path(self, path: [str, Path]):
        """
        sets the save path for the recorded files, ensures its a Path object
        :param path: str or Path object to set the save path
        :return:
        """
        try:
            self._save_path = Path(path)
        except TypeError:
            self.log.error("Error setting save path, must be a str or Path object")

    def connect_spikeglx(self):
        """create the connection handle to the SpikeGLX process"""
        if self.hSglx is None:
            self.log.debug("Calling connect to spikeGLX...")
            self.hSglx = sglx.c_sglx_createHandle()

            # Using default loopback address and port
            if sglx.c_sglx_connect(self.hSglx, SPIKEGLX_COMPUTER.encode(), SPIKEGLX_PORT):
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

    def ask_is_initialized(self) -> bool:
        """
        checks if spikeGLX is currently initialized, and thus ready to start
        :return: bool if initialized
        """
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

    def ask_is_running(self) -> bool:
        """
        checks if spikeGLX is currently running
        :return: bool if running
        """
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

    def ask_is_recording(self) -> bool:
        """
        checks if spikeGLX is currently recording
        :return: bool if recording
        """
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
        To call this spikeGLX needs to be initialized and running.
        """
        self.files_copied = False
        self.check_disk_space()
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
        To call this spikeGLX needs to be initialized.
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
            if not self.can_copy:
                self.log.error("Cant delete files if not on same machine")
                self.socket_comm.send_json_message(SocketMessage.respond_copy_fail)
                return
            self.log.info("Purging recorded files")
            shutil.rmtree(self.recording_file)
        self.recording_file = None

    @staticmethod
    def compress_recorded_file(path2file: [Path, str]) -> [Path, int]:
        """
        compresses the previously recorded files
        """
        if isinstance(path2file, str):
            path2file = Path(path2file)
        if path2file.exists():
            if not path2file.is_dir():
                path2file = path2file.parent
            # find the ap.bin file get its name
            try:
                metafile = list(path2file.glob('*.ap.meta'))[0]
                bin_file = list(path2file.glob('*.ap.bin'))[0]
                out_file = bin_file.with_suffix('.cbin')
                out_meta = bin_file.with_suffix('.ch')
                out_file = out_file.parent / 'compressed' / out_file.name
                out_meta = out_meta.parent / 'compressed' / out_meta.name
                meta = read_meta(metafile)
                sample_rate = get_sample_rate(meta)
                n_channels = get_num_saved_channels(meta)
            except IndexError:
                log.error(f"No ap.bin file found at {path2file}")
                return 0
            mtscompress(bin_file, out_file, out_meta, sample_rate=sample_rate, n_channels=n_channels, dtype=np.int16)
            # copy meta file
            shutil.copy2(metafile, out_meta.parent)
        else:
            log.error(f"Path {path2file} not found")
            return 0
        return out_file.parent

    def copy_recorded_file(self):
        """
        copies the recorded files to the session folder on the data server
        """
        if self.is_recording is False and not self.files_copied and self.recording_file is not None:
            # copy the recorded files to the session folder
            if not self.can_copy:
                self.log.error("Cant copy files if not on same machine")
                self.socket_comm.send_json_message(SocketMessage.respond_copy_fail)
                return
            self.log.info(f"Copying folder {self.recording_file} to {self.session_path}")
            try:
                if 'MusterMaus' in self.session_id:
                    shutil.copytree(self.recording_file, self.session_path)
                else:
                    if self.session_path.exists():
                        self.session_path.mkdir(exist_ok=True)  # make sure we have the ephys folder ready
                        # copy only the folder content not the folder itself
                        [shutil.copy2(file, self.session_path) for file in self.recording_file.rglob('*')]
                        # shutil.copytree(self.recording_file, self.session_path / self.recording_file.name)
                    else:
                        raise FileNotFoundError(f"Session path {self.session_path} doesnt exist")

            except (FileNotFoundError, IOError) as e:
                self.socket_comm.send_json_message(SocketMessage.respond_copy_fail)
                self.log.error(f"Error copying file {e}")
                return
            self.files_copied = True
            self.log.info(f"Finished copying files to {self.session_path}")
            self.socket_comm.send_json_message(SocketMessage.respond_copy)

    def add_to_copy_list(self):
        """
        adds recorded files to the list to be copied later as copy might be long
        """
        if self.is_recording is False and self.recording_file is not None:
            # copy the recorded files to the session folder
            if not self.can_copy:
                self.log.error("Cant copy files if not on same machine")
                self.socket_comm.send_json_message(SocketMessage.respond_copy_fail)
                return
            self.log.info(f"adding folder {self.recording_file} to list")
            self.files_list2copy.append({'session': self.session_id, 'files': self.recording_file,
                                         'directory': self.session_path})
            if self.main:
                self.main.update_copy_view()

    def clear_copy_list(self):
        """
        clears the list of files to be copied
        """
        self.files_list2copy = []

    def compress_file_list(self):
        """
        compresses the files in the copy list
        """
        for sess in self.files_list2copy:
            self.log.info(f"Compressing folder {sess['files']}")
            try:
                new_path = self.compress_recorded_file(sess['files'])
                if new_path:
                    self.log.info(f"Finished compressing files to {new_path}")
                    sess['files'] = new_path
                    sess["compressed"] = "Yes"
                else:
                    raise IOError
            except (FileNotFoundError, IOError) as e:
                self.log.error(f"Error compressing file {e}")
        if COPY_AFTER_COMPRESS:
            self.copy_file_list()

    def copy_file_list(self):
        """
        copies the files in the list to the session folder on the data server
        """
        copied = False
        for sess in self.files_list2copy:
            self.log.info(f"Copying folder {sess['files']} to {sess['directory']}")
            try:
                if 'MusterMaus' in sess['session']:
                    shutil.copytree(sess['files'], sess['directory'])
                else:
                    if sess['directory'].exists():
                        sess['directory'].mkdir(exist_ok=True)  # make sure we have the ephys folder ready
                        # copy only the folder content not the folder itself
                        [shutil.copy2(file, sess['directory']) for file in sess['files'].rglob('*')]
                        copied = True
                    else:
                        raise FileNotFoundError(f"Session path {sess['directory']} doesnt exist")
            except (FileNotFoundError, IOError) as e:
                self.socket_comm.send_json_message(SocketMessage.respond_copy_fail)
                self.log.error(f"Error copying file {e}")

            # if copied: # if succesfully copied
            self.clear_copy_list()

    def send_socket_error(self):
        """sends an error message to the remote main task controller"""
        if self.socket_comm.connected:
            self.socket_comm.send_json_message(SocketMessage.status_error)

    def enter_remote_mode(self):
        """
        Starts a thread that regularly checks for messages from the remote controller
        Sends a status message to the remote controller
        :return:
        """
        self.remote_thread = Thread(target=self.check_and_parse_messages)
        self.remote_thread_stop.clear()
        self.remote_thread.start()
        self.is_remote_ctr = True
        self.socket_comm.send_json_message(SocketMessage.status_ready)

    def check_disk_space(self):
        """
        Check if we have enough free disk space on the indicated drive for >1h recording
        :return:
        """
        _, _, free = shutil.disk_usage(self._save_path)
        free = free // 2**30
        if free < WARN_DISK_SPACE:
            self.log.warning(f'Not enough disc space on {self._save_path}')
            if self.is_remote_ctr:
                self.socket_comm.send_json_message(SocketMessage.respond_recording_fail)

    def exit_remote_mode(self):
        """
        exits the remote mode, signals to stop the thread and closes the socket
        :return:
        """
        self.remote_thread_stop.set()
        # self.remote_thread.join()
        self.socket_comm.close_socket()
        self.is_remote_ctr = False

    def check_and_parse_messages(self):
        """
        timed function that runs in a thread and checks for messages from the remote controller
        checks every self.check_interval seconds
        stops when self.remote_thread_stop Event is set
        :return:
        """
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
                        # self.stop_spikeglx() # TODO not sure which one to use
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
                            if COPY_DIRECT:
                                self.copy_recorded_file()
                            else:
                                self.add_to_copy_list()

                    elif message['type'] == MessageType.purge_files.value:
                        self.log.debug('got message to purge files')
                        self.purge_recorded_file()


if __name__ == '__main__':
    logging.info('Starting via __main__')
    controller = SpikeGLX_Controller()
    controller.socket_comm.threaded_accept_connection()
    while not controller.socket_comm.connected:
        time.sleep(0.5)
        # controller.log.info("waiting for remote connection")
    controller.enter_remote_mode()
