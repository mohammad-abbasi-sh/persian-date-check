"""Tests for persian-date-check.

Conversion anchors are verified against jdatetime (independent
implementation) and against published converters for 20 Aban 1405 =
11 November 2026. Round-trip tests cover every day in the supported
range without any external dependency.
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent
                       / "skills" / "persian-date-check" / "scripts"))
import persian_date_check as pdc

HERE = Path(__file__).parent
CHECKER = (HERE.parent / "skills" / "persian-date-check" / "scripts"
           / "persian_date_check.py")
REF_G = datetime.date(2026, 11, 11)  # Wednesday, 20 Aban 1405


def check(text, ref=REF_G):
    return pdc.check_text(text, reference_gregorian=ref)


def codes(findings):
    return sorted(f.code for f in findings)


def errors(findings):
    return [f for f in findings if f.severity == "error"]


# ---------------------------------------------------------------------------
# Conversion: verified anchors
# ---------------------------------------------------------------------------

ANCHORS = [
    # (gregorian, jalali) — verified against jdatetime + web converters.
    (datetime.date(2026, 11, 11), (1405, 8, 20)),
    (datetime.date(2026, 11, 12), (1405, 8, 21)),
    (datetime.date(2026, 3, 21), (1405, 1, 1)),
    (datetime.date(2026, 3, 20), (1404, 12, 29)),
    (datetime.date(2025, 3, 21), (1404, 1, 1)),
    (datetime.date(2025, 3, 20), (1403, 12, 30)),
    (datetime.date(2024, 3, 20), (1403, 1, 1)),
    (datetime.date(2023, 3, 21), (1402, 1, 1)),
    (datetime.date(2020, 3, 20), (1399, 1, 1)),
    (datetime.date(2000, 1, 1), (1378, 10, 11)),
    (datetime.date(1990, 1, 1), (1368, 10, 11)),
    (datetime.date(2027, 3, 21), (1406, 1, 1)),
    (datetime.date(2030, 1, 1), (1408, 10, 12)),
]


@pytest.mark.parametrize("g,j", ANCHORS)
def test_anchor_gregorian_to_jalali(g, j):
    assert pdc.gregorian_to_jalali(g.year, g.month, g.day) == j


@pytest.mark.parametrize("g,j", ANCHORS)
def test_anchor_jalali_to_gregorian(g, j):
    assert pdc.jalali_to_gregorian(*j) == g


def test_round_trip_jalali_range():
    """Every Jalali day 1300-01-01..1500-12-29 converts back to itself."""
    for jy in range(1300, 1501):
        for jm in range(1, 13):
            ml = pdc.jalali_month_length(jy, jm)
            for jd in (1, ml):
                g = pdc.jalali_to_gregorian(jy, jm, jd)
                assert pdc.gregorian_to_jalali(g.year, g.month, g.day) \
                    == (jy, jm, jd)


def test_round_trip_gregorian_range():
    """Every Gregorian day 1921-03-21..2121-03-21 converts back to itself."""
    d = datetime.date(1921, 3, 21)
    end = datetime.date(2121, 3, 21)
    while d <= end:
        jy, jm, jd = pdc.gregorian_to_jalali(d.year, d.month, d.day)
        assert pdc.jalali_to_gregorian(jy, jm, jd) == d
        d += datetime.timedelta(days=1)


def test_leap_years():
    assert pdc.is_leap_jalali(1403) is True
    assert pdc.is_leap_jalali(1408) is True
    assert pdc.is_leap_jalali(1404) is False
    assert pdc.is_leap_jalali(1409) is False
    assert pdc.is_leap_jalali(1411) is False
    # The 5-year gaps in the cycle: 1403 -> 1408, 1370 -> 1375.
    assert pdc.is_leap_jalali(1407) is False
    assert pdc.is_leap_jalali(1375) is True


def test_month_lengths():
    assert pdc.jalali_month_length(1405, 1) == 31
    assert pdc.jalali_month_length(1405, 6) == 31
    assert pdc.jalali_month_length(1405, 7) == 30
    assert pdc.jalali_month_length(1405, 8) == 30
    assert pdc.jalali_month_length(1405, 12) == 29
    assert pdc.jalali_month_length(1403, 12) == 30  # leap year
    assert pdc.jalali_month_length(1404, 12) == 29


def test_weekdays():
    # 20 Aban 1405 = Wednesday 11 Nov 2026; 21 Aban = Thursday.
    assert pdc.FA_WEEKDAYS[pdc.jalali_weekday(1405, 8, 20)] == "چهارشنبه"
    assert pdc.FA_WEEKDAYS[pdc.jalali_weekday(1405, 8, 21)] == "پنجشنبه"
    assert pdc.FA_WEEKDAYS[pdc.jalali_weekday(1405, 1, 1)] == "شنبه"
    assert pdc.FA_WEEKDAYS[pdc.jalali_weekday(1406, 1, 1)] == "یکشنبه"
    with pytest.raises(ValueError):
        pdc.jalali_to_gregorian(1405, 8, 31)


def test_digits():
    assert pdc.normalize_digits("۲۱ آبان ۱۴۰۵") == "21 آبان 1405"
    assert pdc.normalize_digits("٢١ آبان ١٤٠٥") == "21 آبان 1405"
    assert pdc.digit_script("۲۱") == "fa"
    assert pdc.digit_script("٢١") == "ar"
    assert pdc.digit_script("21") == "latn"
    assert pdc.digit_script("۲1") == "mixed"
    assert pdc.digit_script("آبان") == "none"
    assert pdc.to_fa_digits("21 آبان 1405") == "۲۱ آبان ۱۴۰۵"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extract_long_jalali():
    claims = pdc.extract_dates("جلسه ۲۱ آبان ۱۴۰۵ است.")
    assert len(claims) == 1
    c = claims[0]
    assert (c.year, c.month, c.day) == (1405, 8, 21)
    assert c.calendar == "jalali"


def test_extract_long_jalali_latin_digits():
    claims = pdc.extract_dates("meeting on 21 Aban 1405")
    assert len(claims) == 1
    assert (claims[0].year, claims[0].month, claims[0].day) == (1405, 8, 21)


def test_extract_english_weekday_latin_month():
    claims = pdc.extract_dates("Friday 21 Aban 1405")
    assert len(claims) == 1
    assert claims[0].weekday == 6  # Friday
    f = errors(check("The deadline is Friday 21 Aban 1405."))
    assert codes(f) == ["PDC-02"]
    assert "Thursday" in f[0].detail or "پنجشنبه" in f[0].message


def test_extract_weekday_attached():
    claims = pdc.extract_dates("جمعه ۲۱ آبان ۱۴۰۵")
    assert claims[0].weekday == 6  # Friday
    assert claims[0].weekday_raw == "جمعه"


def test_extract_numeric_jalali():
    claims = pdc.extract_dates("تاریخ 1405/08/21 است.")
    assert len(claims) == 1
    assert (claims[0].year, claims[0].month, claims[0].day) == (1405, 8, 21)


def test_extract_numeric_gregorian_not_jalali():
    claims = pdc.extract_dates("تاریخ 2026-11-11 است.")
    assert len(claims) == 1
    assert claims[0].calendar == "gregorian"
    assert (claims[0].year, claims[0].month, claims[0].day) == (2026, 11, 11)


def test_extract_gregorian_fa_month():
    claims = pdc.extract_dates("۱۱ نوامبر ۲۰۲۶")
    assert len(claims) == 1
    assert claims[0].calendar == "gregorian"
    assert (claims[0].year, claims[0].month, claims[0].day) == (2026, 11, 11)


def test_extract_month_year():
    claims = pdc.extract_dates("آرشیو آبان ۱۴۰۵")
    assert len(claims) == 1
    assert claims[0].kind == "month-year"
    assert claims[0].day is None


def test_extract_dari_month():
    claims = pdc.extract_dates("جلسه ۲۱ عقرب ۱۴۰۵")
    assert len(claims) == 1
    assert (claims[0].year, claims[0].month, claims[0].day) == (1405, 8, 21)


def test_extract_relative():
    claims = pdc.extract_dates("۳ روز پیش آمدم.")
    rel = [c for c in claims if c.calendar == "relative"]
    assert len(rel) == 1
    assert rel[0].relative_days == -3


# ---------------------------------------------------------------------------
# Checks PDC-01..PDC-08
# ---------------------------------------------------------------------------

def test_pdc01_impossible_day():
    f = errors(check("این رویداد ۳۱ آبان ۱۴۰۵ اتفاق افتاد."))
    assert codes(f) == ["PDC-01"]
    assert "30 days" in f[0].detail or "۳۰" in f[0].detail


def test_pdc01_esfand_leap():
    assert errors(check("مهلت ۳۰ اسفند ۱۴۰۳ است.")) == []
    f = errors(check("مهلت ۳۰ اسفند ۱۴۰۴ است."))
    assert codes(f) == ["PDC-01"]
    assert "leap year" in f[0].detail


def test_pdc01_gregorian():
    f = errors(check("The date is 2026-11-31."))
    assert codes(f) == ["PDC-01"]


def test_pdc02_wrong_weekday():
    f = errors(check("مهلت ثبت‌نام جمعه ۲۱ آبان ۱۴۰۵ است."))
    assert codes(f) == ["PDC-02"]
    assert "پنجشنبه" in f[0].message
    assert f[0].fix is not None  # mechanical fix available


def test_pdc02_correct_weekday_passes():
    assert errors(check("مهلت پنجشنبه ۲۱ آبان ۱۴۰۵ است.")) == []


def test_pdc03_mismatched_pair():
    f = errors(check("تاریخ ۲۰ آبان ۱۴۰۵ برابر با ۱۲ نوامبر ۲۰۲۶ است."))
    assert codes(f) == ["PDC-03"]
    assert "2026-11-11" in f[0].detail


def test_pdc03_matching_pair_passes():
    assert errors(check("تاریخ ۲۰ آبان ۱۴۰۵ (۱۱ نوامبر ۲۰۲۶) است.")) == []


def test_pdc04_relative_mismatch():
    f = errors(check("فردا ۲۲ آبان ۱۴۰۵ کلاس داریم."))
    assert codes(f) == ["PDC-04"]


def test_pdc04_relative_match_passes():
    assert errors(check("فردا ۲۱ آبان ۱۴۰۵ کلاس داریم.")) == []


def test_pdc05_mixed_digits():
    f = check("تاریخ ۲1 آبان ۱۴۰۵ ثبت شد.")
    assert codes(f) == ["PDC-05"]
    assert f[0].severity == "warning"


def test_pdc06_arabic_indic_digits():
    f = check("تاریخ ٢١ آبان ١٤٠٥ ثبت شد.")
    assert codes(f) == ["PDC-06"]


def test_pdc07_implausible_year():
    f = check("آرشیو مهر ۱۲۰۰ بررسی شد.")
    assert codes(f) == ["PDC-07"]


def test_pdc08_month_misspelling():
    f = check("جلسه ۲۵ ابان ۱۴۰۵ برگزار می‌شود.")
    assert codes(f) == ["PDC-08"]
    assert "آبان" in f[0].message
    assert f[0].fix is not None


# ---------------------------------------------------------------------------
# Fixtures end-to-end
# ---------------------------------------------------------------------------

def test_fixture_broken():
    text = (HERE / "fixtures" / "broken-fa.md").read_text(encoding="utf-8")
    f = check(text)
    assert codes(errors(f)) == ["PDC-01", "PDC-02", "PDC-02", "PDC-03",
                                "PDC-04"]
    assert len(f) == 5


def test_fixture_clean():
    text = (HERE / "fixtures" / "clean-fa.md").read_text(encoding="utf-8")
    assert check(text) == []


def test_fixture_warnings():
    text = (HERE / "fixtures" / "warnings-fa.md").read_text(encoding="utf-8")
    f = check(text)
    assert codes(f) == ["PDC-05", "PDC-06", "PDC-07", "PDC-08"]
    assert errors(f) == []


# ---------------------------------------------------------------------------
# --fix
# ---------------------------------------------------------------------------

def test_fix_weekday_and_spelling(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text("مهلت جمعه ۲۱ آبان ۱۴۰۵ است.\nجلسه ۲۵ ابان ۱۴۰۵ است.\n",
                   encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "check", str(src),
         "--today", "2026-11-11", "--fix"],
        capture_output=True, text=True)
    fixed = (tmp_path / "doc.md.fixed").read_text(encoding="utf-8")
    assert "پنجشنبه ۲۱ آبان ۱۴۰۵" in fixed
    assert "۲۵ آبان ۱۴۰۵" in fixed
    assert "ابان" not in fixed
    # Re-checking the fixed file is clean.
    proc2 = subprocess.run(
        [sys.executable, str(CHECKER), "check",
         str(tmp_path / "doc.md.fixed"), "--today", "2026-11-11"],
        capture_output=True, text=True)
    assert proc2.returncode == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(*argv, stdin=None):
    return subprocess.run([sys.executable, str(CHECKER)] + list(argv),
                          capture_output=True, text=True, input=stdin)


def test_cli_exit_codes():
    assert run_cli("check", str(HERE / "fixtures" / "clean-fa.md"),
                   "--today", "2026-11-11").returncode == 0
    assert run_cli("check", str(HERE / "fixtures" / "broken-fa.md"),
                   "--today", "2026-11-11").returncode == 1
    assert run_cli("check", str(HERE / "fixtures" / "warnings-fa.md"),
                   "--today", "2026-11-11").returncode == 0
    assert run_cli("check", str(HERE / "fixtures" / "warnings-fa.md"),
                   "--today", "2026-11-11", "--strict").returncode == 1
    assert run_cli("check", "/nonexistent.md").returncode == 2


def test_cli_stdin():
    proc = run_cli("check", "--today", "2026-11-11",
                   stdin="جمعه ۲۱ آبان ۱۴۰۵\n")
    assert proc.returncode == 1
    assert "PDC-02" in proc.stdout


def test_cli_json():
    proc = run_cli("check", str(HERE / "fixtures" / "broken-fa.md"),
                   "--today", "2026-11-11", "--json")
    payload = json.loads(proc.stdout)
    assert payload["counts"] == {"error": 5, "warning": 0, "info": 0}
    assert len(payload["findings"]) == 5
    assert payload["findings"][0]["code"] == "PDC-02"


def test_cli_convert():
    out = run_cli("convert", "to-jalali", "2026-11-11").stdout
    assert "20 آبان 1405" in out
    out = run_cli("convert", "to-gregorian", "1405-08-20").stdout
    assert "2026-11-11" in out
    assert "Wednesday" in out
    assert run_cli("convert", "to-gregorian", "1405-08-31").returncode == 2
    assert run_cli("convert", "to-jalali", "not-a-date").returncode == 2
