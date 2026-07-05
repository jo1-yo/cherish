#!/usr/bin/env python3
"""Cherish — local backend (stdlib only, no dependencies).

Every account action on the frontend goes through here:
  - Sign Up: email -> verification code -> user saved to users.json
  - Sign In: only registered emails may sign in; each login is recorded
The backend also serves its own live table of everything it has recorded,
at http://localhost:8082/ — no passcode, local dev only.

No email provider is configured, so verification codes are printed to this
terminal instead of actually emailed — that's the one thing you'd swap in
for production (e.g. call an email API from send_code_email below).

Run:  python3 backend/server.py [port]   (defaults to 8082)
"""
import json, os, random, re, string, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CODE_TTL_SECONDS = 10 * 60

os.makedirs(DATA_DIR, exist_ok=True)

# in-memory: pending verification codes, keyed by lowercased email
_pending_codes = {}


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def is_valid_email(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def send_code_email(email, code):
    """Stand-in for a real email provider (SMTP / Resend / SendGrid / ...).
    No credentials are configured for this local prototype, so the code is
    just printed here — read it from this terminal to complete signup."""
    print(f"\n{'='*50}\n  VERIFICATION CODE for {email}: {code}\n  (valid for {CODE_TTL_SECONDS // 60} minutes)\n{'='*50}\n")


ADMIN_TABLE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cherish Backend — Registered Users</title>
<style>
  body{font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;background:#FAF7F1;color:#2B2620;margin:0;padding:40px}
  h1{font-weight:600;font-size:1.4rem;letter-spacing:.04em}
  .sub{color:#6B6357;font-size:.85rem;margin-bottom:24px}
  table{border-collapse:collapse;width:100%;background:#fff;font-size:.9rem}
  th,td{border:1px solid #DED4C2;padding:10px 14px;text-align:left}
  th{background:#F2ECE1;font-size:.7rem;letter-spacing:.12em;text-transform:uppercase}
  .muted{color:#6B6357}
  .pill{display:inline-block;background:#F2ECE1;border:1px solid #DED4C2;border-radius:99px;padding:2px 10px;font-size:.75rem}
</style>
</head>
<body>
<h1>Cherish Backend — Registered Users</h1>
<p class="sub">Live from users.json · auto-refreshes every 5s · <span class="pill" id="count">…</span></p>
<table>
  <thead><tr><th>#</th><th>Name</th><th>Email</th><th>Registered At</th><th>Last Login</th><th>Logins</th></tr></thead>
  <tbody id="rows"><tr><td colspan="6" class="muted">Loading…</td></tr></tbody>
</table>
<script>
async function refresh(){
  const r = await fetch('/api/admin/users');
  const d = await r.json();
  document.getElementById('count').textContent = d.count + ' user' + (d.count===1?'':'s');
  document.getElementById('rows').innerHTML = d.users.length
    ? d.users.map((u,i)=>`<tr><td>${i+1}</td><td>${u.name}</td><td>${u.email}</td><td>${u.registeredAt}</td><td>${u.lastLoginAt||'—'}</td><td>${u.loginCount||0}</td></tr>`).join('')
    : '<tr><td colspan="6" class="muted">No one has registered yet.</td></tr>';
}
refresh(); setInterval(refresh, 5000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[backend] {self.address_string()} - {fmt % args}")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        if self.path in ("/", "/admin"):
            return self._send_html(ADMIN_TABLE_PAGE)
        if self.path == "/api/health":
            return self._send_json(200, {"ok": True, "service": "cherish-backend"})
        if self.path == "/api/admin/users":
            users = load_users()
            return self._send_json(200, {"ok": True, "count": len(users), "users": users})
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path == "/api/auth/request-code":
            return self._handle_request_code()
        if self.path == "/api/auth/verify-code":
            return self._handle_verify_code()
        if self.path == "/api/auth/login":
            return self._handle_login()
        self._send_json(404, {"ok": False, "error": "not found"})

    def _handle_request_code(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})

        code = "".join(random.choices(string.digits, k=6))
        _pending_codes[email] = {"code": code, "expires": time.time() + CODE_TTL_SECONDS}
        send_code_email(email, code)
        return self._send_json(200, {"ok": True, "message": "Verification code sent — check the backend terminal"})

    def _handle_verify_code(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        code = (body.get("code") or "").strip()
        name = (body.get("name") or "").strip()

        pending = _pending_codes.get(email)
        if not pending:
            return self._send_json(400, {"ok": False, "error": "Request a new code first"})
        if time.time() > pending["expires"]:
            del _pending_codes[email]
            return self._send_json(400, {"ok": False, "error": "That code expired — request a new one"})
        if code != pending["code"]:
            return self._send_json(400, {"ok": False, "error": "Incorrect code"})

        del _pending_codes[email]
        users = load_users()
        existing = next((u for u in users if u["email"] == email), None)
        if existing:
            if name:
                existing["name"] = name
            user = existing
        else:
            user = {
                "id": str(int(time.time() * 1000)),
                "email": email,
                "name": name or email.split("@")[0],
                "registeredAt": now_str(),
                "lastLoginAt": now_str(),
                "loginCount": 1,
            }
            users.append(user)
        save_users(users)
        return self._send_json(200, {"ok": True, "user": user})

    def _handle_login(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})

        users = load_users()
        user = next((u for u in users if u["email"] == email), None)
        if not user:
            return self._send_json(404, {"ok": False, "error": "No account for this email — please sign up first"})

        user["lastLoginAt"] = now_str()
        user["loginCount"] = int(user.get("loginCount", 0)) + 1
        save_users(users)
        return self._send_json(200, {"ok": True, "user": user})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Cherish backend on http://localhost:{PORT}")
    print(f"Live users table:   http://localhost:{PORT}/")
    print(f"Registered users stored in {USERS_FILE}\n")
    server.serve_forever()
