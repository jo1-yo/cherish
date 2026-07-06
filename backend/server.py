#!/usr/bin/env python3
"""Cherish — backend (stdlib only, no dependencies). Runs locally and on Render.

What goes through here:
  - Sign Up: email -> verification code (emailed via Resend) -> user saved
  - Sign In: only registered emails; every login recorded
  - Orders: checkout posts the order here so it shows on every admin device
  - Interest list: homepage invite + footer signup emails, viewable in admin
  - Site content: admin's homepage words / photos / product edits are saved
    globally (POST /api/admin/content) so every visitor sees them
  - Admin reads (users + orders tables) require the admin key

Configuration is all environment variables (sane local defaults):
  PORT              port to listen on (Render injects this; local default 8082)
  ADMIN_KEY         admin passcode for the dashboard + admin API (default "Cherish")
  RESEND_API_KEY    if set, verification codes are emailed via resend.com;
                    if unset, codes are printed to this log (local dev)
  EMAIL_FROM        sender, e.g. "Cherish <hello@cherishthestudio.com>"
                    (default Cherish domain sender)
  GITHUB_TOKEN      if set, storage moves to GitHub (Render's free disk is
                    ephemeral): users -> DATA_REPO, content+images -> SITE_REPO
                    (committing to SITE_REPO redeploys GitHub Pages, so edits
                    reach the live site in ~1 minute)
  SITE_REPO         default "jo1-yo/cherish"        (public site repo)
  DATA_REPO         default "jo1-yo/cherish-data"   (private, users.json)

Run locally:  python3 backend/server.py [port]
"""
import base64, datetime, hashlib, hmac, json, os, random, re, string, sys, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from zoneinfo import ZoneInfo
    NY_TZ = ZoneInfo("America/New_York")
except Exception:                                      # no tzdata on the host
    NY_TZ = datetime.timezone(datetime.timedelta(hours=-5), "EST")

# line-buffer stdout so verification codes show up in Render/log files immediately
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(BACKEND_DIR)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8082))
ADMIN_KEY = (os.environ.get("ADMIN_KEY", "").strip() or "Cherish")
if ADMIN_KEY.lower() == "cherish":
    ADMIN_KEY = "Cherish"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM") or "Cherish <hello@cherishthestudio.com>"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SITE_REPO = os.environ.get("SITE_REPO", "jo1-yo/cherish")
DATA_REPO = os.environ.get("DATA_REPO", "jo1-yo/cherish-data")
CODE_TTL_SECONDS = 10 * 60

# in-memory: pending verification codes, keyed by lowercased email
_pending_codes = {}


def now_str():
    """New York time — all timestamps the admin dashboard shows."""
    return datetime.datetime.now(NY_TZ).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- GitHub API
def _gh_request(method, url, payload=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "cherish-backend")
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=20) as resp:
        return json.loads(resp.read() or "{}")


def gh_get_file(repo, path):
    """Return (bytes, sha) or (None, None) if the file doesn't exist."""
    try:
        d = _gh_request("GET", f"https://api.github.com/repos/{repo}/contents/{path}")
        return base64.b64decode(d["content"]), d["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise


def gh_put_file(repo, path, raw_bytes, message, sha=None):
    """Create or update a file in the repo (contents API)."""
    if sha is None:
        _, sha = gh_get_file(repo, path)
    payload = {"message": message, "content": base64.b64encode(raw_bytes).decode()}
    if sha:
        payload["sha"] = sha
    _gh_request("PUT", f"https://api.github.com/repos/{repo}/contents/{path}", payload)


# ---------------------------------------------------------------- storage
# Local mode (no GITHUB_TOKEN): plain files in the site folder.
# GitHub mode: users.json in the private DATA_REPO; site-content.json and
# uploaded images committed to the public SITE_REPO (GitHub Pages serves them).
CONTENT_REL = "site-content.json"
UPLOADS_REL = "images/uploads"

os.makedirs(os.path.join(BACKEND_DIR, "data"), exist_ok=True)


def _decode_records(raw):
    try:
        return json.loads(raw) if raw else []
    except (TypeError, json.JSONDecodeError):
        return []


def _load_records_with_sha(filename):
    """users.json / orders.json — a JSON list, in DATA_REPO or a local file."""
    if GITHUB_TOKEN:
        raw, sha = gh_get_file(DATA_REPO, filename)
        return _decode_records(raw), sha
    p = os.path.join(BACKEND_DIR, "data", filename)
    if not os.path.exists(p):
        return [], None
    try:
        with open(p) as f:
            return json.load(f), None
    except (json.JSONDecodeError, OSError):
        return [], None


def _load_records(filename):
    records, _ = _load_records_with_sha(filename)
    return records


def _save_records(filename, records, message, sha=None):
    raw = json.dumps(records, indent=2).encode()
    if GITHUB_TOKEN:
        gh_put_file(DATA_REPO, filename, raw, message, sha)
    else:
        with open(os.path.join(BACKEND_DIR, "data", filename), "wb") as f:
            f.write(raw)


def load_users():
    return _load_records("users.json")


def save_users(users):
    _save_records("users.json", users, "Update users")


def load_orders():
    return _load_records("orders.json")


def save_orders(orders):
    _save_records("orders.json", orders, "Update orders")


def load_interest():
    return _load_records("interest.json")


def save_interest(entries):
    _save_records("interest.json", entries, "Update interest list")


def add_interest(email, source="site", ip="-", joined_at=None):
    """Add an email to the marketing list once, preserving the first source."""
    email = (email or "").strip().lower()
    if not is_valid_email(email):
        return False
    entry = {
        "email": email,
        "joinedAt": joined_at or now_str(),
        "source": str(source or "site")[:40],
        "ip": ip or "-",
    }
    for attempt in range(4):
        entries, sha = _load_records_with_sha("interest.json")
        if any(e.get("email") == email for e in entries):
            return False
        entries.insert(0, entry)
        try:
            _save_records("interest.json", entries, "Update interest list", sha)
            return True
        except urllib.error.HTTPError as e:
            if GITHUB_TOKEN and e.code == 409 and attempt < 3:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise
    return False


def interest_with_registered_users():
    """Admin view guarantee: every registered user also appears in Interest List."""
    entries = load_interest()
    seen = {str(e.get("email", "")).strip().lower() for e in entries}
    changed = False
    for user in load_users():
        email = str(user.get("email", "")).strip().lower()
        if is_valid_email(email) and email not in seen:
            entries.insert(0, {
                "email": email,
                "joinedAt": user.get("registeredAt") or now_str(),
                "source": "registered-user",
                "ip": "-",
            })
            seen.add(email)
            changed = True
    if changed:
        save_interest(entries)
    return entries


def load_content():
    if GITHUB_TOKEN:
        raw, _ = gh_get_file(SITE_REPO, CONTENT_REL)
        return json.loads(raw) if raw else {}
    p = os.path.join(SITE_DIR, CONTENT_REL)
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_content(content):
    raw = json.dumps(content, indent=2).encode()
    if GITHUB_TOKEN:
        gh_put_file(SITE_REPO, CONTENT_REL, raw, "Update site content from admin")
    else:
        with open(os.path.join(SITE_DIR, CONTENT_REL), "wb") as f:
            f.write(raw)


def save_image(key, raw_bytes):
    """Store an uploaded homepage photo; returns its site-relative path."""
    rel = f"{UPLOADS_REL}/{key}.jpg"
    if GITHUB_TOKEN:
        gh_put_file(SITE_REPO, rel, raw_bytes, f"Update homepage photo {key}")
    else:
        p = os.path.join(SITE_DIR, UPLOADS_REL)
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(SITE_DIR, rel), "wb") as f:
            f.write(raw_bytes)
    return rel


# ---------------------------------------------------------------- email
def is_valid_email(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def is_valid_password(password):
    return len(password or "") >= 8


def hash_password(password, salt=None):
    salt = salt or base64.b64encode(os.urandom(16)).decode()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000)
    return "pbkdf2_sha256${}${}".format(salt, base64.b64encode(digest).decode())


def verify_password(password, stored):
    try:
        algo, salt, _ = str(stored or "").split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def public_user(user):
    return {k: v for k, v in dict(user or {}).items() if k != "passwordHash"}


def send_code_email(email, code):
    """Email the code via Resend; without an API key, print it to the log."""
    if not RESEND_API_KEY:
        print(f"\n{'='*50}\n  VERIFICATION CODE for {email}: {code}\n  (valid for {CODE_TTL_SECONDS // 60} minutes)\n{'='*50}\n")
        return
    req = urllib.request.Request("https://api.resend.com/emails", method="POST")
    req.add_header("Authorization", f"Bearer {RESEND_API_KEY}")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "CherishBackend/1.0 (hello@cherishthestudio.com)")
    body = json.dumps({
        "from": EMAIL_FROM,
        "to": [email],
        "subject": f"{code} is your Cherish verification code",
        "html": (
            "<div style=\"font-family:Georgia,serif;max-width:420px;margin:0 auto;"
            "padding:32px;color:#2B2620\">"
            "<h2 style=\"font-weight:400;letter-spacing:.08em\">Cherish</h2>"
            "<p>Your verification code:</p>"
            f"<p style=\"font-size:2rem;letter-spacing:.3em;font-weight:600\">{code}</p>"
            "<p style=\"color:#6B6357;font-size:.85rem\">It expires in 10 minutes. "
            "If you didn't request this, you can ignore this email.</p></div>"
        ),
    }).encode()
    try:
        urllib.request.urlopen(req, body, timeout=15)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(detail)
            detail = payload.get("message") or payload.get("error") or detail
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"Resend rejected the email: {detail}") from e
    print(f"[email] verification code sent to {email}")


# ---------------------------------------------------------------- handler
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Key")
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

    def _is_admin(self):
        return self.headers.get("X-Admin-Key", "") == ADMIN_KEY

    def _client_ip(self):
        """Real visitor IP — Render sits behind a proxy, so prefer X-Forwarded-For."""
        fwd = self.headers.get("X-Forwarded-For", "")
        return (fwd.split(",")[0].strip() if fwd else "") or self.client_address[0]

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        if self.path in ("/", "/admin"):
            self.send_response(302)
            self.send_header("Location", "https://cherishthestudio.com/admin.html")
            self.end_headers()
            return
        if self.path == "/api/health":
            return self._send_json(200, {
                "ok": True, "service": "cherish-backend",
                "email": "resend" if RESEND_API_KEY else "log-only",
                "storage": "github" if GITHUB_TOKEN else "local-files",
            })
        if self.path == "/api/content":
            return self._send_json(200, {"ok": True, "content": load_content()})
        if self.path == "/api/admin/users":
            if not self._is_admin():
                return self._send_json(401, {"ok": False, "error": "Access denied"})
            users = load_users()
            return self._send_json(200, {"ok": True, "count": len(users), "users": [public_user(u) for u in users]})
        if self.path == "/api/admin/orders":
            if not self._is_admin():
                return self._send_json(401, {"ok": False, "error": "Access denied"})
            orders = load_orders()
            return self._send_json(200, {"ok": True, "count": len(orders), "orders": orders})
        if self.path == "/api/admin/interest":
            if not self._is_admin():
                return self._send_json(401, {"ok": False, "error": "Access denied"})
            entries = interest_with_registered_users()
            return self._send_json(200, {"ok": True, "count": len(entries), "interest": entries})
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        routes = {
            "/api/auth/request-code": self._handle_request_code,
            "/api/auth/verify-code": self._handle_verify_code,
            "/api/auth/login": self._handle_login,
            "/api/auth/request-reset": self._handle_request_reset,
            "/api/auth/reset-password": self._handle_reset_password,
            "/api/orders": self._handle_place_order,
            "/api/interest": self._handle_join_interest,
            "/api/admin/verify-key": self._handle_verify_key,
            "/api/admin/content": self._handle_save_content,
        }
        handler = routes.get(self.path)
        if handler:
            try:
                return handler()
            except Exception as e:                     # noqa: BLE001 — surface any failure as JSON
                print(f"[error] {self.path}: {e}")
                return self._send_json(500, {"ok": False, "error": f"Server error: {e}"})
        self._send_json(404, {"ok": False, "error": "not found"})

    # ---- auth ----
    def _handle_request_code(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})

        code = "".join(random.choices(string.digits, k=6))
        _pending_codes[email] = {"code": code, "expires": time.time() + CODE_TTL_SECONDS, "purpose": "register"}
        try:
            send_code_email(email, code)
        except Exception as e:                         # noqa: BLE001
            detail = str(e)
            print(f"[email] FAILED to send to {email}: {detail} — code is {code}")
            if "testing emails" in detail.lower():
                detail = "Resend is still in test mode. Verify cherishthestudio.com in Resend and send from hello@cherishthestudio.com."
            return self._send_json(502, {"ok": False, "error": f"Couldn't send the email: {detail}"})
        sent_via = "email" if RESEND_API_KEY else "backend log"
        return self._send_json(200, {"ok": True, "message": f"Verification code sent via {sent_via}"})

    def _handle_verify_code(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        code = (body.get("code") or "").strip()
        name = (body.get("name") or "").strip()
        password = (body.get("password") or "").strip()

        pending = _pending_codes.get(email)
        if not pending:
            return self._send_json(400, {"ok": False, "error": "Request a new code first"})
        if pending.get("purpose") not in ("register", None):
            return self._send_json(400, {"ok": False, "error": "Request a new sign-up code first"})
        if time.time() > pending["expires"]:
            del _pending_codes[email]
            return self._send_json(400, {"ok": False, "error": "That code expired — request a new one"})
        if code != pending["code"]:
            return self._send_json(400, {"ok": False, "error": "Incorrect code"})
        if not is_valid_password(password):
            return self._send_json(400, {"ok": False, "error": "Password must be at least 8 characters"})

        del _pending_codes[email]
        users = load_users()
        existing = next((u for u in users if u["email"] == email), None)
        if existing:
            if name:
                existing["name"] = name
            existing["passwordHash"] = hash_password(password)
            user = existing
        else:
            user = {
                "id": str(int(time.time() * 1000)),
                "email": email,
                "name": name or email.split("@")[0],
                "passwordHash": hash_password(password),
                "registeredAt": now_str(),
                "lastLoginAt": now_str(),
                "loginCount": 1,
            }
            users.append(user)
        save_users(users)
        add_interest(email, "registered-user", self._client_ip(), user.get("registeredAt") or now_str())
        return self._send_json(200, {"ok": True, "user": public_user(user)})

    def _handle_login(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        password = (body.get("password") or "").strip()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})
        if not password:
            return self._send_json(400, {"ok": False, "error": "Please enter your password"})

        users = load_users()
        user = next((u for u in users if u["email"] == email), None)
        if not user:
            return self._send_json(404, {"ok": False, "error": "No account for this email — please sign up first"})
        if not user.get("passwordHash"):
            return self._send_json(409, {"ok": False, "error": "Please reset your password to finish signing in"})
        if not verify_password(password, user.get("passwordHash")):
            return self._send_json(401, {"ok": False, "error": "Incorrect email or password"})

        user["lastLoginAt"] = now_str()
        user["loginCount"] = int(user.get("loginCount", 0)) + 1
        save_users(users)
        return self._send_json(200, {"ok": True, "user": public_user(user)})

    def _handle_request_reset(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})

        users = load_users()
        if not any(u.get("email") == email for u in users):
            return self._send_json(404, {"ok": False, "error": "No account for this email — please sign up first"})

        code = "".join(random.choices(string.digits, k=6))
        _pending_codes[email] = {"code": code, "expires": time.time() + CODE_TTL_SECONDS, "purpose": "reset"}
        try:
            send_code_email(email, code)
        except Exception as e:                         # noqa: BLE001
            detail = str(e)
            print(f"[email] FAILED to send password reset to {email}: {detail} — code is {code}")
            return self._send_json(502, {"ok": False, "error": f"Couldn't send the email: {detail}"})
        return self._send_json(200, {"ok": True, "message": "Password reset code sent"})

    def _handle_reset_password(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        code = (body.get("code") or "").strip()
        password = (body.get("password") or "").strip()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})
        if not is_valid_password(password):
            return self._send_json(400, {"ok": False, "error": "Password must be at least 8 characters"})

        pending = _pending_codes.get(email)
        if not pending or pending.get("purpose") != "reset":
            return self._send_json(400, {"ok": False, "error": "Request a reset code first"})
        if time.time() > pending["expires"]:
            del _pending_codes[email]
            return self._send_json(400, {"ok": False, "error": "That code expired — request a new one"})
        if code != pending["code"]:
            return self._send_json(400, {"ok": False, "error": "Incorrect code"})

        users = load_users()
        user = next((u for u in users if u["email"] == email), None)
        if not user:
            return self._send_json(404, {"ok": False, "error": "No account for this email — please sign up first"})

        del _pending_codes[email]
        user["passwordHash"] = hash_password(password)
        user["lastLoginAt"] = now_str()
        user["loginCount"] = int(user.get("loginCount", 0)) + 1
        save_users(users)
        add_interest(email, "registered-user", self._client_ip(), user.get("registeredAt") or now_str())
        return self._send_json(200, {"ok": True, "user": public_user(user)})

    # ---- orders ----
    def _handle_place_order(self):
        """Checkout. The cart sends the signed-in customer + invoice lines;
        the order id / tracking / status are minted here so every admin
        device sees the same record."""
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please sign in before checking out"})
        lines_in = body.get("lines")
        if not isinstance(lines_in, list) or not lines_in:
            return self._send_json(400, {"ok": False, "error": "Your bag is empty"})

        lines = []
        for l in lines_in[:50]:
            if not isinstance(l, dict):
                continue
            lines.append({
                "name": str(l.get("name", ""))[:120],
                "detail": str(l.get("detail", ""))[:200],
                "qty": max(1, int(l.get("qty", 1) or 1)),
                "price": round(float(l.get("price", 0) or 0), 2),
            })
        if not lines:
            return self._send_json(400, {"ok": False, "error": "Your bag is empty"})

        orders = load_orders()
        existing_ids = {o.get("id") for o in orders}
        order_id = "CH" + "".join(random.choices(string.digits, k=5))
        while order_id in existing_ids:
            order_id = "CH" + "".join(random.choices(string.digits, k=5))

        def _num(key):
            try:
                return round(float(body.get(key, 0) or 0), 2)
            except (TypeError, ValueError):
                return 0

        order = {
            "id": order_id,
            "date": now_str(),
            "email": email,
            "name": (str(body.get("name", "")).strip() or email.split("@")[0])[:80],
            "items": sum(l["qty"] for l in lines),
            "lines": lines,
            "subtotal": _num("subtotal"),
            "shipping": _num("shipping"),
            "total": _num("total"),
            "status": "In production",
            "tracking": "1Z" + "".join(random.choices(string.digits, k=9)),
        }
        orders.insert(0, order)
        save_orders(orders)
        print(f"[order] {order_id} — {email} — ${order['total']}")
        return self._send_json(200, {"ok": True, "order": order})

    # ---- interest list ----
    def _handle_join_interest(self):
        body = self._read_json_body()
        email = (body.get("email") or "").strip().lower()
        if not is_valid_email(email):
            return self._send_json(400, {"ok": False, "error": "Please enter a valid email address"})
        source = str(body.get("source") or "site")[:40]

        joined = add_interest(email, source, self._client_ip())
        if not joined:
            return self._send_json(200, {"ok": True, "already": True})
        print(f"[interest] {email} joined via {source}")
        return self._send_json(200, {"ok": True, "already": False})

    # ---- admin ----
    def _handle_verify_key(self):
        if not self._is_admin():
            return self._send_json(401, {"ok": False, "error": "Access denied"})
        return self._send_json(200, {"ok": True})

    def _handle_save_content(self):
        """Merge the provided sections into site content. Payload may contain:
        cats (list|None), products (list|None), images ({key: dataURL}|None).
        None means "reset that section to defaults". Uploaded images are
        stored as real files; content keeps only their paths."""
        if not self._is_admin():
            return self._send_json(401, {"ok": False, "error": "Access denied"})
        body = self._read_json_body()
        content = load_content()

        for section in ("cats", "products"):
            if section in body:
                if body[section] is None:
                    content.pop(section, None)
                else:
                    content[section] = body[section]

        if "images" in body:
            if body["images"] is None:
                content.pop("images", None)
            else:
                stored = content.get("images", {})
                for key, data_url in body["images"].items():
                    if not re.match(r"^[\w-]+$", key):
                        continue
                    if isinstance(data_url, str) and data_url.startswith("data:image"):
                        raw = base64.b64decode(data_url.split(",", 1)[1])
                        stored[key] = save_image(key, raw)
                content["images"] = stored

        content["updatedAt"] = now_str()
        save_content(content)
        note = " (live site updates in ~1 minute)" if GITHUB_TOKEN else ""
        return self._send_json(200, {"ok": True, "message": f"Saved{note}", "content": content})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Cherish backend on http://localhost:{PORT}")
    print(f"  email:   {'Resend' if RESEND_API_KEY else 'log-only (codes print here)'}")
    print(f"  storage: {'GitHub (' + SITE_REPO + ' / ' + DATA_REPO + ')' if GITHUB_TOKEN else 'local files'}")
    server.serve_forever()
