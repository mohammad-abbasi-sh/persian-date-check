---
name: persian-date-check
description: Audit Persian text for wrong Shamsi (Jalali) dates — impossible dates (31 Aban, 30 Esfand in a non-leap year), wrong weekdays ("Friday 21 Aban 1405" — it is Thursday), mismatched Jalali/Gregorian pairs stated together, relative dates ("tomorrow") that disagree with an absolute date in the same sentence, mixed digit scripts, Arabic-Indic digits, implausible years, and month-name misspellings. Use when an agent writes or edits Persian content with dates (articles, social posts, deadlines, exam material), when a Persian deadline or event date looks wrong, when a text states both a Jalali and a Gregorian date, or before publishing any Persian text that names a day. Also use to verify a fix before reporting the date as fixed.
---

# Persian date check — the audit layer your Jalali converter is missing

Agents writing Persian content state Shamsi dates constantly — and
get them wrong constantly. The classic failure is the weekday: an
agent writes «جمعه ۲۱ آبان ۱۴۰۵» and 21 Aban 1405 is a Thursday.
Nobody notices, because the sentence reads fine and no build fails.
The same happens with impossible dates («۳۱ آبان»، «۳۰ اسفند» in a
non-leap year) and with Jalali/Gregorian pairs where one side was
copied wrong («۲۰ آبان ۱۴۰۵ برابر با ۱۲ نوامبر ۲۰۲۶» — it is
11 November, not 12).

Converters do not catch any of this. parsi-mcp (56 tools), the
persian-text-skill, jalali-moment and PersianDate will all happily
convert whatever date you hand them — they never read your paragraph
and ask whether the date in it is true. This skill is that audit
layer. It complements converters; it does not replace them.

## The contract

1. **Check first, with the tool — never guess.** Run the bundled
   checker (zero-dependency, Python stdlib only):

   ```bash
   python3 scripts/persian_date_check.py check article.md
   ```

   Exit codes: `0` = no errors · `1` = errors found ·
   `2` = usage error or an unreadable file. Warnings do not fail
   the check unless `--strict` is passed.

   Useful flags: `--today YYYY-MM-DD` (reference date for relative
   dates like «فردا»/«۳ روز پیش» — default: today),
   `--json` (machine-readable output for CI),
   `--fix` (write `<file>.fixed` with mechanical fixes).

   Convert a single date without auditing text:

   ```bash
   python3 scripts/persian_date_check.py convert to-jalali 2026-11-11
   python3 scripts/persian_date_check.py convert to-gregorian 1405-08-20
   python3 scripts/persian_date_check.py convert today
   ```

2. **Fix mechanically, then review.** `--fix` writes
   `<file>.fixed` next to the input — it never overwrites the
   input — applying only the safely mechanical fixes: wrong
   weekdays (PDC-02) and month-name misspellings (PDC-08). It
   then re-checks and reports what still needs a human. PDC-01
   (impossible date), PDC-03 (mismatched pair) and PDC-04
   (relative mismatch) are never auto-fixed: an impossible date
   is a judgement call about which number was mistyped, not a
   string replace.

   ```bash
   python3 scripts/persian_date_check.py check article.md --fix
   # review the .fixed diff, then re-check it until exit 0
   python3 scripts/persian_date_check.py check article.md.fixed
   ```

3. **Prove the fix.** Do not report a date as fixed after editing
   text — re-run the check on the fixed file until it exits 0.
   Quote the final `0 error(s)` line in your report.

4. **Know the limits — and say them.** This skill audits *dates
   stated in text*. It does not convert dates for display (route
   that to a converter), it does not know holidays (Iranian
   holidays are a separate dataset — see `references/date-rules.md`),
   it does not parse dates written out as words («بیست و یکم آبان»),
   and relative dates («۳ روز پیش») are only checked when an
   absolute date appears in the same sentence. Say so in every
   report (see `references/date-rules.md`).

## What each check means

- **PDC-01 impossible date** — a day that does not exist: 31 Aban
  (Aban has 30 days), 30 Esfand in a non-leap year (Esfand has 30
  days only in leap years — 1403 was, 1404 is not), 31 November,
  30 February. The detail names the real month length.
- **PDC-02 weekday mismatch** — the stated weekday disagrees with
  the calendar. The most common agent date error. The fix is the
  correct weekday, computed — never guessed.
- **PDC-03 Gregorian-pair mismatch** — a Jalali date and a Gregorian
  date stated together (in parentheses, or after «برابر با» / «=»)
  that do not convert to each other. One of the two was copied
  wrong; the detail gives the correct Gregorian equivalent.
- **PDC-04 relative-date mismatch** — a relative phrase («فردا»،
  «۳ روز پیش») and an absolute date in the same sentence that
  disagree, resolved against `--today` (default: today).
- **PDC-05 digit-script mixing** — two digit scripts inside one
  date («۲1 آبان ۱۴۰۵»). Pick one script — Persian digits (۰-۹)
  for Persian prose.
- **PDC-06 Arabic-Indic digits** — ٠-٩ in Persian text. They look
  like Persian digits but are different codepoints and break
  search. Use ۰-۹.
- **PDC-07 implausible year** — a Jalali year outside 1300–1500
  (usually a typo: an extra digit, or a Gregorian year written as
  Jalali).
- **PDC-08 month misspelling** — a token sitting where a month
  name belongs (between a day number and a year) that is one edit
  away from a real month («ابان» for «آبان»).

## Calendar facts the tool enforces

- Months 1–6 (Farvardin–Shahrivar) have 31 days; 7–11 (Mehr–
  Bahman) have 30; Esfand has 29, or 30 in a leap year.
- The week starts Saturday (شنبه). 20 Aban 1405 = Wednesday
  11 November 2026; 21 Aban 1405 = Thursday 12 November 2026.
- The converter is verified against jdatetime on every day from
  1 Farvardin 1300 to 29 Esfand 1500 (73,414 days, 0 mismatches)
  and every Gregorian day 1921-03-21–2121-03-21 (73,050 days,
  0 mismatches). See `tests/test_persian_date_check.py`.
- Dari month names (حمل، ثور، …، حوت) and Latin transliterations
  («21 Aban 1405», «Friday 21 Aban 1405») are recognised too.

## MCP server

`mcp-server/persian_date_check_mcp_server.py` exposes the same
capability over stdio JSON-RPC: `check_persian_dates` (text or
files), `convert_date` (to-jalali / to-gregorian), `today`.
See `tests/test_mcp_server.py` for a full lifecycle test.
