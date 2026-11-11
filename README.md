# persian-date-check

**Audit Persian text for wrong Shamsi (Jalali) dates — the layer your Jalali converter is missing.**

Agents writing Persian content state Shamsi dates constantly — and get them wrong constantly. The classic failure is the weekday: an agent writes «جمعه ۲۱ آبان ۱۴۰۵» and 21 Aban 1405 is a Thursday. Nobody notices, because the sentence reads fine and no build fails. The same happens with impossible dates («۳۱ آبان»، «۳۰ اسفند» in a non-leap year) and with Jalali/Gregorian pairs where one side was copied wrong («۲۰ آبان ۱۴۰۵ برابر با ۱۲ نوامبر ۲۰۲۶» — it is 11 November, not 12).

Converters do not catch any of this. [parsi-mcp](https://glama.ai/mcp/servers/amirjld/parsi-mcp) (56 tools), the [persian-text-skill](https://github.com/hanyehkhl/persian-text-skill), [jalali-moment](https://github.com/fingerpich/jalali-moment) (★442) and [PersianDate](https://github.com/babakhani/PersianDate) (★608) will all happily convert whatever date you hand them — they never read your paragraph and ask whether the date *in it* is true. This skill is that audit layer. It complements converters; it does not replace them.

## What it checks

| Code | Check | Example |
|------|-------|---------|
| PDC-01 | Impossible date | 31 Aban (30 days); 30 Esfand 1404 (not a leap year) |
| PDC-02 | Wrong weekday | «جمعه ۲۱ آبان ۱۴۰۵» — 21 Aban is Thursday |
| PDC-03 | Mismatched Jalali/Gregorian pair | 20 Aban 1405 ≠ 12 Nov 2026 (it is 11 Nov) |
| PDC-04 | Relative date vs absolute date | «فردا ۲۲ آبان» on 20 Aban (tomorrow is 21 Aban) |
| PDC-05 | Mixed digit scripts in one date | «۲1 آبان ۱۴۰۵» |
| PDC-06 | Arabic-Indic digits (٠-٩) in Persian text | «٢١ آبان ١٤٠٥» |
| PDC-07 | Implausible year | Jalali year outside 1300–1500 |
| PDC-08 | Month-name misspelling | «ابان» for «آبان» |

## Before / after

```text
$ python3 scripts/persian_date_check.py check article.md

[ERROR] PDC-02 line 1: Wrong weekday: "جمعه ۲۱ آبان ۱۴۰۵" says جمعه, but that date is پنجشنبه
[ERROR] PDC-01 line 3: Impossible date: "۳۱ آبان ۱۴۰۵" — day 31 does not exist
      آبان ۱۴۰۵ has 30 days
[ERROR] PDC-03 line 4: Mismatched pair: "۲۰ آبان ۱۴۰۵" is 2026-11-11, not "۱۲ نوامبر ۲۰۲۶"
      The Jalali date converts to 2026-11-11 (۱۱ نوامبر ۲۰۲۶).
3 error(s), 0 warning(s).
```

Fix mechanically, then prove it:

```bash
python3 scripts/persian_date_check.py check article.md --fix   # writes article.md.fixed
python3 scripts/persian_date_check.py check article.md.fixed   # until exit 0
```

## Install

**Claude Code / Claude.ai** — copy the skill directory, or upload the
`dist/persian-date-check-skill.zip`:

```bash
cp -r skills/persian-date-check ~/.claude/skills/
```

**Cursor** — copy `cursor/persian-date-check.mdc` into your project's
`.cursor/rules/` (see `cursor/README.md` for Windsurf, Cline and
Continue).

**MCP (any client)** — the stdio server in `mcp-server/` exposes
`check_persian_dates` (text or files), `convert_date`
(to-jalali / to-gregorian) and `today`:

```json
{
  "mcpServers": {
    "persian-date-check": {
      "command": "python3",
      "args": ["mcp-server/persian_date_check_mcp_server.py"]
    }
  }
}
```

**Direct use** — no install, no dependencies (Python 3.9+ stdlib only):

```bash
python3 skills/persian-date-check/scripts/persian_date_check.py check article.md
python3 skills/persian-date-check/scripts/persian_date_check.py convert to-jalali 2026-11-11
python3 skills/persian-date-check/scripts/persian_date_check.py convert today
```

## Verification (no statistical claims without a run)

- **71 tests pass** (`pytest tests/`): conversion anchors verified
  against jdatetime, round-trips over every day in the supported
  range, every check code, fixture end-to-end, `--fix` round-trip,
  CLI exit codes, JSON output, and MCP stdio end-to-end.
- **Conversion verified against jdatetime on 73,414 Jalali days**
  (1 Farvardin 1300 – 29 Esfand 1500) with **0 mismatches**, and
  73,050 Gregorian days (1921-03-21 – 2121-03-21) with **0
  mismatches**. Leap years identical over 1300–1500.
- The converter is a from-scratch stdlib implementation of the
  Borkowski breaks method — no date library is used at runtime.

## What it does not do

- It does not convert dates for display (use a converter for that).
- It does not know holidays — Iranian holidays are a separate dataset.
- It does not parse word-form dates («بیست و یکم آبان»).
- Relative dates are only checked when an absolute date appears in
  the same sentence.

See `skills/persian-date-check/references/date-rules.md` for the full
reasoning, and `skills/persian-date-check/references/examples.md` for
worked before/after cases.

## Roadmap

- Holiday dataset (fixed solar holidays first, lunar holidays with
  their sources stated).
- Word-form date parsing («بیست و یکم آبان»).
- Hijri (lunar) date cross-checks for religious dates stated
  alongside Jalali ones.
- CI action: fail a PR when a Persian file introduces a date error.

## License

MIT. Persian version: [README-fa.md](README-fa.md).
