"""Regressions shared with quiet-controller-plugin (identical hardware/client code)."""

import json
import shutil
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from freiren_quiet import client
from freiren_quiet.hardware import Hardware


class UnsupportedHardwareRegressionTests(unittest.TestCase):
    def test_missing_dmi_or_cpufreq_is_a_clear_refusal(self):
        # An empty /sys (VMs, containers, non-Intel) used to raise a bare
        # FileNotFoundError instead of the documented refusal.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "GL62 6QE / intel_pstate"):
                Hardware(Path(directory)).validate()


class ClientRejectedPeerRegressionTests(unittest.TestCase):
    def listen(self):
        runtime = tempfile.mkdtemp(prefix="fq-")
        self.addCleanup(shutil.rmtree, runtime, ignore_errors=True)
        path = str(Path(runtime) / "control.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(path)
        server.listen(1)
        return server, path

    def test_rejection_reply_is_read_even_if_service_closed_first(self):
        # serve() answers a rejected UID before reading the request and closes.
        # If that happened before the client's sendall, the CLI showed
        # "Broken pipe" instead of the permission error.
        server, path = self.listen()
        closed = threading.Event()

        def reject():
            connection, _ = server.accept()
            with connection:
                reply = {"ok": False, "error": "이 사용자는 장치 제어 권한이 없습니다."}
                connection.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode())
            closed.set()

        class LateSocket(socket.socket):
            def sendall(self, data, *args):
                if threading.current_thread() is threading.main_thread():
                    closed.wait(5)
                return super().sendall(data, *args)

        thread = threading.Thread(target=reject, daemon=True)
        thread.start()
        with (
            patch.object(client, "SOCKET", path),
            patch.object(client.socket, "socket", LateSocket),
            self.assertRaisesRegex(RuntimeError, "권한"),
        ):
            client.request("mode", mode="performance")
        thread.join(5)

    def test_closed_connection_without_reply_is_a_clean_error(self):
        server, path = self.listen()

        def crash():
            connection, _ = server.accept()
            with connection:
                connection.recv(4096)

        thread = threading.Thread(target=crash, daemon=True)
        thread.start()
        with (
            patch.object(client, "SOCKET", path),
            self.assertRaisesRegex(RuntimeError, "응답하지 않았습니다"),
        ):
            client.request()
        thread.join(5)


if __name__ == "__main__":
    unittest.main()
