import json
import socket

from .service import SOCKET


def request(operation="status", **parameters):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(8)
        try:
            connection.connect(SOCKET)
        except (FileNotFoundError, ConnectionRefusedError) as error:
            raise RuntimeError("Freiren Quiet 서비스가 실행되지 않았습니다.") from error
        connection.sendall((json.dumps({"op": operation, **parameters}) + "\n").encode())
        stream = connection.makefile("rb")
        response = json.loads(stream.readline(65536))
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "서비스 요청 실패"))
        return response["status"]
