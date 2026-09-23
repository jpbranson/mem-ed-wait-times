"""Local review server with a single, rate-limited free routing gateway. Not a deployment."""

import argparse
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from edwait.data import METRIC, load_history, registry, timestamp
from edwait.latest import build_latest
from edwait.routing import Router, RoutingError

ROOT = Path(__file__).resolve().parents[1]


class ReviewHandler(SimpleHTTPRequestHandler):
    router = Router()
    live_s3 = False
    s3 = None
    cache = None
    cached_at = 0
    cache_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dashboard" / "_site"), **kwargs)

    def log_message(self, *args):
        # No request/body/coordinate logging, including malformed requests.
        pass

    def send_body(self, body, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/routes":
            return self.send_body(b'{"error":"not_found"}', status=404)
        port = self.server.server_address[1]
        host = self.headers.get("Host")
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}") or self.headers.get("Origin") != f"http://{host}":
            return self.send_body(b'{"error":"origin_rejected"}', status=403)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 512 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Invalid request")
            self.connection.settimeout(5)
            request = json.loads(self.rfile.read(size))
            result = self.router.matrix(request)
            self.send_body(json.dumps(result, allow_nan=False).encode())
        except RoutingError as error:
            code = str(error)
            status = (429 if code in ("rate_limited", "provider_limit_reached", "request_budget_exhausted") else
                      503 if code in ("routing_unavailable", "routing_not_configured", "routing_access_denied", "request_budget_unavailable") else 422)
            self.send_body(json.dumps({"error": code}).encode(), status=status)
        except (ValueError, OSError):
            self.send_body(b'{"error":"invalid_request"}', status=400)

    @classmethod
    def recent_readings(cls):
        with cls.cache_lock:
            if cls.cache is not None and time.monotonic() - cls.cached_at < 30:
                return cls.cache
            if cls.s3 is None:
                import boto3
                cls.s3 = boto3.client("s3", region_name="us-east-1")
            now = datetime.now(timezone.utc)
            history = load_history(cls.s3, "mem-ed-wait-times", now - timedelta(hours=2), now, now=now)
            rows = [r for r in history.records if r["metric"] == METRIC]
            newest = max((timestamp(r["batch_id"]) for r in rows), default=None)
            rows = [r for r in rows if timestamp(r["batch_id"]) == newest]
            attempts = {r["facility"]: {"batch_id": r["batch_id"], "attempted_at": r["observed_at"],
                        "state": "success", "error_code": None} for r in rows}
            generated = max((timestamp(r["observed_at"]) for r in rows), default=now).isoformat()
            cls.cache = json.dumps(build_latest(None, rows, attempts, registry(), generated_at=generated)).encode()
            cls.cached_at = time.monotonic()
            return cls.cache

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/routes/status":
            # Lets the page keep Compare disabled where no gateway exists (static S3).
            available = bool(self.router.api_key)
            return self.send_body(json.dumps({"schema_version": 1, "available": available}).encode())
        if path == "/data/latest.json" and self.live_s3:
            try:
                return self.send_body(self.recent_readings())
            except Exception:
                return self.send_body(b'{"error":"preview_history_read_failed"}', status=503)
        if path in ("/", "/index.html"):
            page = (ROOT / "dashboard" / "_site" / "index.html").read_text(encoding="utf-8")
            banner = '<div class="review-banner">Local preview · not deployed</div>'
            position = page.index(">", page.index("<body")) + 1
            return self.send_body((page[:position] + banner + page[position:]).encode(), "text/html; charset=utf-8")
        super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--live-s3", action="store_true", help="Read recent S3 batches; pre-M0 collection failures remain unknown")
    args = parser.parse_args()
    ReviewHandler.live_s3 = args.live_s3
    print(f"Local review: http://127.0.0.1:{args.port} (not deployed)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), ReviewHandler).serve_forever()


if __name__ == "__main__":
    main()
