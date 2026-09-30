"""Self-contained smoke test for the VoxText server.

Boots a real uvicorn process on a free port, exercises the HTTP API against it,
then shuts it down - so it works even where background processes cannot outlive
a single command.

    .venv\\Scripts\\python.exe selftest.py

Deliberately avoids uploading valid audio: that would download the ~460 MB
Whisper model. Transcription is covered by tests/test_speech.py instead.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, extra: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"PASS  {label} {extra}".rstrip())
    else:
        FAILED.append(label)
        print(f"FAIL  {label} {extra}".rstrip())


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def wait_for_server(client: httpx.Client, base: str, timeout: float = 40.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.get(f"{base}/api/health")
            return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    port = free_port()
    base = f"http://{HOST}:{port}"

    env = dict(os.environ)
    env["WHISPER_WARM_ON_STARTUP"] = "false"
    env["DEBUG"] = "true"

    log = open(ROOT / "selftest-server.log", "w", encoding="utf-8", errors="replace")
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", HOST, "--port", str(port), "--log-level", "warning",
        ],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=15) as probe:
            ready = wait_for_server(probe, base)
            check("server boots", ready, f"(port {port})")
            if not ready:
                return 1
        run_checks(base)
        return 1 if FAILED else 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()
        print()
        print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
        for name in FAILED:
            print(f"  - {name}")


def run_checks(base: str) -> None:
    # Separate clients on purpose: one httpx.Client would keep the session
    # cookie in its jar after sign-up and silently send it on "anonymous"
    # requests, hiding auth bugs.
    anon = httpx.Client(trust_env=False, follow_redirects=False, timeout=30)
    user = httpx.Client(trust_env=False, follow_redirects=False, timeout=30)
    try:
        public_checks(anon, base)
        auth_checks(anon, user, base)
    finally:
        anon.close()
        user.close()


def public_checks(client: httpx.Client, base: str) -> None:
    r = client.get(f"{base}/api/health")
    check("GET /api/health -> 200", r.status_code == 200, f"({r.status_code})")
    body = r.json()
    check("health status ok", body.get("status") == "ok")
    check("health reports app name", body.get("app") == "VoxText", f"({body.get('app')})")

    r = client.get(f"{base}/")
    check(
        "GET / anonymous -> 302 to /login",
        r.status_code == 302 and r.headers.get("location") == "/login",
        f"({r.status_code} -> {r.headers.get('location')})",
    )
    check("X-Content-Type-Options set", r.headers.get("x-content-type-options") == "nosniff")
    check(
        "Permissions-Policy restricts microphone",
        "microphone=(self)" in r.headers.get("permissions-policy", ""),
    )

    for page in ("/login", "/signup"):
        r = client.get(f"{base}{page}")
        check(f"GET {page} -> 200", r.status_code == 200, f"({r.status_code})")
    for asset in ("/static/js/auth.js", "/static/style.css", "/static/app.js"):
        r = client.get(f"{base}{asset}")
        check(f"GET {asset} -> 200", r.status_code == 200, f"({r.status_code})")

    # Anonymous users must not reach any API.
    r = client.get(f"{base}/api/auth/me")
    check("GET /api/auth/me anonymous -> 401", r.status_code == 401, f"({r.status_code})")

    r = client.post(f"{base}/api/transcribe", files={"audio": ("a.wav", b"xx", "audio/wav")})
    check("transcribe anonymous -> 401", r.status_code == 401, f"({r.status_code})")

    r = client.post(f"{base}/api/auth/signup", json={"email": "not-an-email", "password": "short"})
    check("invalid signup payload -> 422", r.status_code == 422, f"({r.status_code})")

    r = client.post(
        f"{base}/api/auth/login",
        json={"email": "someone@example.com", "password": "whatever-123"},
        headers={"Origin": "https://evil.example"},
    )
    check("cross-origin login -> 403", r.status_code == 403, f"({r.status_code})")


def auth_checks(anon: httpx.Client, user: httpx.Client, base: str) -> None:
    email = f"smoke{int(time.time())}@example.com"

    r = user.post(
        f"{base}/api/auth/signup",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Smoke Test"},
    )
    check("POST /api/auth/signup -> 201", r.status_code == 201, f"({r.status_code} {r.text[:140]})")
    session = r.cookies.get("voxtext_session")
    check("session cookie issued", bool(session))

    # The cookie must never be readable by browser JavaScript.
    raw = r.headers.get("set-cookie", "").lower()
    check("session cookie is HttpOnly", "httponly" in raw, f"({raw[:90]})")
    check("session cookie is SameSite=Lax", "samesite=lax" in raw)
    cookie = {"Cookie": f"voxtext_session={session}"} if session else {}

    r = anon.post(
        f"{base}/api/auth/signup",
        json={"email": email.upper(), "password": "correct-horse-battery"},
    )
    check("duplicate email (different case) -> 409", r.status_code == 409, f"({r.status_code})")

    r = user.get(f"{base}/api/auth/me")
    ok = r.status_code == 200 and r.json().get("email") == email
    check("GET /api/auth/me -> 200 + correct email", ok, f"({r.status_code})")
    check("session cookie is sent and accepted", r.status_code == 200)

    r = user.get(f"{base}/")
    check("GET / signed in -> 200", r.status_code == 200, f"({r.status_code})")
    check(
        "signed-in dashboard is the real app page",
        b"transcrib" in r.content.lower(),
        f"({len(r.content)} bytes)",
    )
    r = user.get(f"{base}/login")
    check("GET /login signed in -> 302 to /", r.status_code == 302, f"({r.status_code})")

    # --- forged sessions are rejected ---------------------------------------
    # Same header+claims but a flipped signature byte: proves the cookie is
    # cryptographically verified, not merely base64-decoded.
    if session:
        head, _, sig = session.rpartition(".")
        flipped = ("Z" if sig[:1] != "Z" else "Y") + sig[1:]
        forged = {"Cookie": f"voxtext_session={head}.{flipped}"}
        r = anon.get(f"{base}/api/auth/me", headers=forged)
        check(
            "tampered signature -> 401",
            r.status_code == 401,
            f"({r.status_code} {r.text[:120]})",
        )
    r = anon.get(f"{base}/api/auth/me", headers={"Cookie": "voxtext_session=not-a-jwt"})
    check("garbage session cookie -> 401", r.status_code == 401, f"({r.status_code})")

    # --- login failures are indistinguishable --------------------------------
    bad = anon.post(f"{base}/api/auth/login", json={"email": email, "password": "definitely-wrong-1"})
    check("wrong password -> 401", bad.status_code == 401, f"({bad.status_code})")
    unknown = anon.post(
        f"{base}/api/auth/login", json={"email": "nobody404@example.com", "password": "definitely-wrong-1"}
    )
    check(
        "unknown email indistinguishable from wrong password",
        unknown.status_code == bad.status_code
        and unknown.json().get("detail") == bad.json().get("detail"),
    )

    good = anon.post(f"{base}/api/auth/login", json={"email": email, "password": "correct-horse-battery"})
    check("correct login -> 200", good.status_code == 200, f"({good.status_code})")

    # --- upload validation (never reaches the model) --------------------------
    # Snapshot the upload directory first: anything the server leaves behind
    # after these requests is a leak, and pre-existing files must not be
    # blamed on this run (or hide a real one).
    try:
        from app.config import get_settings  # noqa: PLC0415 - same .env as the server

        upload_dir = Path(get_settings().resolved_upload_dir)
    except Exception:  # pragma: no cover - fall back to the conventional path
        upload_dir = Path(os.environ.get("UPLOAD_DIR", ROOT / "uploads"))

    def uploads_present() -> list[str]:
        if not upload_dir.is_dir():
            return []
        return sorted(p.name for p in upload_dir.iterdir() if p.is_file())

    before_uploads = uploads_present()

    r = user.post(
        f"{base}/api/transcribe",
        files={"audio": ("notes.txt", b"not audio at all", "text/plain")},
    )
    check("unsupported extension -> 415", r.status_code == 415, f"({r.status_code} {r.text[:120]})")

    r = user.post(f"{base}/api/transcribe", files={"audio": ("song.mp4", b"", "audio/mp4")})
    check("empty upload -> 4xx", 400 <= r.status_code < 500, f"({r.status_code})")

    r = user.post(
        f"{base}/api/transcribe",
        data={"task": "sideways"},
        files={"audio": ("notes.txt", b"nope", "text/plain")},
    )
    check("unknown task -> 400", r.status_code == 400, f"({r.status_code})")

    # --- logout revokes the session -------------------------------------------
    # `anon` collected a cookie of its own during the login checks above, and
    # httpx merges the jar into every request; clear it so the replay below
    # sends exactly one cookie and cannot silently override the dead one.
    anon.cookies.clear()

    r = user.post(f"{base}/api/auth/logout")
    check("POST /api/auth/logout -> 204", r.status_code == 204, f"({r.status_code})")

    r = anon.get(f"{base}/api/auth/me", headers=cookie)
    check(
        "old cookie rejected after logout -> 401",
        r.status_code == 401,
        f"({r.status_code} {r.text[:120]})",
    )

    r = anon.get(f"{base}/", headers=cookie)
    check(
        "dashboard rejects the dead cookie -> 302 to /login",
        r.status_code == 302 and r.headers.get("location") == "/login",
        f"({r.status_code} {r.headers.get('location')})",
    )

    leaked = [name for name in uploads_present() if name not in before_uploads]
    check(
        "no orphaned uploads left behind",
        not leaked,
        f"(dir={upload_dir} leaked={leaked[:5]})",
    )


def unit_checks() -> None:
    """Path-traversal and filename guards, exercised directly."""
    from app.services.uploads import _safe_basename
    from app.services.errors import UploadError

    for hostile in (
        "..\\..\\..\\windows\\system32\\config\\sam",
        "../../../../etc/passwd",
        "/etc/passwd",
        "C:\\Users\\HP\\secrets.wav",
    ):
        name = _safe_basename(hostile)
        check(
            f"traversal neutralised: {hostile[:28]!r}",
            "\\" not in name and "/" not in name and name not in {"", ".", ".."},
            f"-> {name!r}",
        )

    for rejected in ("", "   ", ".", "..", "a/../..", "dir/"):
        try:
            got = _safe_basename(rejected)
            check(f"path-only name rejected: {rejected!r}", False, f"(accepted as {got!r})")
        except UploadError:
            check(f"path-only name rejected: {rejected!r}", True)

    try:
        _safe_basename("")
        check("missing filename raises UploadError", False)
    except UploadError:
        check("missing filename raises UploadError", True)


if __name__ == "__main__":
    unit_checks()
    sys.exit(main())

