# My Causelist Watcher

Automatically checks the J&K High Court, Srinagar Wing causelist page
(https://jkhighcourt.nic.in/causelistk.php), downloads the day-wise /
entire / supplementary / registrar PDFs, searches them for your name, and
keeps a running local file (`cases_auto.json`) plus a viewable dashboard
(`causelist_dashboard.html`) with a calendar of your listing dates.

This runs on **your own computer or a free GitHub Actions schedule** — not
inside Claude — because Claude itself currently cannot fetch PDFs from this
particular site (tested directly; the site's HTML pages load fine but PDF
requests get blocked, most likely by bot-protection on their server). A
plain script using your normal internet connection doesn't hit that wall.

## 1. One-time setup

You need Python 3.9+ installed.

```bash
pip install -r requirements.txt
cp config.example.json config.json
```

Edit `config.json` with the name(s) to track, in one of two formats:

**Tracking one person** (with optional alternate spellings as `aliases`):
```json
{
  "name": "Mohd Ashraf Wani",
  "aliases": ["Ashraf Wani", "M.A. Wani"],
  "list_types": ["daywise", "supplementary", "entire", "registrar"]
}
```

**Tracking two or more advocates** — use `people` instead of `name`/`aliases`.
Each match gets tagged with which advocate it belongs to, so the dashboard
can show/filter cases per person instead of lumping everyone together
(this is the format `config.example.json` ships with):
```json
{
  "people": [
    { "name": "Bilal Nazir", "aliases": ["Adv. Bilal Nazir", "B. Nazir"] },
    { "name": "Tanveer Ahmad", "aliases": [] },
    { "name": "Sameer Kaul", "aliases": ["S. Kaul"] }
  ],
  "list_types": ["daywise", "supplementary", "entire", "registrar"]
}
```
Add as many entries to `people` as you need — three, five, however many.
Every docket card in the dashboard shows an "Advocate" field, and the
"All cases" tab gets a filter bar to view one person's cases at a time
once there's more than one person being tracked.

`list_types` controls which PDFs get checked each run — drop any you don't
need (e.g. `"list_types": ["daywise"]` to skip the entire/registrar lists
and go faster). It works the same in both formats above.

## 2. Run it

```bash
python causelist_watcher.py
```

First run creates `cases_auto.json` (your saved matches) and
`causelist_dashboard.html` — open this in any browser (double-click it,
no internet needed to view it). The dashboard has:

- A **sticky "Today's Board"** panel (top-right on a desktop screen, a
  banner at the top on tablet/phone widths) listing today's hearings by
  Sr. No. and Court No. It's ordered by serial number within each court —
  that's usually also the hearing order, but there's no live "now calling"
  feed publicly available for this court, so treat it as a schedule, not
  a real-time queue.
- **Stat cards** — today's count, next 7 days, next hearing date, total tracked.
- A **calendar** — click any highlighted date to see that day's cases.
- An **Upcoming agenda** panel that groups your next hearings by date.
- A **sortable, searchable table** of every case ever found — click any
  column header to sort by it (Date, Court No, Sr No, Case No, Case Name,
  Advocate, Bench).
- If `config.json` tracks more than one advocate, a **filter bar** lets
  you view one advocate's cases at a time everywhere on the page.

Run again any time; it only re-parses PDFs that actually changed since last
time, and never duplicates entries.

Use `python causelist_watcher.py --dry-run` to test without saving anything.

**If a run fails** with "Could not reach the causelist page" — the site may
be down, or (less likely for a real browser-like request, but possible) it's
blocking the request. The script logs this in `watcher.log` and exits
cleanly rather than crashing; just try again later, or fall back to
downloading that day's PDF by hand and using the "My Causelist Docket"
upload app instead.

## 3. Make it run automatically

Pick whichever fits you — both are genuinely automatic, the difference is
where it runs.

### Option A — Your own computer (simplest)

**Windows (Task Scheduler):**
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily (or a few times a day, on court days)
3. Action: Start a program
   - Program: `python.exe` (or `py.exe`) — full path if needed, e.g. `C:\Python311\python.exe`
   - Arguments: `causelist_watcher.py`
   - Start in: the folder where you put these files
4. Finish. Check `watcher.log` after it runs once to confirm it worked.

**macOS/Linux (cron):**
```bash
crontab -e
```
Add a line to run it, e.g. twice a day on weekdays:
```
0 9,15 * * 1-5 cd /path/to/this/folder && /usr/bin/python3 causelist_watcher.py >> cron.log 2>&1
```

Your computer needs to be on and online at that time for it to run.

### Option B — Free cloud automation (GitHub Actions), so it runs even if your PC is off

1. Create a free GitHub account if you don't have one, and a new **private**
   repository.
2. Push these files to it (including the `.github/workflows/watch.yml`
   file that's already included here) — **do not commit `config.json` to a
   public repo**; if you want the repo public, add `config.json` to a
   `.gitignore` and instead set your name/aliases as GitHub Actions
   "Repository secrets" and adjust the script to read from environment
   variables. For a private repo this isn't a concern.
3. The included workflow (`.github/workflows/watch.yml`) runs the script
   twice a day and commits the updated `causelist_dashboard.html` back to
   the repo automatically. Edit the `cron:` lines if you want a different
   schedule.
4. To actually *view* the dashboard from your phone or computer: enable
   **GitHub Pages** for the repo (Settings → Pages → deploy from the branch,
   `/` root), then bookmark
   `https://<your-username>.github.io/<repo-name>/causelist_dashboard.html`.
   It'll reflect whatever the last automated run found.

## 4. Viewing it on iPad

The dashboard itself is fully responsive — open it in Safari on an iPad and
the sticky corner widget automatically becomes a full-width banner at the
top instead of a floating box, and the layout stacks into a single column.

The catch: an iPad can't run the Python script (it needs a real computer,
or GitHub Actions, to fetch and parse the PDFs). So to view it on iPad:

- **Best option** — set up GitHub Actions + Pages (Option B above). You get
  a normal `https://` URL that stays up to date on its own; just open it in
  Safari and optionally "Add to Home Screen" so it behaves like an app icon.
- **Manual option** — after running the script on your computer, AirDrop or
  email yourself the `causelist_dashboard.html` file and open it in Safari.
  This snapshot won't update on its own; you'd redo this each time you want
  fresh data.

## Notes on accuracy

Court No. / Sr. No. / Case No. are extracted heuristically from the text
layout of each PDF — this generally works well but formatting varies. Treat
`cases_auto.json` as a strong first draft; the dashboard shows you the raw
matched text snippet for each entry so you can sanity-check it against the
actual PDF if something looks off.

## Files

- `causelist_watcher.py` — the script you run
- `causelist_core.py` — parsing/URL logic (shared style with the browser-upload version)
- `dashboard_template.py` — generates `causelist_dashboard.html`
- `config.json` — your name/settings (create this from `config.example.json`)
- `cases_auto.json` — accumulated saved matches (created after first run)
- `manifest.json` — tracks which PDFs were already processed (created after first run)
- `causelist_dashboard.html` — the viewable result (created/updated after each run)
- `watcher.log` — run history / errors
