# LUNCH — cafeteria meal-access system

A single-PC cafeteria access system for ~250 people. Each person has a unique
ID card. They tap the card on a USB reader at one kiosk station to claim their
daily meal. **Each person may eat up to a per-card daily limit (default 2 meals
per calendar day); you can change the limit per card or in bulk from admin.**
You (the operator)
manage cards and view reports **remotely over the internet**; the company that
runs the kiosk only ever sees the scan screen.

All user-facing text — the kiosk, admin, reports, errors, and every exported
Excel/CSV file — is in **Georgian (ქართული)**. Internal scan statuses stay in
English (`ALLOWED` / `DENIED`) so the code and tests are reliable.

---

## How it is split (important)

| Audience | Sees | Reachable from |
|---|---|---|
| **The company's kiosk PC** | The scan screen only (`/`) | The kiosk PC itself, fully **offline** |
| **You (operator)** | Admin (`/admin`) + Reports (`/reports`) | **Only remotely** via the ngrok tunnel |

* The app binds to **`127.0.0.1`**, so the cafeteria LAN cannot reach it at all.
* **Scanning works 100% offline.** The SQLite database on the kiosk PC is the
  single source of truth — no internet, no sync.
* Admin / Reports / Login (and their APIs) are **blocked for any local request**
  and allowed **only through the tunnel**, proven by a shared secret header.
  Even the kiosk PC's own browser cannot open `/admin`.

```
  Your laptop/phone  --HTTPS-->  ngrok  -->  ngrok.exe (on kiosk PC)
        -->  local header-injecting proxy (adds X-Tunnel-Secret)  -->  app
  Kiosk PC browser  -->  app  (no secret -> /admin etc. blocked; / works)
```

---

## Requirements

* A Windows PC for the kiosk (Python 3.11+; the launcher finds `py` or `python`).
* A USB card reader in **keyboard mode** (tapping "types" the card ID and
  presses Enter). Any such reader works — no driver, no vendor SDK.
* No reader during development? You can **type a card ID + Enter** anywhere the
  reader would be used — the whole flow is testable by typing.

---

## Install & run (one click)

1. Copy this folder to the kiosk PC.
2. Copy `.env.example` to `.env` and set a **strong `ADMIN_PASSWORD`**
   (the app refuses to start with a blank password or `changeme`).
   `SECRET_KEY` and `TUNNEL_SECRET` are filled in automatically on first run.
3. For stable remote access, create a free ngrok account and put your
   `NGROK_AUTHTOKEN` and assigned `NGROK_DOMAIN` in `.env`.
4. **Double-click `start.bat`.**

On the **first run** (needs internet once) `start.bat` will:

* create a Python virtual environment in `.venv` and install dependencies,
* generate `SECRET_KEY` and `TUNNEL_SECRET` in `.env` if they are blank,
* run startup checks (refuses a weak password / missing `SECRET_KEY`),
* create the database with the admin account if `lunch.db` is missing
  (no demo cards by default — set `SEED_SAMPLE_CARDS=true` in `.env` for a demo),
* download `ngrok.exe`,
* start the app + the local proxy + the ngrok tunnel hidden in the background,
* automatically open the kiosk scan screen,
* **print the stable remote-admin URL** and also save it to `tunnel-url.txt`.

After first setup, **scanning runs offline forever**. The tunnel only matters
when you want remote admin.

**After the first setup, use `quick-start.bat` for a fast launch** — it skips
the dependency install / config / seed steps and just (re)starts the app, proxy,
and tunnel. Run the full `start.bat` only after an update or if something is
broken. To reopen just the scan screen, double-click `kiosk.bat`. To stop the
background app/proxy/tunnel processes, double-click `stop.bat`.

> You don't have to run `stop.bat`. Closing the start window or shutting down
> leaves the background processes running until the next reboot or the next
> `start.bat`/`quick-start.bat` (which clean up old processes automatically).
> `stop.bat` is only for stopping them without rebooting.

> If Python is missing, the launcher tells you to install Python 3.11+ and to
> check **"Add Python to PATH"** during installation.

---

## Open the kiosk full-screen

On the kiosk PC, open a browser at:

```
http://127.0.0.1:8000/
```

`start.bat` opens this page automatically. If the browser was closed, run
`kiosk.bat` or open the URL above manually. Press **F11** for full-screen. The
screen shows **„დაადეთ ბარათი"** and an
invisible, always-focused field captures the card tap. Results:

* **Allowed** → full green, huge **„ნებადართულია"**, with the time below.
* **Denied** → full red, huge **„უარყოფილია"**, with a Georgian reason:
  * **„უცნობი ბარათი"** — unknown card
  * **„ბარათი გათიშულია"** — card is inactive
  * **„დღეს უკვე ნაჭამია"** — already eaten today

The screen auto-returns to neutral after ~2.5s and debounces double taps. A
small 🔔 button (bottom-right) toggles an optional beep. No names or photos are
shown, by design.

### Test without a card reader

For local testing on the kiosk PC, open:

```
http://127.0.0.1:8000/kiosk-test
```

or double-click `kiosk-test.bat`. This opens a local-only test harness with
buttons for demo card IDs (`1001`, `1002`, `1003`, `0573856032`, inactive
`9999`, and an unknown card). It drives the real kiosk page by filling the
hidden capture input and pressing Enter, the same way a keyboard-mode USB
reader does. This page is blocked through the remote ngrok tunnel.

---

## Remote admin (ngrok stable domain)

`start.bat` prints a line like:

```
  REMOTE ADMIN URL:  https://your-assigned-domain.ngrok-free.app
```

(also saved in `tunnel-url.txt`). Open it from **your own** laptop or phone:

* `https://your-assigned-domain.ngrok-free.app/admin` — manage cards
* `https://your-assigned-domain.ngrok-free.app/reports` — view who ate / export files

Log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`.

**Why it is airtight:** ngrok forwards to a tiny local proxy that injects the
secret `X-Tunnel-Secret` header. The app only unlocks `/admin`, `/reports`,
`/login` and their APIs when that exact secret is present. Local requests
(no secret) get a `403`. The scan page and `/api/scan` are always served
locally so the kiosk works offline.

### Get your free stable ngrok URL

1. Create/log in to a free ngrok account.
2. Copy your authtoken from the ngrok dashboard.
3. Find your assigned free dev domain under **Universal Gateway → Domains**.
   It looks like `abc123.ngrok-free.app` or `abc123.ngrok-free.dev`.
4. Put both values in `.env`:

```
NGROK_AUTHTOKEN=your_ngrok_token_here
NGROK_DOMAIN=abc123.ngrok-free.app
```

Do not include `https://` in `NGROK_DOMAIN`. If you paste it accidentally,
`start.bat` strips it before launching ngrok.

---

## Managing cards

On `/admin`:

* **Search** cards by card ID; the list shows card ID, active, and ate-today.
* **Add a card** by typing an ID, or click **„ბარათის წაკითხვა"** and tap a
  card to fill it in. New cards get the name placeholder `----`.
* **Edit / reassign / deactivate / delete** a card. Deactivating keeps history;
  deleting removes the card and its scans.
* Assigning a card ID that already exists shows a Georgian error
  (**„ეს ბარათი უკვე მინიჭებულია."**).

### Bulk import ~250 cards (.xlsx — primary)

Prepare an Excel file with **one card ID per line in the first column** (an
optional `card_id` header is fine; a `.csv` works too). On `/admin` →
**„ჯგუფური იმპორტი"** choose the file and upload. Each row becomes an **active**
card with name `----`. The result reports how many were added, plus any
duplicates / failures **by row number**.

> **Leading zeros are preserved** end-to-end (e.g. `0573856032` stays
> `0573856032`). Make sure the file stores card IDs as **text** so Excel does
> not turn them into numbers (format the column as Text, or prefix with `'`).

### Demo seed cards

For an immediate demo, run:

```
python -m scripts.seed
```

The seed is idempotent and creates the configured admin plus a few sample cards,
including a leading-zero card (`0573856032`) and one inactive card. Sample names
are left as `----`.

---

## Reports & exports

On `/reports`:

* **Today**: number who ate, total active cards, remaining.
* **Date range** → daily counts table; quick buttons for **Today / This week /
  This month**, plus a custom range.
* **A selected day** → who ate, listed by **card ID + time**.
* **Downloads** (all Georgian content, identified by card ID):
  * **Attendance .xlsx / .csv** — single day = each active card marked
    **„ჭამა" / „არ უჭამია"** + a summary; multi-day = days-attended out of
    days-in-range + status.
  * **Detail .xlsx / .csv** — every scan row (date, card ID, time) for the range.

---

## Configuration (`.env`)

| Key | Meaning | Default |
|---|---|---|
| `TIMEZONE` | IANA zone deciding the "calendar day" | `Asia/Tbilisi` |
| `ADMIN_USERNAME` | first admin login | `admin` |
| `ADMIN_PASSWORD` | first admin password (must be strong) | *(none — set it)* |
| `SECRET_KEY` | signs the session cookie (auto-generated) | *(auto)* |
| `TUNNEL_SECRET` | shared secret for the remote gate (auto-generated) | *(auto)* |
| `NGROK_AUTHTOKEN` | ngrok account token for stable tunnel | *(set it)* |
| `NGROK_DOMAIN` | assigned free ngrok dev domain, no `https://` | *(set it)* |
| `HOST` | bind address — keep `127.0.0.1` | `127.0.0.1` |
| `PORT` | app port (proxy uses `PORT+1`) | `8000` |
| `DB_PATH` | SQLite file | `lunch.db` |

Never commit `.env`, the database, or real card files — they are gitignored.

### Change the timezone

Edit `TIMEZONE` in `.env` (any IANA name, e.g. `Europe/Berlin`) and restart.
`tzdata` is bundled, so this works on Windows (which ships no system tz data).

### Set a strong password / SECRET_KEY

Put a strong `ADMIN_PASSWORD` in `.env`. To set `SECRET_KEY` yourself:

```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`SECRET_KEY` must stay the same across restarts (otherwise sessions are
invalidated and could otherwise be forged).

---

## Back up the database

Everything is in the single file **`lunch.db`** (plus `lunch.db-wal` /
`lunch.db-shm` while running). To back up: stop the app, then copy `lunch.db`
somewhere safe. To restore: put the file back and start again.

---

## Security notes

* App binds to `127.0.0.1` — **not reachable from the LAN**.
* Admin / Reports / Login require the tunnel secret; local requests are `403`.
* Passwords are hashed with **bcrypt**; sessions are **signed** cookies
  (httponly, and `Secure` over the tunnel's HTTPS).
* **Login rate-limiting:** 5 failed attempts → a 5-minute cooldown.
* The app **refuses to start** with a blank/weak password or a too-short
  `SECRET_KEY`.

---

## Updating

After pulling updates, **hard-refresh the browser (Ctrl+F5)** — static files
(HTML/CSS/JS) are cached by the browser.

---

## Development / tests

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
# create a .env with a strong ADMIN_PASSWORD + a SECRET_KEY (see above)
python -m scripts.seed                         # seed admin + sample cards
python run.py                                  # run the app
python -m pytest -q                            # acceptance tests (section 16)
```

The acceptance suite types card IDs (there is no physical reader in tests) and
covers: allow/deny, once-per-day + midnight reset, **concurrent taps → exactly
one ALLOWED**, leading zeros, CRUD + unique enforcement, importing 250 cards,
Georgian exports, the remote-only gate, rate-limiting, and weak-password refusal.

### Project layout

```
app/            FastAPI app (config, models, db, security, scan logic, routers)
static/         kiosk / admin / reports / login pages (no build step)
scripts/        seed + start.bat helpers
tests/          acceptance tests
run.py          entry point (validates config, then launches uvicorn)
tunnel_proxy.py local header-injecting proxy (ngrok -> proxy -> app)
start.bat       one-click Windows setup + run + tunnel (first run / after updates)
quick-start.bat fast relaunch after setup (skips install/config, just launches)
kiosk.bat       reopens the local kiosk scan screen
kiosk-test.bat  opens the local card-reader simulator
diagnose.bat    writes diagnose.txt when startup fails
stop.bat        stops background processes started by start.bat
```
