#!/usr/bin/env python3
"""Tiny static server for local preview — sends no-cache headers so every
reload picks up the latest edits (avoids stale HTML/CSS/JS during dev)."""
import http.server, socketserver, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


with socketserver.TCPServer(("", PORT), NoCacheHandler) as httpd:
    print(f"Cherish preview on http://localhost:{PORT}  (no-cache)")
    httpd.serve_forever()
