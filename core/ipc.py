import os
import socket
import threading
import json

from core.logging_utils import log

class IPCServer(threading.Thread):
    def __init__(self, command_handler=None):
        super().__init__()
        self.command_handler = command_handler
        self.running = False
        self.socket_path = self._get_socket_path()

    def _get_socket_path(self):
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        return os.path.join(xdg_runtime, "voxquill.socket")

    def run(self):
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        server.listen(1)
        server.settimeout(1.0)
        self.running = True
        
        log(f"IPC Server listening on {self.socket_path}")

        while self.running:
            try:
                conn, _ = server.accept()
                with conn:
                    data = conn.recv(1024)
                    if data:
                        try:
                            msg = json.loads(data.decode())
                            command = msg.get("command")
                            if command and self.command_handler:
                                self.command_handler(command)
                        except json.JSONDecodeError:
                            log("Received invalid JSON IPC message")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log(f"IPC Server error: {e}")

        server.close()
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

    def stop(self):
        self.running = False

class IPCClient:
    def __init__(self):
        self.socket_path = self._get_socket_path()

    def _get_socket_path(self):
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        return os.path.join(xdg_runtime, "voxquill.socket")

    def send_command(self, command):
        if not os.path.exists(self.socket_path):
            log(f"Server not running at {self.socket_path}")
            return False

        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.socket_path)
            msg = json.dumps({"command": command})
            client.sendall(msg.encode())
            client.close()
            return True
        except Exception as e:
            log(f"Failed to send IPC command: {e}")
            return False
