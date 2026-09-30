# VoxText

Privacy-first speech-to-text web app: record from the microphone or drop in an
audio file, and get a transcript back from a **local**
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) model. Nothing is
sent to a third-party API and no cloud key is involved.

Accounts gate the whole product: the transcriber at `/` is only reachable once
signed in, and every transcription request is authenticated.

---

## Quick start (Windows)

```bat
setup.cmd          REM create .venv and install requirements
run.cmd            REM serve on http://127.0.0.1:8000
```

Then open **http://127.0.0.1:8000** — you land on `/login`; create an account
and start transcribing. `run.cmd --reload` also restarts on code changes.

> `setup.cmd` builds the virtualenv with an explicit interpreter path rather
> than the bare `python` on `PATH`. On this machine `PATH` resolves `python` to
> a half-deleted Anaconda install that dies with `ModuleNotFoundError: No
> module named 'encodings'`. Edit `WORKING_PY` in `setup.cmd` on other machines.

### Any other platform

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The **first** transcription downloads the model weights (~460 MB for the
default `small` model) into the Hugging Face cache. Either set
`WHISPER_WARM_ON_STARTUP=true` to pay that cost at boot, or the first request
pays it.

---

## Project structure

```
whisper-app/
├── main.py                    # app wiring, middleware, page routes, routers
├── app/
│   ├── config.py              # pydantic-settings; every knob from .env
│   ├── db.py                  # engine, Session, init_db(), get_db()
│   ├── models.py              # User (the only table so far - see Next steps)
│   ├── schemas.py             # request/response models
│   ├── routers/
│   │   ├── auth.py            # /api/auth/signup|login|logout|me
│   │   ├── speech.py          # /api/transcribe
│   │   └── health.py          # /api/health
│   ├── security/
│   │   ├── passwords.py       # bcrypt hashing + dummy verify for flat timing
│   │   ├── tokens.py          # signed session tokens (jti, exp)
│   │   ├── cookies.py         # HttpOnly cookie set/clear
│   │   ├── deps.py            # get_current_user, origin guard, page guard
│   │   ├── revocation.py      # in-memory jti deny-list for signed-out tokens
│   │   ├── rate_limit.py      # in-memory sign-in attempt limiter
│   │   └── errors.py          # AuthError -> 401
│   └── services/
│       ├── uploads.py         # streamed, validated, size-capped uploads
│       ├── speech.py          # faster-whisper wrapper (lazy, thread-safe)
│       └── errors.py          # UploadError, SpeechEngineError
├── public/                    # static frontend, served under /static
│   ├── index.html             # transcriber (authenticated)
│   ├── login.html, signup.html
│   ├── app.js                 # recording, visualizer, drag-and-drop, API call
│   ├── js/auth.js             # sign-in / sign-up / sign-out wiring
│   └── style.css
├── tests/                     # pytest suite (auth, security, speech access)
├── selftest.py                # boots a real uvicorn and smoke-tests it
├── verify.ps1                 # the same smoke test in PowerShell
├── .env.example               # copy to .env
├── setup.cmd, run.cmd         # Windows convenience wrappers
└── requirements.txt
```

Generated at runtime and git-ignored: `.env`, `voxtext.db*`, `uploads/`,
`instance/dev_secret.key`, `.venv/`.

---

## HTTP surface

| Method | Path                 | Auth                            | Notes                                        |
| ------ | -------------------- | ------------------------------- | -------------------------------------------- |
| GET    | `/`                  | session, else 302 to `/login`   | transcriber page                             |
| GET    | `/login`, `/signup`  | none (302 to `/` if signed in)  | auth pages                                   |
| GET    | `/static/...`        | none                            | `public/` mounted under one explicit prefix  |
| POST   | `/api/auth/signup`   | public, same-origin             | 201, starts a session                        |
| POST   | `/api/auth/login`    | public, same-origin             | rate limited, timing-equalised               |
| POST   | `/api/auth/logout`   | same-origin                     | 204, clears cookie **and** revokes the token |
| GET    | `/api/auth/me`       | session or bearer               | current user                                 |
| POST   | `/api/transcribe`    | session or bearer               | multipart `audio` plus `task` form field     |
| GET    | `/api/health`        | none                            | model readiness for load probes              |

`task` is `transcribe` or `translate`. Errors are returned as
`{"detail": "..."}`; unexpected exceptions are logged server-side and reported
to the client as a generic 500.

---

## Configuration

Everything is environment driven (`.env.example`, implemented in
`app/config.py`). No secret is hard-coded and none reaches the browser.

| Variable                   | Default                    | Meaning                                           |
| -------------------------- | -------------------------- | ------------------------------------------------- |
| `DEBUG`                    | `true`                     | enables `/api/docs` and the auto dev secret       |
| `SECRET_KEY`               | auto-generated in DEBUG    | token signing key; **required when DEBUG=false**  |
| `SESSION_MAX_AGE_SECONDS`  | `604800` (7 days)          | session lifetime                                  |
| `COOKIE_SECURE`            | `false`                    | force `Secure`; implied for HTTPS requests        |
| `COOKIE_SAMESITE`          | `lax`                      | cookie CSRF posture                               |
| `BCRYPT_ROUNDS`            | `12`                       | password hashing cost                             |
| `LOGIN_MAX_ATTEMPTS`       | `10`                       | failures per IP+email before lockout              |
| `LOGIN_WINDOW_SECONDS`     | `900`                      | limiter window                                    |
| `DATABASE_URL`             | `sqlite:///./voxtext.db`   | any SQLAlchemy URL; Postgres needs no code change |
| `WHISPER_MODEL`            | `small`                    | faster-whisper model name                         |
| `WHISPER_DEVICE`           | `cpu`                      | `cpu` or `cuda`                                   |
| `WHISPER_COMPUTE_TYPE`     | `int8`                     | quantisation                                      |
| `WHISPER_BEAM_SIZE`        | `5`                        | beam search width                                 |
| `WHISPER_WARM_ON_STARTUP`  | `true`                     | load the model in a background thread at boot     |
| `UPLOAD_DIR`               | `uploads`                  | where uploads are written                         |
| `MAX_UPLOAD_MB`            | `25`                       | hard size cap                                     |
| `ALLOWED_AUDIO_EXTENSIONS` | webm/wav/mp3/m4a/mp4/ogg/opus/flac/aac | upload allow-list                     |
| `CORS_ORIGINS`             | `[]`                       | set only if the frontend is another origin        |

While `DEBUG=true` and `SECRET_KEY` is unset, a throw-away key is generated
once into `instance/dev_secret.key` so sessions survive `--reload`. A
placeholder such as `change-me` is rejected at start-up rather than silently
trusted.

---

## How sessions work

- Sign-in issues a **signed session token** (`sub`, `jti`, `exp`) in an
  `HttpOnly`, `SameSite=Lax` cookie; `Secure` is added automatically for HTTPS
  responses. The browser cannot read it, and `GET /api/auth/me` also accepts it
  as a `Bearer` token for non-browser clients.
- Passwords are stored only as **bcrypt** digests. Signing in with an unknown
  email still runs a bcrypt verify, so response time does not reveal whether an
  account exists, and both cases return the same message.
- `POST /api/auth/logout` clears the cookie **and** adds the token's `jti` to a
  deny-list, so a captured cookie stops working immediately instead of living
  out the rest of its 7 days.
- Sign-up, sign-in and transcription require a **same-origin** request (a
  browser request carrying a foreign `Origin` is refused with 403), which
  together with `SameSite=Lax` is the CSRF defence.
- Every response carries `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` and a `Permissions-Policy` that limits the microphone to
  this origin; HSTS is added on HTTPS.
- Uploads are validated before touching disk (extension allow-list), written
  under a generated UUID name, streamed in 1 MiB chunks with a hard size cap,
  and deleted when the request finishes — including when the client disconnects
  part-way through an upload.

---

## Testing

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe selftest.py
```

- `pytest` runs the suite in `tests/` against FastAPI's `TestClient` with a
  temporary database. Transcription is exercised through a fake engine, so no
  model download is needed.
- `selftest.py` boots a **real uvicorn process** on a free port and drives the
  HTTP API against it: anonymous access, cookie flags, forged and
  tampered-signature tokens, sign-out replay, upload validation, and a check
  that the upload directory is left empty afterwards. It then shuts the server
  down. It deliberately never uploads valid audio, so it stays offline.

---

## Production notes

These are the current limits of the implementation, and the two in-memory
stores referenced from `app/security/revocation.py` and
`app/security/rate_limit.py`:

1. **Run exactly one worker process.** The sign-in limiter and the signed-out
   token deny-list are in-process dictionaries guarded by a lock. With
   `uvicorn --workers 2`, a token revoked by worker A is still accepted by
   worker B, and each worker keeps its own attempt budget — so both protections
   are weakened by the worker count. To scale out, move both to a shared store
   such as Redis (`SETEX voxtext:revoked:<jti> 1 <expiry>` for revocation, a
   fixed-window counter or sorted set per IP+email for the limiter) and keep
   the same two call sites; everything else in the app is stateless and already
   safe to replicate. Until then, keep `--workers 1` and scale with more
   instances only behind a session-sticky load balancer, accepting the gap.
2. **`init_db()` only creates missing tables.** `app/db.py` calls
   `create_all()` at start-up. That is convenient for development but cannot
   change an existing column, so adopt Alembic before the schema moves in a
   real deployment: `pip install alembic`, `alembic init migrations`, point its
   `sqlalchemy.url` at `DATABASE_URL`, set
   `target_metadata = app.db.Base.metadata` in `migrations/env.py`, then
   `alembic revision --autogenerate -m "users"` and `alembic upgrade head`.
   Afterwards, drop the `init_db()` call from the lifespan handler in `main.py`
   so schema changes only ever come from reviewed migrations.
3. **Set `SECRET_KEY` and `DEBUG=false`.** Outside DEBUG a missing key is a
   start-up error by design, and `/api/docs` plus `/api/openapi.json` are
   disabled. Set `COOKIE_SECURE=true` when TLS terminates upstream.
4. **`DATABASE_URL` is the only change needed for Postgres** — install
   `psycopg[binary]` and swap the URL. SQLite serialises writes, which is fine
   for one process and not for several.
5. **Uploads and transcripts are never persisted.** Files are deleted as soon
   as the request ends and only the text travels back to the caller. That is
   the privacy stance, but it also means there is no server-side record of past
   jobs.
6. **No TLS termination here.** Put a reverse proxy (Caddy, nginx) in front of
   uvicorn and rely on the automatic `Secure` cookie plus HSTS.
7. **The first request may be slow.** Weights load lazily into a shared model
   instance; warm it at boot with `WHISPER_WARM_ON_STARTUP=true` and gate
   traffic on `speech_model_ready` from `/api/health`.

---

## Next steps

The account layer is deliberately the only persisted state: `models.py` has a
single `User` table, so there is no per-user transcription history, usage
quota, or e-mail verification yet. The natural next slice is a
`transcriptions` table (user id, language, duration, created at, optional
text) written by `/api/transcribe` plus a history page that reads it — the same
`Depends(get_current_user)` dependency already scopes every query to the
signed-in user, and it should be applied to the new table's queries from day
one rather than bolted on later.

- `verify.ps1` repeats the smoke test against an already-running server.
