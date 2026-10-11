"""Client for the local controller socket."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from .core import ControllerError
from .server import socket_path


def call(operation: str, path: Path | None = None, _source: str = "local", **args):
    destination = Path(path or socket_path())
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(125)
            connection.connect(str(destination))
            connection.sendall(
                (
                    json.dumps({"op": operation, "args": args, "source": _source}, ensure_ascii=False) + "\n"
                ).encode()
            )
            with connection.makefile("rb") as incoming:
                line = incoming.readline(1024 * 1024)
    except (OSError, TimeoutError) as exc:
        raise ControllerError("컨트롤러 서비스에 연결하지 못했어요. 사용자 서비스를 확인해 주세요.") from exc
    if not line:
        raise ControllerError("컨트롤러가 응답하지 않았어요.")
    try:
        response = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ControllerError("컨트롤러 응답을 읽지 못했어요.") from exc
    if not response.get("ok"):
        raise ControllerError(response.get("error", "요청을 처리하지 못했어요."))
    return response["result"]
