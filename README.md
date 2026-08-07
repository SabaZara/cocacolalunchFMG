# LUNCH — cafeteria meal-access system

A single-PC cafeteria access system for ~250 people. Each person has a unique
ID card. They tap the card on a USB reader at one kiosk station to claim their
daily meal.

**There is no pre-approved list of cards.** A card the system has never seen is
registered automatically on its first tap, and that tap counts as a meal — so
nobody is turned away at the kiosk and the card list builds itself from real
usage. Names are optional and can be filled in later.

**Every card has the same daily limit** — one number (default **1 meal per
calendar day**) that you change once, from the admin page, for everybody. There
are no per-card limits.

The one way to block somebody is to **deactivate** their card in admin (lost or
stolen card, person left): a deactivated card is denied on tap and is *not*
silently re-registered.

You (the operator) manage cards and view reports **remotely over the internet**;
the company that runs the kiosk only ever sees the scan screen.

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

* **Allowed** → full green, huge **„ნებადართულია"**, with the time and either
  **„დარჩა: N"** or **„მეტი აღარ გაქვთ"** when that was the last meal. A card
  registering itself on this tap is deliberately *not* announced — to the
  person at the reader it is just a normal allowed scan.
* **Denied** → full red, huge **„უარყოფილია"**, with a Georgian reason:
  * **„დღის ლიმიტი ამოიწურა"** — the daily limit is used up
  * **„ბარათი გათიშულია"** — card was deactivated by an admin
  * **„უცნობი ბარათი"** — nothing was read from the card (empty tap). An
    genuinely *unknown* card is no longer denied: it registers itself.

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

Cards normally appear here **on their own** — the kiosk registers each card the
first time it taps, so you do not have to load anything up front.

On `/admin`:

* **Daily limit** — one field at the top of the card list. It applies to
  **every card**; save it and the next tap already uses the new number.
* **Search** cards by card ID; the list shows card ID, active, today's meals
  out of the limit, and the limit itself.
* **Add a card** manually by typing an ID, or click **„ბარათის წაკითხვა"** and
  tap a card to fill it in. New cards get the name placeholder `----`. This is
  optional — it only pre-loads a card that has not tapped yet.
* **Edit / reassign / deactivate / delete** a card. **Deactivating is how you
  block somebody**: the card is denied at the kiosk and will not be
  re-registered by a tap. Deactivating keeps history; deleting removes the card
  and its scans (and a later tap would register it again as a fresh card).
* Assigning a card ID that already exists shows a Georgian error
  (**„ეს ბარათი უკვე მინიჭებულია."**).

### Bulk import ~250 cards (.xlsx — primary) — optional

Importing is no longer required, since unknown cards register themselves. It is
still useful to pre-load a known list (so cards show up in reports before their
first tap).

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

## Start automatically when the laptop turns on

Run **`install-autostart.bat` once** (right-click → *Run as administrator* if it
complains). It registers two Windows Scheduled Tasks:

| Task | When | What it does |
|---|---|---|
| `LunchKioskStartup` | every logon | starts app + proxy + tunnel and opens the kiosk screen |
| `LunchKioskWatchdog` | every 5 min | checks `/healthz`; relaunches the app if it is not answering |

After that: **turn the laptop on and it is ready to scan.** Nothing to click.

**Shutting down stays entirely manual** — neither task ever stops or closes
anything. Shut the laptop down whenever your day ends, exactly as before.

The watchdog is the safety net for the failure that used to require a physical
visit: if a remote update (or a crash, or a bad shutdown) leaves the app dead,
nothing inside the app can revive it — the app *is* what died. The watchdog runs
outside it and brings it back within ~5 minutes. It writes `watchdog.log`.

To undo all of this, run **`uninstall-autostart.bat`**. Your data and settings
are untouched; you just go back to starting the kiosk by hand.

---

## Back up the database

Everything is in the single file **`lunch.db`** (plus `lunch.db-wal` /
`lunch.db-shm` while running). To back up manually: stop the app, then copy
`lunch.db` somewhere safe. To restore: put the file back and start again.

### Automatic backups to a private GitHub repo

The app can upload a snapshot of the database to a **private** GitHub repo, so a
dead laptop does not mean lost data. Set it up once, from the admin page:

1. On GitHub, create a **new private repository**, e.g. `cocacolalunch-backups`.
   *It must be private* — it will hold real scan data.
2. Create a token: **Settings → Developer settings → Personal access tokens →
   Tokens (classic) → Generate new token**, tick the **`repo`** scope, and copy
   the token (you only see it once).
3. On `/admin`, find the backup box: paste `owner/repo` (e.g.
   `SabaZara/cocacolalunch-backups`) and the token, then save.

From then on it uploads by itself (weekly, plus on startup when due) and keeps
the newest few snapshots so the repo never grows large. The token is stored on
the kiosk in `.backup-config.json` (gitignored, preserved across updates) and is
**never** shown back in the UI or committed to the public code repo.

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

Two buttons on `/admin`, under **სისტემა**:

**„განახლება რესტარტის გარეშე" (safe — use this by default).** Downloads the new
code and leaves the app running. Scanning is never interrupted. Python only
loads new code when the process restarts, so the new version goes live at the
**next logon** — i.e. the next morning you turn the laptop on.

**„განახლება + გადატვირთვა".** Applies immediately, but the app is down for
~10 seconds while it restarts. Use it when you need a fix live right now.

> The restart path is what can strand the kiosk: the app kills itself and, if
> the relaunch fails, nothing inside the app is left to fix it — you get a
> `502 upstream error` on the tunnel and someone has to walk to the PC. Once
> `install-autostart.bat` is set up, the watchdog covers this within ~5 minutes.

Either way, local data (`.env`, `lunch.db`, `.app-config.json`,
`.backup-config.json`, `backups/`) is preserved, and the previous code is
snapshotted to `.rollback/` first.

After a code update, **hard-refresh the browser (Ctrl+F5)** — static files
(HTML/CSS/JS) are cached by the browser. The kiosk screen reloads itself.

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
