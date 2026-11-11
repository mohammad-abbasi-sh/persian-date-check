# Examples — before / after

Every example below is real: the dates were checked with the tool
(reference date 2026-11-11, i.e. 20 Aban 1405) and the "after" lines
exit 0.

## 1. Wrong weekday — the classic

Before:

```text
مهلت ثبت‌نام جمعه ۲۱ آبان ۱۴۰۵ است.
```

```text
[ERROR] PDC-02 line 1: Wrong weekday: "جمعه ۲۱ آبان ۱۴۰۵" says جمعه, but that date is پنجشنبه
```

After:

```text
مهلت ثبت‌نام پنجشنبه ۲۱ آبان ۱۴۰۵ است.
```

21 Aban 1405 is Thursday 12 November 2026. The agent that wrote
«جمعه» was guessing.

## 2. Impossible date — Esfand in a non-leap year

Before:

```text
مهلت ۳۰ اسفند ۱۴۰۴ است.
```

```text
[ERROR] PDC-01 line 1: Impossible date: "۳۰ اسفند ۱۴۰۴" — day 30 does not exist
      اسفند ۱۴۰۴ has 29 days (Esfand has 30 days only in a leap year; 1404 is not a leap year)
```

After: `۳۰ اسفند ۱۴۰۳` (1403 *is* a leap year) — or `۲۹ اسفند ۱۴۰۴`.

## 3. Mismatched Jalali/Gregorian pair

Before:

```text
تاریخ انتشار ۲۰ آبان ۱۴۰۵ برابر با ۱۲ نوامبر ۲۰۲۶ است.
```

```text
[ERROR] PDC-03 line 1: Mismatched pair: "۲۰ آبان ۱۴۰۵" is 2026-11-11, not "۱۲ نوامبر ۲۰۲۶"
      The Jalali date converts to 2026-11-11 (۱۱ نوامبر ۲۰۲۶).
```

After:

```text
تاریخ انتشار ۲۰ آبان ۱۴۰۵ برابر با ۱۱ نوامبر ۲۰۲۶ است.
```

## 4. Relative date disagreeing with the absolute date

Before (reference date 2026-11-11):

```text
فردا ۲۲ آبان ۱۴۰۵ کلاس داریم.
```

```text
[ERROR] PDC-04 line 1: Relative date "فردا" resolves to 21 آبان 1405, but the same sentence also states ۲۲ آبان ۱۴۰۵
```

After: `فردا ۲۱ آبان ۱۴۰۵ کلاس داریم.` — tomorrow *is* 21 Aban.

## 5. Digit-script mixing and Arabic-Indic digits

Before:

```text
تاریخ ۲1 آبان ۱۴۰۵ ثبت شد.
تاریخ ٢١ آبان ١٤٠٥ ثبت شد.
```

```text
[WARNING] PDC-05: Mixed digit scripts inside one date: "۲1 آبان ۱۴۰۵"
[WARNING] PDC-06: Arabic-Indic digits (٠-٩) in a Persian date: "٢١ آبان ١٤٠٥"
```

After:

```text
تاریخ ۲۱ آبان ۱۴۰۵ ثبت شد.
```

## 6. Month-name misspelling (auto-fixed)

Before:

```text
جلسه ۲۵ ابان ۱۴۰۵ برگزار می‌شود.
```

```text
[WARNING] PDC-08: Possible month misspelling: "ابان" — did you mean "آبان"?
```

`--fix` corrects it to `۲۵ آبان ۱۴۰۵`.

## 7. A clean paragraph (exits 0)

```text
مهلت ثبت‌نام پنجشنبه ۲۱ آبان ۱۴۰۵ است.
جلسه دوشنبه ۲۵ آبان ۱۴۰۵ برگزار می‌شود.
تحویل پروژه ۲۰ آبان ۱۴۰۵ (۱۱ نوامبر ۲۰۲۶) است.
```

```text
0 error(s), 0 warning(s).
```
