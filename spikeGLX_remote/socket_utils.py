import socket
import ssl
import threading
import select
import logging
import time
import json

from enum import Enum


class MessageType(Enum):
    """
    Enum for message types
    to be able to change the message easily across the code
    """
    start_daq = 'start_rec'
    stop_daq = 'stop'
    start_daq_pulses = 'start_pulses'
    stop_daq_pulses = 'stop_pulses'
    start_daq_viewing = 'start_viewing'
    poll_status = 'status_poll'
    start_video_rec = 'start_rec'
    start_video_view = 'start_viewing'
    stop_video = 'stop'
    start_video_calibrec = 'start_calibrec'
    status = 'status'
    response = 'response'
    disconnected = 'disconnected'
    copy_files = 'copy_files'
    purge_files = 'purge_files'


class MessageStatus(Enum):
    """
    Enum for message status
    to be able to change the message easily across the code
    """
    ready = 'ready'
    error = 'error'
    viewing = 'viewing'
    recording = 'recording'
    viewing_ok = 'viewing_ok'
    recording_ok = 'recording_ok'
    recording_fail = 'recording_fail'
    stop_ok = 'stop_ok'
    pulsing_ok = 'pulsing_ok'
    calib_ok = 'calib_ok'
    copy_ok = 'copy_ok'
    copy_fail = 'copy_fail'


class SocketMessage:
    """
    Class to hold all the messages that can be sent over the socket

    :param session_path: str: path to the session
    :param fps: float: frames per second
    :param session_id: str: session id
    :param daq_setting_file: str: path to the daq setting file
    :param basler_setting_file: str: path to the basler setting file
    :param pulse_lag: int: pulse lag after DAQ start
    :param start_daq: dict: message to start the daq
    :param stop_daq: dict: message to stop the daq
    :param start_daq_pulses: dict: message to start the daq pulses
    :param stop_daq_pulses: dict: message to stop the daq pulses
    :param start_daq_viewing: dict: message to start the daq viewing
    :param poll_status: dict: message to poll the status
    :param start_video_rec: dict: message to start the video recording
    :param start_video_view: dict: message to start the video viewing
    :param stop_video: dict: message to stop the video
    :param start_video_calibrec: dict: message to start the calibration recording

    :param copy_files: dict: message to copy the files
    :param purge_files: dict: message to purge the files
    :param view_spike_glx: dict: message to view the spike glx
    :param start_spike_glx: dict: message to start the spike glx
    :param stop_spike_glx: dict: message to stop the spike glx
    """
    status_error = {'type': MessageType.status.value, 'status': MessageStatus.error.value}
    status_ready = {'type': MessageType.status.value, 'status': MessageStatus.ready.value}
    status_recording = {'type': MessageType.status.value, 'status': MessageStatus.recording.value}
    status_viewing = {'type': MessageType.status.value, 'status': MessageStatus.viewing.value}

    respond_recording = {'type': MessageType.response.value, 'status': MessageStatus.recording_ok.value}
    respond_recording_fail = {'type': MessageType.response.value, 'status': MessageStatus.recording_fail.value}
    respond_viewing = {'type': MessageType.response.value, 'status': MessageStatus.viewing_ok.value}
    respond_stop = {'type': MessageType.response.value, 'status': MessageStatus.stop_ok.value}
    respond_pulsing = {'type': MessageType.response.value, 'status': MessageStatus.pulsing_ok.value}
    respond_calib = {'type': MessageType.response.value, 'status': MessageStatus.calib_ok.value}
    respond_copy = {'type': MessageType.response.value, 'status': MessageStatus.copy_ok.value}
    respond_copy_fail = {'type': MessageType.response.value, 'status': MessageStatus.copy_fail.value}
    client_disconnected = {'type': MessageType.disconnected.value}

    def __init__(self):
        self._session_path = None
        self._fps = 30
        self._session_id = "test"
        self._daq_setting_file = ''
        self._basler_setting_file = ''
        self._pulse_lag = 0
        self.start_daq = {'type': MessageType.start_daq.value, 'session_id': self._session_id,
                          'setting_file': self._daq_setting_file}
        self.stop_daq = {'type': MessageType.stop_daq.value}
        self.start_daq_pulses = {'type': MessageType.start_daq_pulses.value, 'fps': self._fps,
                                 'pulse_lag': self._pulse_lag}
        self.stop_daq_pulses = {'type': MessageType.stop_daq_pulses.value}
        self.start_daq_viewing = {'type': MessageType.start_daq_viewing.value, 'session_id': self._session_id,
                                  'setting_file': self._daq_setting_file}
        self.poll_status = {'type': MessageType.poll_status.value}

        self.start_video_rec = {'type': MessageType.start_video_rec.value, 'session_id': self._session_id,
                                'setting_file': self._basler_setting_file, 'frame_rate': self._fps}
        self.start_video_view = {'type': MessageType.start_video_view.value, 'session_id': self._session_id,
                                 'setting_file': self._basler_setting_file, 'frame_rate': self._fps}
        self.stop_video = {'type': MessageType.stop_video.value}

        self.start_video_calibrec = {'type': MessageType.start_video_calibrec.value, 'session_id': 'calibration',
                                     'setting_file': self._basler_setting_file, 'frame_rate': 5}

        self.copy_files = {'type': MessageType.copy_files.value, 'session_id': self._session_id,
                           'session_path': self._session_path}
        self.purge_files = {'type': MessageType.purge_files.value, 'session_id': self._session_id}

        self.view_spike_glx = {'type': MessageType.start_video_view.value,
                               'session_id': self._session_id}  # maybe further params
        self.start_spike_glx = {'type': MessageType.start_video_rec.value, 'session_id': self._session_id}
        self.stop_spike_glx = {'type': MessageType.stop_video.value}
        # if i add new ones they also need to addd to the update_messages function or automate this ?

    @property
    def pulse_lag(self):
        return self._pulse_lag

    @pulse_lag.setter
    def pulse_lag(self, value: int):
        self._pulse_lag = value
        self.update_messages()

    @property
    def session_id(self):
        return self._session_id

    @session_id.setter
    def session_id(self, value: str):
        self._session_id = value
        self.update_messages()

    @property
    def session_path(self):
        return self._session_path

    @session_path.setter
    def session_path(self, value: str):
        self._session_path = value
        self.update_messages()

    @property
    def fps(self):
        return self._fps

    @fps.setter
    def fps(self, value: float):
        self._fps = value
        self.update_messages()

    @property
    def daq_setting_file(self):
        return self._daq_setting_file

    @daq_setting_file.setter
    def daq_setting_file(self, value: str):
        self._daq_setting_file = value
        self.update_messages()

    @property
    def basler_setting_file(self):
        return self._basler_setting_file

    @basler_setting_file.setter
    def basler_setting_file(self, value: str):
        self._basler_setting_file = value
        self.update_messages()

    def update_messages(self):
        """
        Updates all the messages with current values.
        :return:
        """
        self.start_daq.update(**{'session_id': self.session_id, 'setting_file': self.daq_setting_file})
        self.start_daq_viewing.update(**{'session_id': self._session_id,
                                         'setting_file': self.daq_setting_file})
        self.start_daq_pulses.update(**{'fps': self.fps, 'pulse_lag': self.pulse_lag})
        self.start_video_rec.update(**{'session_id': self.session_id, 'setting_file': self.basler_setting_file,
                                       'frame_rate': self.fps})
        self.start_video_view.update(**{'session_id': self._session_id, 'setting_file': self.basler_setting_file,
                                        'frame_rate': self.fps})
        self.start_video_calibrec.update(**{'session_id': 'calibration', 'setting_file': self.basler_setting_file})
        self.copy_files.update(**{'session_id': self.session_id, 'session_path': self._session_path})
        self.purge_files.update(**{'session_id': self._session_id})
        self.view_spike_glx.update(**{'session_id': self._session_id})  # maybe further params
        self.start_spike_glx.update(**{'session_id': self._session_id})
        self.stop_spike_glx.update(**{'session_id': self._session_id})


class SocketComm:
    """
    Class to handle socket communication between processes or devices
    :param soctype: str: type of socket, either 'client' or 'server'
    :param host: str: host IP address
    :param port: int: port number
    :param use_ssl: bool: use ssl encryption

    :param acception_thread: threading.Thread: thread to accept connection
    :param ssl_sock: ssl.SSLSocket: ssl socket
    :param sock: socket.socket: socket
    :param _sock: socket.socket: socket
    :param _ssl_sock: ssl.SSLSocket: ssl socket
    :param context: ssl.SSLContext: ssl context
    :param use_ssl: bool: use ssl encryption
    :param connected: bool: connection status
    :param stop_event: threading.Event: event to stop waiting for connection
    :param log: logging.Logger: logger
    :param message_time: float: time of last message
    """

    def __init__(self, soctype: str = "server", host: str = "localhost", port: int = 8800, use_ssl: bool = False):
        self.acception_thread = None
        self.ssl_sock = None
        self.sock = None
        self._sock = None
        self._ssl_sock = None
        self.type = soctype
        self.host = host
        self.port = port
        if self.type == "server":
            self.context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        else:
            self.context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        # self.context.set_ciphers('DEFAULT')
        self.use_ssl = use_ssl
        if use_ssl:
            raise NotImplementedError("SSL not implemented yet")
        # this doesnt work yet get some weird error from ssl module
        self.connected = False
        self.stop_event = threading.Event()
        self.log = logging.getLogger(f"SocketComm_{self.type}")
        self.log.setLevel(logging.DEBUG)
        self.message_time = time.monotonic()

    def create_socket(self):
        """
        Creates the socket for the server or client
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.type == 'client':
            pass
        elif self.type == 'server':
            try:
                self._sock.bind((self.host, self.port))
            except OSError:
                self.log.warning('Address already in use.. need to delete somehow ?')
            self._sock.listen()
            if self.use_ssl:
                self._ssl_sock = self.context.wrap_socket(self._sock, server_side=True, do_handshake_on_connect=False)

    def accept_connection(self):
        """
        Accepts connection-request from client
        :return:
        """
        self.create_socket()
        while not self.stop_event.is_set():
            if time.monotonic() - self.message_time > 5:
                self.message_time = time.monotonic()
                self.log.debug('waiting for connection...')
            if self.use_ssl:
                ready, _, _ = select.select([self._ssl_sock], [], [], 0.1)
                if ready:
                    self.ssl_sock, self.addr = self._ssl_sock.accept()
                    self.ssl_sock.settimeout(0.1)
                    self.connected = True
                    self.log.info(f"Connected to {self.addr}")
                    break
            else:
                ready, _, _ = select.select([self._sock], [], [], 0.1)
                if ready:
                    self.sock, self.addr = self._sock.accept()
                    self.sock.settimeout(0.1)
                    self.connected = True
                    self.log.info(f"Connected to {self.addr}")
                    break
        else:
            self.log.debug("Stop event set. Stopping thread...")
            return

    def threaded_accept_connection(self):
        """
        Accepts connection in a separate thread, to not block the main thread
        """
        self.stop_event.clear()
        self.acception_thread = threading.Thread(target=self.accept_connection)
        self.acception_thread.start()

    def stop_waiting_for_connection(self):
        """
        sets the stop event, so the thread will stop waiting for a connection
        """
        self.stop_event.set()

    def connect(self) -> bool:
        """
        Connects to the server
        """
        if self.type == 'client':
            if self.use_ssl:
                self.ssl_sock = self.context.wrap_socket(self._sock, server_hostname=self.host,
                                                         do_handshake_on_connect=False)
            else:
                self.sock = self._sock
                self.sock.settimeout(0.1)  # otherwise we get issues if nothing is comming
            self._connect(self.host, self.port)
            self.connected = True
            return True
        else:
            return False
            # raise RuntimeError("Error: Cannot connect on server socket")

    def close_socket(self):
        """
        Closes the socket
        :return:
        """
        if self.use_ssl:
            if self.ssl_sock:
                self.ssl_sock.close()
            self._ssl_sock.close()
        if self.sock:
            self.sock.close()
        if self._sock:
            self._sock.close()
        self.connected = False

    def read_json_message(self) -> [dict, None]:
        """
        Reads a json message from the socket until a linebreak is reached then decodes it via json
        :return: dict, None: message or None if no message is received
        """
        try:
            message = self._recv_until(b'\n')
            if message is not None:
                message = json.loads(message.decode())
            else:
                return message
        except json.decoder.JSONDecodeError:
            message = None
        return message

    def read_json_message_fast(self) -> [dict, None]:
        """
        Reads a json message from the socket via a large bulk then decodes it via json
        :return: dict, None: message or None if no message is received
        """
        try:
            message = self._recv(1024)
            if message == -1:
                return SocketMessage.client_disconnected
            if message is not None:
                message = json.loads(message.decode())
            else:
                return message
        except json.decoder.JSONDecodeError:
            message = None
            print('message decoding failed')
        return message

    def read_json_message_fast_linebreak(self) -> [dict,None]:
        """
        Reads a json message from the socket until a linebreak is reached then decodes it via json
        :return: dict, None: message or None if no message is received
        """
        try:
            message = self._recv_until(b'\n')
            if message == -1:
                return SocketMessage.client_disconnected
            if message is not None:
                message = json.loads(message.decode())
        except json.decoder.JSONDecodeError:
            message = None
            self.log.error('message decoding failed')
        except OSError:
            message = None
            self.log.warning('socket disconnected and deleted')
        return message

    def send_json_message(self, message: dict):
        """
        Sends a json message over the socket
        :param message: dict: message to send of SocketMessage type
        :return:
        """
        message = json.dumps(message).encode()
        message += b'\n'
        self._send(message)

    def _connect(self, host, port):
        if self.use_ssl:
            self.ssl_sock.connect((host, port))
        else:
            self.sock.connect((host, port))

    def _send(self, data):
        try:
            if self.use_ssl:
                self.ssl_sock.sendall(data)
            else:
                self.sock.sendall(data)
        except ConnectionResetError:
            self.log.error("Connection reset by peer")

    def _recv(self, size) -> (bytes, int):
        try:
            if self.use_ssl:
                return self.ssl_sock.recv(size)
            else:
                return self.sock.recv(size)
        except socket.timeout:
            return None
        except ConnectionResetError:
            self.log.warning("Client disconnected")
            return -1

    def _recv_until(self, delimiter: bytes) -> [bytes, None, int]:
        """
        Receives data until a delimiter is reached
        :param delimiter:  bytes: delimiter to stop receiving
        :return: bytes, None, int: received data or None if no data is received or -1 if client disconnected
        """
        data = b''
        try:
            if self.use_ssl:
                while not data.endswith(delimiter):
                    received = self.ssl_sock.recv(1)
                    if received == b'':
                        self.connected = False
                        break
                    data += self.ssl_sock.recv(1)
            else:
                while not data.endswith(delimiter):
                    received = self.sock.recv(1)
                    if received == b'':
                        self.connected = False
                        break
                    data += received
        except socket.timeout:
            data = None
        except (BrokenPipeError, ConnectionResetError):
            self.log.warning("Client disconnected")
            data = -1
        return data

    def _recv_all(self):
        data = b''
        if self.use_ssl:
            while True:
                try:
                    data += self.ssl_sock.recv(1024)
                except socket.timeout:
                    break
        else:
            while True:
                try:
                    data += self.sock.recv(1024)
                except socket.timeout:
                    break
        return data



if __name__ == "__main__":
    import time
    import argparse
    import json

    """
    parser = argparse.ArgumentParser(description='Socket communication test')
    parser.add_argument('--type', type=str, default='server', help='Socket type: client or server')
    parser.add_argument('--host', type=str, default='localhost', help='Host IP address')
    parser.add_argument('--port', type=int, default=8800, help='Port number')
    parser.add_argument('--use_ssl', type=bool, default=False, help='Use SSL')
    args = parser.parse_args()

    sock = SocketComm('server')
    sock.create_socket()
    sock.threaded_accept_connection()
    while not sock.connected:
        print('no connection established,waiting...')
        time.sleep(1)
    try:
        data = sock.read_json_message()
        print(data)
    except Exception as e:
        print(e)
        pass
    sock.close_socket()
    """

    import json
    from pathlib import PureWindowsPath

    sock = SocketComm('client', port=8882)
    sock.create_socket()
    sock.connect()
    time.sleep(0.5)
    response = sock.read_json_message_fast()
    socket_messages = SocketMessage()
    print(response)
    socket_messages.session_id = 'testMousy42_yeah'
    sock.send_json_message(socket_messages.start_spike_glx)
    time.sleep(0.5)
    response = sock.read_json_message_fast()
    print(response)
    time.sleep(5)
    sock.send_json_message(socket_messages.stop_spike_glx)
    time.sleep(0.5)
    response = sock.read_json_message_fast()
    print(response)
    time.sleep(1)

    sess_path = r"2023_BehFlex\HillYmaze_training\data\0_raw\20230620_r0083_wt_1711"
    win_path = PureWindowsPath("O:\\archive\\users\\as153\\Copytest") / sess_path
    socket_messages.session_path = str(win_path)
    sock.send_json_message(socket_messages.copy_files)
    time.sleep(2)
    response = sock.read_json_message_fast()
    print(response)
    sock.close_socket()
