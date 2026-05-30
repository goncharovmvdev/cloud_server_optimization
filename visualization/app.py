"""HTTP-сервер дашборда визуализации."""

from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .service import build_snapshot


STATIC_DIR = Path(__file__).resolve().parent / "static"
_NODE_COUNT_PREFIX = "count_"


class VisualizationRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/snapshot":
            query = parse_qs(parsed.query)
            self._send_json(
                build_snapshot(
                    node_counts=_parse_node_counts(query),
                    pod_requests=_parse_pod_requests(query),
                )
            )
            return

        if parsed.path == "/api/health":
            self._send_json({"status": "ok"})
            return

        if parsed.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _parse_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except ValueError:
        return fallback


def _parse_node_counts(query: dict[str, list[str]]) -> dict[str, int]:
    return {
        key.removeprefix(_NODE_COUNT_PREFIX): _parse_int(values[0], 0)
        for key, values in query.items()
        if key.startswith(_NODE_COUNT_PREFIX) and values
    }


def _parse_pod_requests(query: dict[str, list[str]]) -> list[dict[str, Any]]:
    raw_pods = query.get("pods", [])
    if not raw_pods:
        return []

    try:
        parsed = json.loads(raw_pods[0])
    except json.JSONDecodeError:
        return []

    return parsed if isinstance(parsed, list) else []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the interactive cluster visualization dashboard",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), VisualizationRequestHandler)
    print(f"Visualization dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
