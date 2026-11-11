# Date rules — why each check exists

## The Jalali calendar in one page

- 12 months. Months 1–6 (فروردین، اردیبهشت، خرداد، تیر، مرداد،
  شهریور) have **31 days**. Months 7–11 (مهر، آبان، آذر، دی، بهمن)
  have **30 days**. Month 12 (اسفند) has **29 days**, or **30 in a
  leap year**.
- Leap years follow a 33-year cycle with occasional 5-year gaps
  (not a plain "every 4 years" rule). Recent leaps: 1399, 1403,
  1408. Non-leaps nearby: 1404, 1409, 1411. Never guess whether a
  year is a leap year — compute it (the tool's leap table is
  verified against jdatetime for 1300–1500).
- The week starts **Saturday** (شنبه). Order: شنبه، یکشنبه، دوشنبه،
  سه‌شنبه، چهارشنبه، پنجشنبه، جمعه.
- 1 Farvardin 1 = 21 March 622 (Gregorian). 1 Farvardin 1405 =
  Saturday 21 March 2026. 20 Aban 1405 = Wednesday 11 November 2026.
- Dari (Afghan) month names are the same calendar: حمل، ثور، جوزا،
  سرطان، اسد، سنبله، میزان، عقرب، قوس، جدی، دلو، حوت.

## The three errors agents make most

1. **Wrong weekday (PDC-02).** The agent "knows" the date and
   invents the weekday from feel. Weekdays are the single most
   common wrong token in Persian date claims — always recompute
   from the calendar, never trust the draft.
2. **Impossible day (PDC-01).** 31 Aban, 31 Azar, 30 Esfand in a
   non-leap year, 31 November. The agent copies a day number from
   one month into another.
3. **Mismatched pair (PDC-03).** The text states the date twice —
   once Jalali, once Gregorian — and the two disagree, usually by
   one day (the agent converted in its head, or copied last year's
   pair). When a text states a date twice, the pair *is* the check.

## Digit rules

- Persian prose uses Persian digits **۰-۹**. Arabic-Indic digits
  **٠-٩** look almost identical but are different codepoints: a
  search for «۱۴۰۵» does not find «١٤٠٥», and a date parser that
  only handles one script silently misreads the other.
- Never mix scripts inside one date («۲1 آبان ۱۴۰۵»).
- Latin digits are fine in Latin-script contexts («21 Aban 1405»,
  ISO dates «1405-08-21») but not mixed with Persian digits in one
  date.

## What this skill deliberately does not do

- **Holidays.** Iranian holidays (Nowruz, religious observances,
  the shifting lunar holidays) are a separate dataset with their
  own sources. A date can be valid and still be a holiday; a
  holiday claim needs a holiday dataset, not a calendar.
- **Word-form dates.** «بیست و یکم آبان» (twenty-first of Aban)
  is not parsed. If your corpus uses word-form dates, normalise
  them to digits first.
- **Relative dates without an anchor.** «۳ روز پیش» can only be
  checked against a reference date (`--today`) and only flags
  when an absolute date in the same sentence disagrees with it.
- **Time-of-day, timezones, Hijri dates.** Out of scope.

## Neighbours — and the exact difference

- **Converters** (parsi-mcp, 56 tools incl. Jalali convert/format/
  parse/relative/holidays; FarsiTools, paid MCP; persian-text-skill,
  SKILL.md + stdlib scripts incl. Jalali conversion; jalali-moment
  ★442; PersianDate ★608; jdatetime): they convert a date you hand
  them. None reads a paragraph and proves the dates *in it* right
  or wrong. This skill is the audit layer on top of them.
- **CheckDateShamsi** (C#, 2 commits, 2024): validates that one
  Shamsi date exists. No text auditing, no weekday check, no
  Gregorian cross-check, no skill, no CLI for agents.
- **bidi-skills** (same author): fixes RTL *text* (ZWNJ, codepoints,
  bidi order). It never checks whether a date is true. The two
  skills compose: normalise the text with bidi-skills, then audit
  its dates with this one.
