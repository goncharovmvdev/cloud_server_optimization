import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .service import DEFAULT_POLICY_NAME, build_snapshot


STATIC_DIR = Path(__file__).resolve().parent / "static"


class VisualizationRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/snapshot":
            query = parse_qs(parsed.query)
            policy = query.get("policy", [DEFAULT_POLICY_NAME])[0]
            node_counts = _parse_node_counts(query)
            pod_requests = _parse_pod_requests(query)
            self._send_json(
                build_snapshot(
                    policy_name=policy,
                    node_counts=node_counts,
                    pod_requests=pod_requests,
                )
            )
            return

        if parsed.path == "/api/health":
            self._send_json({"status": "ok"})
            return

        if parsed.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the interactive cluster visualization dashboard.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), VisualizationRequestHandler)
    print(f"Visualization dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


def _parse_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except ValueError:
        return fallback


def _parse_node_counts(query: dict[str, list[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, values in query.items():
        if not key.startswith("count_"):
            continue
        pool_name = key.removeprefix("count_")
        counts[pool_name] = _parse_int(values[0], 0)
    return counts


def _parse_pod_requests(query: dict[str, list[str]]) -> list[dict]:
    raw_pods = query.get("pods", [])
    if not raw_pods:
        return []

    try:
        parsed = json.loads(raw_pods[0])
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []
    return parsed


if __name__ == "__main__":
    main()
