# POS printer setup — v2.5.0

## Short path: use the existing update button

1. In remote admin click **განახლება + გადატვირთვა**. The update preserves
   the existing database and settings, adds the receipt queue table, and attempts
   to install the Windows printing component. Wait for the app to return and
   verify **v2.5.0**. The no-restart button also prepares the component/schema,
   but new Python features only activate after restart.
2. At the POS: connect/power the HPRT TP80BE by USB, load 80 mm paper, and install
   its Windows driver if it is not already installed. Set the driver's receipt
   paper size to 80 mm (e.g. 200 mm long), with suitable cutter/feed settings.
3. In remote admin find **ჩეკის პრინტერი**. Click **სიის განახლება**, select
   the printer, then **საცდელი ჩეკი**. Have the on-site developer check Georgian
   letters and cutting on actual paper. The sample does not record a meal.
4. Check **ავტომატური ბეჭდვა** and click **შენახვა**. This takes effect
   immediately. No terminal commands, .env edits or second local restart.

If the component could not download during update, the panel provides
**ბეჭდვის კომპონენტის დაყენება** to retry remotely. If it reports a restart is
required, use the existing update-and-restart button once more. Internet is
needed for initial component installation; normal scanning/printing is local.
Installing the hardware driver is the only possible extra software step on
the laptop. The application cannot install an unprovided manufacturer driver.

## Data preservation

The update keeps the existing .env, card records, meal history, and database
file. It adds a new receipt_jobs table; it does not replace the database or
re-import cards. Remote printer settings are stored separately in
.receipt-config.json and survive updates. They override the optional legacy
RECEIPT_PRINTING / RECEIPT_PRINTER environment settings.

## On-site acceptance

Use a designated test card: real test taps record actual usage.

- First tap today: one receipt with known full name (roster preferred), or
  manual name / არაიდენტიფიცირებული, date, time, daily sequence and per-card count.
- Wait at least 1.2 seconds, tap again: **დღეს ბარათი მეორედ არის გამოყენებული**.
  Third and later taps show their actual count. Existing taps today count too.
- Denied taps print **უარყოფილია — კვება არ გაიცა** plus the reason. Counts
  include denied attempts; a reader bounce suppressed by the kiosk does not count.
- Check the laptop clock. Receipt/tap timestamps use TIMEZONE (normally
  Asia/Tbilisi). The report-only 14-minute clock correction is not applied to
  receipts. Correct any clock discrepancy before relying on printed times.
- Disconnect USB briefly during a designated test: scans must continue.
  Reconnect and inspect the Windows queue; it may hold the submitted job.
  Do not tap again just to retry a print.
- After app restart, counts continue; already submitted receipts are not replayed.

## Diagnosis / disabling

Refresh the printer panel for queue counts. Pending jobs survive restart.
Submitted means Windows accepted a job, not confirmed paper output. Check the
Windows spooler, USB/paper and driver when paper does not appear. Failed or
interrupted (sending) jobs are not automatically retried, because they may
already have printed. Review Windows queue and paper before deliberate recovery.
Detailed errors are in app.log.

Uncheck automatic printing and save remotely to disable it immediately.
Already submitted Windows jobs are managed in Windows; pending application
jobs remain saved if printing is re-enabled later.

## ZIP / command-line fallback (normally unnecessary)

The ZIP can be applied to an existing installation if GitHub is unavailable.
Extract into a separate staging directory. Stop the existing app, then use its
Python to run the staging scripts/install_local_release.py with the ZIP path
and --target pointing to the existing POS project folder. The installer keeps
.env/database/backups/.venv and snapshots old code in .rollback. Never start
another app from the staging folder. Then run scripts/migrate_db.py from the
existing installation and start with quick-start.bat /noupdate.

The scripts.receipt_printer module still supports --list, --check, --test and
--status for a developer working locally. The remote panel replaces these
manual setup commands for normal use.

## Validation limits

Automated tests use isolated synthetic databases, including concurrent scans,
queue recovery, update/migration preservation and authenticated remote setup.
Windows GDI calls are tested with a recording API double on macOS. Actual
Windows execution, the TP80BE driver, USB, Georgian glyphs and cutter/feed
require the paper acceptance test above.
