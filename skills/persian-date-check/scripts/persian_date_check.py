#!/usr/bin/env python3
"""persian-date-check — audit Persian text for wrong Shamsi (Jalali) dates.

Agents writing Persian content constantly state Shamsi dates. Converters
(parsi-mcp, persian-text-skill, jalali-moment, PersianDate) will convert
any date you hand them — none of them reads a Persian paragraph, extracts
every date claim, and proves each one right or wrong. This tool is that
audit layer:

  PDC-01  impossible date      (31 Aban, 30 Esfand in a non-leap year, ...)
  PDC-02  weekday mismatch     ("Friday 21 Aban 1405" — 21 Aban is Thursday)
  PDC-03  Gregorian-pair mismatch  (20 Aban 1405 is NOT 12 Nov 2026)
  PDC-04  relative-date mismatch   ("3 days ago" next to a wrong absolute date)
  PDC-05  digit-script mixing inside one date (21 mixed with ۱۴۰۵)
  PDC-06  Arabic-Indic digits (٠-٩) in Persian text (should be ۰-۹)
  PDC-07  year out of range / implausible (typo like 14050, or year 1200)
  PDC-08  month-name misspelling (ابان for آبان) next to a day number

Zero-dependency: Python standard library only. No network access.

Usage:
    python3 persian_date_check.py check [file ...]   # stdin when no file
    python3 persian_date_check.py check text.md --json --today 2026-11-11
    python3 persian_date_check.py convert to-jalali 2026-11-11
    python3 persian_date_check.py convert to-gregorian 1405-08-20
    python3 persian_date_check.py convert today
    python3 persian_date_check.py check text.md --fix   # writes text.fixed.md

Exit codes: 0 = no errors, 1 = errors found, 2 = usage error /
unreadable file. Warnings never fail the check unless --strict is given.
"""
import argparse
import datetime
import json
import re
import sys

VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Calendar data (facts, not opinions)
# ---------------------------------------------------------------------------

FA_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
# Dari/Afghan variants of the same months (same calendar, same lengths).
FA_MONTHS_DARI = [
    "حمل", "ثور", "جوزا", "سرطان", "اسد", "سنبله",
    "میزان", "عقرب", "قوس", "جدی", "دلو", "حوت",
]
# Latin transliterations, as they appear in English text ("21 Aban 1405").
LATIN_MONTHS = {
    "farvardin": 1, "ordibehesht": 2, "khordad": 3, "tir": 4,
    "mordad": 5, "shahrivar": 6, "mehr": 7, "aban": 8, "azar": 9,
    "dey": 10, "bahman": 11, "esfand": 12,
}
FA_GREGORIAN_MONTHS = [
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
]
EN_GREGORIAN_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
# Persian week, Saturday-first. Index 0 = Saturday.
FA_WEEKDAYS = [
    "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه",
]
FA_WEEKDAYS_NORM = {
    "شنبه": 0, "یکشنبه": 1, "دوشنبه": 2, "سه‌شنبه": 3, "سه شنبه": 3,
    "چهارشنبه": 4, "پنجشنبه": 5, "پنج‌شنبه": 5, "جمعه": 6,
}
EN_WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday",
]
# English weekday name -> Persian weekday index (0 = Saturday).
EN_WEEKDAY_TO_FA = {
    "saturday": 0, "sunday": 1, "monday": 2, "tuesday": 3,
    "wednesday": 4, "thursday": 5, "friday": 6,
}
# Persian weekday index (0 = Saturday) -> Python weekday() (Monday = 0).
FA_TO_PY_WEEKDAY = {0: 5, 1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4}
PY_TO_FA_WEEKDAY = {v: k for k, v in FA_TO_PY_WEEKDAY.items()}

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
LATIN_DIGITS = "0123456789"
_DIGIT_MAP = {}
for _fa, _ar, _la in zip(FA_DIGITS, AR_DIGITS, LATIN_DIGITS):
    _DIGIT_MAP[_fa] = _la
    _DIGIT_MAP[_ar] = _la

# Month lengths: months 1-6 have 31 days, 7-11 have 30, Esfand 29/30.
_MONTH_LENGTHS = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

# Break years of the Jalali 33-year leap cycle (Borkowski 1996). This is
# astronomical data, not code: the years at which the leap pattern resets.
_JALALI_BREAKS = [
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635,
    2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178,
]
# 1 Farvardin 1 = 21 March 622 (Gregorian). Verified against jdatetime.
_EPOCH = datetime.date(622, 3, 21)
_MIN_YEAR = 1300
_MAX_YEAR = 1500


def _div(a, b):
    """Truncating division (C-style), not Python floor division."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _mod(a, b):
    """Truncating modulo, consistent with _div."""
    return a - _div(a, b) * b


# ---------------------------------------------------------------------------
# Jalali calendar arithmetic (stdlib only, verified against jdatetime)
# ---------------------------------------------------------------------------

def jalali_leap_info(jy):
    """Return (is_leap, gregorian_year_of_1_farvardin, march_day).

    Implements the Borkowski breaks method. Valid for the years covered
    by the breaks table (-61..3178); the checker only uses 1300..1500.
    """
    bl = len(_JALALI_BREAKS)
    gy = jy + 621
    leap_j = -14
    jp = _JALALI_BREAKS[0]
    jump = 0
    for i in range(1, bl):
        jm = _JALALI_BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return (leap == 0), gy, march


def is_leap_jalali(jy):
    return jalali_leap_info(jy)[0]


def jalali_month_length(jy, jm):
    if jm < 1 or jm > 12:
        return 0
    if jm == 12:
        return 30 if is_leap_jalali(jy) else 29
    return _MONTH_LENGTHS[jm - 1]


def jalali_to_gregorian(jy, jm, jd):
    """Convert a Jalali date to a Gregorian date (datetime.date)."""
    if not (1 <= jm <= 12):
        raise ValueError("month out of range: %s" % jm)
    if not (1 <= jd <= jalali_month_length(jy, jm)):
        raise ValueError("day out of range for %s-%s: %s" % (jy, jm, jd))
    days = 0
    # Whole 33-year cycles (12053 days each: 33*365 + 8 leaps).
    year = 1
    remaining_years = jy - 1
    cycles = remaining_years // 33
    days += cycles * 12053
    year += cycles * 33
    while year < jy:
        days += 366 if is_leap_jalali(year) else 365
        year += 1
    for m in range(1, jm):
        days += jalali_month_length(jy, m)
    days += jd - 1
    return _EPOCH + datetime.timedelta(days=days)


def gregorian_to_jalali(gy, gm, gd):
    """Convert a Gregorian date to a Jalali (year, month, day) tuple."""
    target = datetime.date(gy, gm, gd)
    days = (target - _EPOCH).days
    if days < 0:
        raise ValueError("date before Jalali epoch (622-03-21)")
    jy = 1
    cycles = days // 12053
    jy += cycles * 33
    days -= cycles * 12053
    while True:
        year_len = 366 if is_leap_jalali(jy) else 365
        if days < year_len:
            break
        days -= year_len
        jy += 1
    jm = 1
    while True:
        month_len = jalali_month_length(jy, jm)
        if days < month_len:
            break
        days -= month_len
        jm += 1
    return (jy, jm, days + 1)


def jalali_weekday(jy, jm, jd):
    """Persian weekday index (0 = Saturday) for a Jalali date."""
    g = jalali_to_gregorian(jy, jm, jd)
    return PY_TO_FA_WEEKDAY[g.weekday()]


def gregorian_weekday_fa(gy, gm, gd):
    """Persian weekday index (0 = Saturday) for a Gregorian date."""
    return PY_TO_FA_WEEKDAY[datetime.date(gy, gm, gd).weekday()]


# ---------------------------------------------------------------------------
# Digits
# ---------------------------------------------------------------------------

def normalize_digits(text):
    """Convert Persian and Arabic-Indic digits in text to Latin digits."""
    return "".join(_DIGIT_MAP.get(ch, ch) for ch in text)


def digit_script(text):
    """Return 'fa' / 'ar' / 'latn' / 'mixed' for the digits in text."""
    scripts = set()
    for ch in text:
        if ch in FA_DIGITS:
            scripts.add("fa")
        elif ch in AR_DIGITS:
            scripts.add("ar")
        elif ch in LATIN_DIGITS:
            scripts.add("latn")
    if len(scripts) > 1:
        return "mixed"
    if scripts:
        return scripts.pop()
    return "none"


def to_fa_digits(text):
    """Convert Latin digits in text to Persian digits."""
    table = {la: fa for la, fa in zip(LATIN_DIGITS, FA_DIGITS)}
    table.update({ar: fa for ar, fa in zip(AR_DIGITS, FA_DIGITS)})
    return "".join(table.get(ch, ch) for ch in text)


# ---------------------------------------------------------------------------
# Date extraction from Persian prose
# ---------------------------------------------------------------------------

_NUM = r"[0-9۰-۹٠-٩]"
_MONTH_ALT = "|".join(FA_MONTHS + FA_MONTHS_DARI + list(LATIN_MONTHS.keys()))
_WEEKDAY_ALT = "|".join(
    sorted(FA_WEEKDAYS_NORM.keys(), key=len, reverse=True)
    + ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday",
       "friday"])
_GREG_MONTH_FA_ALT = "|".join(FA_GREGORIAN_MONTHS)
_GREG_MONTH_EN_ALT = "|".join(EN_GREGORIAN_MONTHS)

# Long Jalali: "21 Aban 1405" / "۲۱ آبان ۱۴۰۵" / "جمعه ۲۱ آبان ۱۴۰۵"
RE_LONG_JALALI = re.compile(
    r"(?P<weekday>" + _WEEKDAY_ALT + r")?\s*[،,]?\s*"
    r"(?P<day>" + _NUM + r"{1,2})\s+"
    r"(?P<month>" + _MONTH_ALT + r")\s+"
    r"(?P<year>" + _NUM + r"{2,4})",
    re.IGNORECASE,
)
# Long Jalali without year: "21 Aban" (weekday can only be checked with a year)
RE_LONG_JALALI_NO_YEAR = re.compile(
    r"(?P<weekday>" + _WEEKDAY_ALT + r")?\s*[،,]?\s*"
    r"(?P<day>" + _NUM + r"{1,2})\s+"
    r"(?P<month>" + _MONTH_ALT + r")(?!\s*" + _NUM + r")",
    re.IGNORECASE,
)
# Month + year: "Aban 1405" / "آبان ۱۴۰۵"
RE_MONTH_YEAR = re.compile(
    r"(?P<month>" + _MONTH_ALT + r")\s+"
    r"(?P<year>" + _NUM + r"{3,4})",
    re.IGNORECASE,
)
# Numeric Jalali: "1405/08/21", "۱۴۰۵-۰۸-۲۱", "1405.8.21"
RE_NUMERIC_JALALI = re.compile(
    r"(?P<year>" + _NUM + r"{3,4})[/\-.](?P<month>" + _NUM + r"{1,2})[/\-.](?P<day>" + _NUM + r"{1,2})"
)
# Long Gregorian in Persian: "11 November 2026" / "۱۱ نوامبر ۲۰۲۶"
RE_LONG_GREGORIAN = re.compile(
    r"(?P<weekday_en>[A-Za-z]+day)?\s*[،,]?\s*"
    r"(?P<day>" + _NUM + r"{1,2})\s+"
    r"(?P<month>" + _GREG_MONTH_FA_ALT + r"|" + _GREG_MONTH_EN_ALT + r")\s+"
    r"(?P<year>" + _NUM + r"{4})",
    re.IGNORECASE,
)
# Numeric Gregorian: "2026-11-11" / "2026/11/11" (4-digit year first)
RE_NUMERIC_GREGORIAN = re.compile(
    r"(?P<year>" + _NUM + r"{4})[/\-.](?P<month>" + _NUM + r"{1,2})[/\-.](?P<day>" + _NUM + r"{1,2})"
)
# Relative dates: "3 days ago" / "۵ روز دیگر" / "2 weeks later"
_RELATIVE_UNITS = {
    "روز": 1, "هفته": 7, "ماه": 30, "سال": 365,
}
RE_RELATIVE = re.compile(
    r"(?P<num>" + _NUM + r"+)\s*(?P<unit>روز|هفته|ماه|سال)\s*"
    r"(?P<dir>پیش|قبل|دیگر|بعد|آینده)"
)
RE_RELATIVE_WORD = re.compile(
    r"(?P<word>امروز|فردا|پس‌فردا|پس فردا|دیروز|پریروز)"
)
# Possible month-name misspelling: a token next to a day number.
RE_MAYBE_MONTH = re.compile(
    r"(?P<day>" + _NUM + r"{1,2})\s+(?P<token>[آ-ی]{3,9})\s+(?P<year>" + _NUM + r"{2,4})"
)


def _levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[len(b)]


def _month_index(name):
    if name in FA_MONTHS:
        return FA_MONTHS.index(name) + 1
    if name in FA_MONTHS_DARI:
        return FA_MONTHS_DARI.index(name) + 1
    return LATIN_MONTHS.get(name.lower())


def _weekday_index(raw):
    if raw in FA_WEEKDAYS_NORM:
        return FA_WEEKDAYS_NORM[raw]
    return EN_WEEKDAY_TO_FA.get(raw.lower())


def _greg_month_index(name):
    low = name.lower()
    if name in FA_GREGORIAN_MONTHS:
        return FA_GREGORIAN_MONTHS.index(name) + 1
    if low in EN_GREGORIAN_MONTHS:
        return EN_GREGORIAN_MONTHS.index(low) + 1
    return None


def _parse_int(text):
    return int(normalize_digits(text))


class DateClaim:
    """One date claim extracted from text, with its source span."""

    def __init__(self, kind, year, month, day, start, end, raw,
                 weekday=None, weekday_raw=None, calendar="jalali"):
        self.kind = kind  # long | numeric | month-year | gregorian | relative
        self.year = year
        self.month = month
        self.day = day
        self.start = start
        self.end = end
        self.raw = raw
        self.weekday = weekday  # Persian weekday index 0=Saturday, or None
        self.weekday_raw = weekday_raw
        self.calendar = calendar

    def __repr__(self):
        return "<DateClaim %s %s-%s-%s %r>" % (
            self.calendar, self.year, self.month, self.day, self.raw)


def _overlaps(a_start, a_end, spans):
    return any(a_start < e and a_end > s for s, e in spans)


def extract_dates(text, reference_jalali=None):
    """Extract every date claim from Persian prose.

    Returns a list of DateClaim objects in order of appearance.
    Overlapping matches are resolved longest-first: a long date
    ("21 Aban 1405") wins over the month-year inside it.
    """
    claims = []
    spans = []

    def add(claim):
        # The long-date pattern can match a leading space when no weekday
        # is present; strip it so raw text and offsets stay clean.
        stripped = claim.raw.lstrip()
        lead = len(claim.raw) - len(stripped)
        if lead:
            claim.start += lead
            claim.raw = stripped
        if _overlaps(claim.start, claim.end, spans):
            return
        spans.append((claim.start, claim.end))
        claims.append(claim)

    # 1. Long Jalali with year (highest priority: longest spans).
    for m in RE_LONG_JALALI.finditer(text):
        wd = None
        wd_raw = None
        if m.group("weekday"):
            wd_raw = m.group("weekday")
            wd = _weekday_index(wd_raw)
        add(DateClaim(
            "long", _parse_int(m.group("year")),
            _month_index(m.group("month")), _parse_int(m.group("day")),
            m.start(), m.end(), m.group(0),
            weekday=wd, weekday_raw=wd_raw, calendar="jalali"))

    # 2. Numeric Jalali (year first: 1405/08/21).
    for m in RE_NUMERIC_JALALI.finditer(text):
        y, mo, d = (_parse_int(m.group("year")), _parse_int(m.group("month")),
                    _parse_int(m.group("day")))
        # A 4-digit-first numeric date with a year in the Gregorian range
        # (e.g. 2026/11/11) is Gregorian, not Jalali — leave it for the
        # Gregorian pass instead of claiming it as Jalali.
        if 1900 <= y <= 2200:
            continue
        add(DateClaim("numeric", y, mo, d, m.start(), m.end(),
                      m.group(0), calendar="jalali"))

    # 3. Long Gregorian ("11 November 2026" / "۱۱ نوامبر ۲۰۲۶").
    for m in RE_LONG_GREGORIAN.finditer(text):
        wd = None
        if m.group("weekday_en"):
            wd = EN_WEEKDAY_TO_FA.get(m.group("weekday_en").lower())
        add(DateClaim(
            "gregorian", _parse_int(m.group("year")),
            _greg_month_index(m.group("month")), _parse_int(m.group("day")),
            m.start(), m.end(), m.group(0),
            weekday=wd, weekday_raw=m.group("weekday_en"),
            calendar="gregorian"))

    # 4. Numeric Gregorian (2026-11-11).
    for m in RE_NUMERIC_GREGORIAN.finditer(text):
        y, mo, d = (_parse_int(m.group("year")), _parse_int(m.group("month")),
                    _parse_int(m.group("day")))
        if not (1900 <= y <= 2200):
            continue
        add(DateClaim("numeric", y, mo, d, m.start(), m.end(),
                      m.group(0), calendar="gregorian"))

    # 5. Long Jalali without year ("21 Aban").
    for m in RE_LONG_JALALI_NO_YEAR.finditer(text):
        wd = None
        wd_raw = None
        if m.group("weekday"):
            wd_raw = m.group("weekday")
            wd = _weekday_index(wd_raw)
        year = reference_jalali[0] if reference_jalali else None
        add(DateClaim(
            "long-no-year", year, _month_index(m.group("month")),
            _parse_int(m.group("day")), m.start(), m.end(), m.group(0),
            weekday=wd, weekday_raw=wd_raw, calendar="jalali"))

    # 6. Month + year ("Aban 1405").
    for m in RE_MONTH_YEAR.finditer(text):
        add(DateClaim(
            "month-year", _parse_int(m.group("year")),
            _month_index(m.group("month")), None,
            m.start(), m.end(), m.group(0), calendar="jalali"))

    # 7. Relative dates ("3 days ago", "۵ روز دیگر", "tomorrow"...).
    for m in RE_RELATIVE.finditer(text):
        num = _parse_int(m.group("num"))
        unit = _RELATIVE_UNITS[m.group("unit")]
        direction = -1 if m.group("dir") in ("پیش", "قبل") else 1
        add(DateClaim(
            "relative", None, None, None, m.start(), m.end(), m.group(0),
            calendar="relative"))
        claims[-1].relative_days = num * unit * direction
    for m in RE_RELATIVE_WORD.finditer(text):
        offsets = {"امروز": 0, "فردا": 1, "پس‌فردا": 2, "پس فردا": 2,
                   "دیروز": -1, "پریروز": -2}
        add(DateClaim(
            "relative", None, None, None, m.start(), m.end(), m.group(0),
            calendar="relative"))
        claims[-1].relative_days = offsets[m.group("word")]

    claims.sort(key=lambda c: c.start)
    return claims


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

class Finding:
    def __init__(self, code, severity, message, line=None, detail=None,
                 fix=None, claim=None):
        self.code = code
        self.severity = severity  # error | warning | info
        self.message = message
        self.line = line
        self.detail = detail
        self.fix = fix  # (start, end, replacement) for --fix, or None
        self.claim = claim

    def to_dict(self, source=None):
        d = {"code": self.code, "severity": self.severity,
             "message": self.message}
        if source:
            d["file"] = source
        if self.line is not None:
            d["line"] = self.line
        if self.detail:
            d["detail"] = self.detail
        return d


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _pair_context(text, claim):
    """Find a Gregorian claim paired with this Jalali claim.

    A pair is a Gregorian date in the same sentence (or in parentheses
    right after the Jalali date, or after "برابر با" / "=").
    """
    window_start = max(0, claim.start - 4)
    window_end = min(len(text), claim.end + 60)
    window = text[window_start:window_end]
    return window


def check_text(text, reference_gregorian=None, reference_jalali=None,
               strict=False):
    """Check Persian text for wrong Shamsi dates.

    reference_gregorian: datetime.date used to resolve relative dates
    and year-less dates (defaults to today). Returns a list of Findings.
    """
    if reference_gregorian is None:
        reference_gregorian = datetime.date.today()
    if reference_jalali is None:
        reference_jalali = gregorian_to_jalali(
            reference_gregorian.year, reference_gregorian.month,
            reference_gregorian.day)
    claims = extract_dates(text, reference_jalali=reference_jalali)
    findings = []
    jalali_claims = [c for c in claims if c.calendar == "jalali"]
    greg_claims = [c for c in claims if c.calendar == "gregorian"]

    # --- per-claim checks ----------------------------------------------
    for claim in claims:
        line = _line_of(text, claim.start)
        raw = claim.raw

        # Digit hygiene (PDC-05 / PDC-06): applies to every dated claim.
        script = digit_script(raw)
        if script == "mixed":
            findings.append(Finding(
                "PDC-05", "warning",
                "Mixed digit scripts inside one date: \"%s\"" % raw, line,
                detail="One date uses Persian, Latin or Arabic-Indic digits "
                       "together. Pick one script — Persian digits (۰-۹) "
                       "for Persian prose.",
                claim=claim))
        elif script == "ar":
            findings.append(Finding(
                "PDC-06", "warning",
                "Arabic-Indic digits (٠-٩) in a Persian date: \"%s\"" % raw, line,
                detail="Persian text uses Persian digits (۰-۹), not "
                       "Arabic-Indic digits (٠-٩). They look alike but are "
                       "different codepoints and break search.",
                claim=claim))

        if claim.calendar == "relative":
            continue

        # Year plausibility (PDC-07).
        if claim.year is not None:
            if claim.calendar == "jalali" and not (
                    _MIN_YEAR <= claim.year <= _MAX_YEAR):
                findings.append(Finding(
                    "PDC-07", "warning",
                    "Implausible Jalali year %s in \"%s\"" % (claim.year, raw),
                    line,
                    detail="Jalali years in running text are normally "
                           "%s-%s. %s looks like a typo (extra digit? "
                           "Gregorian year written as Jalali?)"
                           % (_MIN_YEAR, _MAX_YEAR, claim.year),
                    claim=claim))
            if claim.calendar == "gregorian" and not (
                    1900 <= claim.year <= 2200):
                findings.append(Finding(
                    "PDC-07", "warning",
                    "Implausible Gregorian year %s in \"%s\"" % (claim.year, raw),
                    line, claim=claim))

        # Month validity.
        if claim.month is not None and not (1 <= claim.month <= 12):
            findings.append(Finding(
                "PDC-01", "error",
                "Month %s does not exist in \"%s\"" % (claim.month, raw), line,
                detail="Months run 1-12.",
                claim=claim))
            continue

        # Day validity (PDC-01).
        if claim.day is not None and claim.year is not None:
            if claim.calendar == "jalali":
                max_day = jalali_month_length(claim.year, claim.month)
            else:
                try:
                    max_day = [31, 29 if _is_greg_leap(claim.year) else 28,
                               31, 30, 31, 30, 31, 31, 30, 31, 30,
                               31][claim.month - 1]
                except IndexError:
                    max_day = 31
            if claim.day < 1 or claim.day > max_day:
                if claim.calendar == "jalali":
                    month_name = FA_MONTHS[claim.month - 1]
                    year_text = to_fa_digits(str(claim.year))
                else:
                    month_name = EN_GREGORIAN_MONTHS[claim.month - 1].capitalize()
                    year_text = str(claim.year)
                detail = "%s %s has %d days" % (month_name, year_text,
                                                 max_day)
                if claim.calendar == "jalali" and claim.month == 12:
                    detail += (" (Esfand has 30 days only in a leap year; "
                               "%s is %s)" % (
                                   claim.year,
                                   "a leap year" if is_leap_jalali(claim.year)
                                   else "not a leap year"))
                findings.append(Finding(
                    "PDC-01", "error",
                    "Impossible date: \"%s\" — day %s does not exist"
                    % (raw, claim.day), line, detail=detail, claim=claim))
                continue  # a non-existent date has no weekday to check

        # Weekday check (PDC-02).
        if claim.weekday is not None and claim.day is not None \
                and claim.year is not None:
            try:
                if claim.calendar == "jalali":
                    actual = jalali_weekday(claim.year, claim.month,
                                            claim.day)
                else:
                    actual = gregorian_weekday_fa(claim.year, claim.month,
                                                  claim.day)
            except ValueError:
                actual = None
            if actual is not None and actual != claim.weekday:
                correct = FA_WEEKDAYS[actual]
                stated = claim.weekday_raw or FA_WEEKDAYS[claim.weekday]
                fix = None
                if claim.weekday_raw:
                    fix = (claim.start, claim.start + len(claim.weekday_raw),
                           correct)
                findings.append(Finding(
                    "PDC-02", "error",
                    "Wrong weekday: \"%s\" says %s, but that date is %s"
                    % (raw, stated, correct), line,
                    detail="The weekday is part of the claim and it is "
                           "provably wrong — recompute it from the calendar "
                           "instead of trusting the draft.",
                    fix=fix, claim=claim))

    # --- pair checks: Jalali + Gregorian stated together (PDC-03) ------
    for j in jalali_claims:
        if j.day is None or j.year is None:
            continue
        try:
            j_greg = jalali_to_gregorian(j.year, j.month, j.day)
        except ValueError:
            continue
        for g in greg_claims:
            if g.day is None or g.year is None:
                continue
            # Same sentence, or the Gregorian date sits within ~60 chars
            # after the Jalali date (parentheses / "برابر با" / "=").
            gap = g.start - j.end
            same_sentence = (
                0 <= gap <= 60
                and "\n" not in text[j.end:g.start]
                and not re.search(r"[.!؟]\s", text[j.end:g.start]))
            if not same_sentence:
                continue
            try:
                g_date = datetime.date(g.year, g.month, g.day)
            except ValueError:
                continue
            if g_date != j_greg:
                correct_g = j_greg
                correct_fa = "%s %s %s" % (
                    to_fa_digits(str(correct_g.day)),
                    FA_GREGORIAN_MONTHS[correct_g.month - 1],
                    to_fa_digits(str(correct_g.year)))
                findings.append(Finding(
                    "PDC-03", "error",
                    "Mismatched pair: \"%s\" is %s, not \"%s\""
                    % (j.raw, correct_g.isoformat(), g.raw),
                    _line_of(text, j.start),
                    detail="The Jalali date converts to %s (%s). The "
                           "Gregorian date written next to it disagrees — "
                           "one of the two was copied wrong."
                           % (correct_g.isoformat(), correct_fa),
                    claim=j))

    # --- relative-date checks (PDC-04) ----------------------------------
    # A relative expression ("3 days ago") is resolved against the
    # reference date; if an absolute date appears in the same sentence,
    # the two must agree.
    for rel in [c for c in claims if c.calendar == "relative"]:
        resolved = reference_gregorian + datetime.timedelta(
            days=getattr(rel, "relative_days", 0))
        rel_j = gregorian_to_jalali(resolved.year, resolved.month,
                                    resolved.day)
        # Find absolute claims in the same sentence.
        sent_start = text.rfind("\n", 0, rel.start) + 1
        sent_end = text.find("\n", rel.end)
        if sent_end == -1:
            sent_end = len(text)
        for abs_claim in claims:
            if abs_claim is rel or abs_claim.calendar == "relative":
                continue
            if not (sent_start <= abs_claim.start < sent_end):
                continue
            if abs_claim.day is None or abs_claim.year is None:
                continue
            try:
                if abs_claim.calendar == "jalali":
                    abs_g = jalali_to_gregorian(
                        abs_claim.year, abs_claim.month, abs_claim.day)
                else:
                    abs_g = datetime.date(abs_claim.year, abs_claim.month,
                                          abs_claim.day)
            except ValueError:
                continue
            if abs_g != resolved:
                findings.append(Finding(
                    "PDC-04", "error",
                    "Relative date \"%s\" resolves to %s, but the same sentence "
                    "also states %s" % (
                        rel.raw, "%d %s %d" % (
                            rel_j[2], FA_MONTHS[rel_j[1] - 1], rel_j[0]),
                        abs_claim.raw),
                    _line_of(text, rel.start),
                    detail="Relative to %s, \"%s\" is %s (%s). Either the "
                           "relative phrase or the absolute date is wrong."
                           % (reference_gregorian.isoformat(), rel.raw,
                              "%d %s %d" % (rel_j[2], FA_MONTHS[rel_j[1] - 1],
                                            rel_j[0]),
                              resolved.isoformat()),
                    claim=rel))

    # --- month-name misspelling (PDC-08) --------------------------------
    for m in RE_MAYBE_MONTH.finditer(text):
        token = m.group("token")
        if _month_index(token) is not None:
            continue  # a real month name, already handled
        best = None
        best_d = 99
        for name in FA_MONTHS:
            d = _levenshtein(token, name)
            if d < best_d:
                best_d, best = d, name
        if best_d == 1 and len(token) >= 3:
            findings.append(Finding(
                "PDC-08", "warning",
                "Possible month misspelling: \"%s\" — did you mean \"%s\"?"
                % (token, best),
                _line_of(text, m.start()),
                detail="The token sits where a month name belongs (between "
                       "a day number and a year) and is one edit away from "
                       "%s." % best,
                fix=(m.start("token"), m.end("token"), best)))

    findings.sort(key=lambda f: (f.line or 0, f.code))
    return findings


def _is_greg_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


# ---------------------------------------------------------------------------
# Fixing
# ---------------------------------------------------------------------------

def apply_fixes(text, findings):
    """Apply mechanical fixes (weekday corrections, month spelling).

    Returns (fixed_text, applied_count). Fixes are applied right-to-left
    so offsets stay valid.
    """
    fixes = [f.fix for f in findings if f.fix]
    fixes.sort(key=lambda x: x[0], reverse=True)
    applied = 0
    for start, end, replacement in fixes:
        text = text[:start] + replacement + text[end:]
        applied += 1
    return text, applied


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_input(path):
    if path == "-":
        return sys.stdin.read(), "<stdin>"
    with open(path, encoding="utf-8") as fh:
        return fh.read(), path


def cmd_check(args):
    if args.today:
        try:
            y, m, d = (int(p) for p in args.today.split("-"))
            ref_g = datetime.date(y, m, d)
        except ValueError:
            print("error: --today must be YYYY-MM-DD", file=sys.stderr)
            return 2
    else:
        ref_g = datetime.date.today()
    ref_j = gregorian_to_jalali(ref_g.year, ref_g.month, ref_g.day)

    inputs = args.files or ["-"]
    all_findings = []
    outputs = []
    for path in inputs:
        try:
            text, source = _read_input(path)
        except (OSError, UnicodeDecodeError) as exc:
            print("error: cannot read %s: %s" % (path, exc), file=sys.stderr)
            return 2
        findings = check_text(text, reference_gregorian=ref_g,
                              reference_jalali=ref_j, strict=args.strict)
        for f in findings:
            f.source = source
        all_findings.extend(findings)
        if args.fix and path != "-":
            fixed, applied = apply_fixes(text, findings)
            if applied:
                out_path = path + ".fixed"
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(fixed)
                outputs.append("%s: %d fix(es) -> %s"
                               % (path, applied, out_path))
        if args.json:
            continue
        if findings:
            print("== %s ==" % source)
            for f in findings:
                line = "line %s: " % f.line if f.line else ""
                print("[%s] %s %s%s" % (f.severity.upper(), f.code, line,
                                        f.message))
                if f.detail:
                    print("      %s" % f.detail)
        else:
            print("%s: no date problems found." % source)
    for line in outputs:
        print(line)

    errors = sum(1 for f in all_findings if f.severity == "error")
    warnings = sum(1 for f in all_findings if f.severity == "warning")
    if args.strict:
        errors += warnings
    if args.json:
        payload = {
            "counts": {"error": errors, "warning": warnings,
                       "info": sum(1 for f in all_findings
                                   if f.severity == "info")},
            "findings": [f.to_dict(getattr(f, "source", None))
                         for f in all_findings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("%d error(s), %d warning(s)." % (errors, warnings))
    return 1 if errors else 0


def _parse_ymd(text):
    parts = re.split(r"[/\-.]", normalize_digits(text.strip()))
    if len(parts) != 3:
        raise ValueError("expected YYYY-MM-DD, got %r" % text)
    return tuple(int(p) for p in parts)


def cmd_convert(args):
    if args.action == "today":
        today = datetime.date.today()
        jy, jm, jd = gregorian_to_jalali(today.year, today.month, today.day)
        print("Gregorian: %s (%s)" % (
            today.isoformat(), today.strftime("%A")))
        print("Jalali: %d %s %d (%s)" % (
            jd, FA_MONTHS[jm - 1], jy,
            FA_WEEKDAYS[PY_TO_FA_WEEKDAY[today.weekday()]]))
        return 0
    if args.action == "to-jalali":
        try:
            gy, gm, gd = _parse_ymd(args.date)
            datetime.date(gy, gm, gd)
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
        wd = FA_WEEKDAYS[gregorian_weekday_fa(gy, gm, gd)]
        print("%d %s %d (%s)" % (jd, FA_MONTHS[jm - 1], jy, wd))
        print("%s = %s" % (args.date, "%04d-%02d-%02d" % (jy, jm, jd)))
        return 0
    if args.action == "to-gregorian":
        try:
            jy, jm, jd = _parse_ymd(args.date)
            g = jalali_to_gregorian(jy, jm, jd)
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        print("%s (%s)" % (g.isoformat(), g.strftime("%A")))
        return 0
    print("error: unknown convert action %r" % args.action, file=sys.stderr)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="persian_date_check",
        description="Audit Persian text for wrong Shamsi (Jalali) dates.")
    parser.add_argument("--version", action="version",
                        version="persian-date-check %s" % VERSION)
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="check files or stdin for wrong "
                             "Shamsi dates")
    p_check.add_argument("files", nargs="*", help="files to check "
                         "(stdin when omitted)")
    p_check.add_argument("--today", help="reference date YYYY-MM-DD for "
                         "relative dates (default: today)")
    p_check.add_argument("--json", action="store_true",
                         help="machine-readable JSON output")
    p_check.add_argument("--strict", action="store_true",
                         help="warnings also fail the check")
    p_check.add_argument("--fix", action="store_true",
                         help="write <file>.fixed with mechanical fixes "
                         "(weekday, month spelling)")

    p_conv = sub.add_parser("convert", help="convert a single date")
    p_conv.add_argument("action", choices=["to-jalali", "to-gregorian",
                                           "today"])
    p_conv.add_argument("date", nargs="?", help="date as YYYY-MM-DD")

    args = parser.parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "convert":
        if args.action != "today" and not args.date:
            print("error: convert %s needs a date" % args.action,
                  file=sys.stderr)
            return 2
        return cmd_convert(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
