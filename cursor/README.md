# Cursor — persian-date-check rule

`cursor/persian-date-check.mdc` is the Cursor version of this skill.
It carries the same contract in condensed form: check first with the
tool, fix mechanically into a `.fixed` file and review it, prove the
fix with a re-check until exit 0, and state the limits (dates stated
in text only — conversion belongs to a converter, holidays are a
separate dataset, word-form dates are not parsed).

## Install

Copy `cursor/persian-date-check.mdc` into your project's
`.cursor/rules/` directory (create it if needed). Cursor applies it
automatically. The rule points at the checker script — copy the whole
`skills/persian-date-check/` directory into your project, or install
the checker where the rule's commands can find it.

## What it covers

- The check-first contract (PDC-01 impossible dates, PDC-02 weekday
  mismatches, PDC-03 Gregorian-pair mismatches, PDC-04 relative-date
  mismatches, PDC-05 digit mixing, PDC-06 Arabic-Indic digits,
  PDC-07 implausible years, PDC-08 month misspellings).
- The fix rules (mechanical fixes only, never overwrite the input,
  PDC-01/03/04 need a human).
- The proof rule (re-check the fixed file until exit 0).
- The limit (dates stated in text only).

The full skill with references and the MCP server lives in
`skills/persian-date-check/` and `mcp-server/`.

## Other agents

- **Windsurf:** copy the `.mdc` file to `.windsurf/rules/` — the
  same format applies.
- **Cline:** copy `skills/persian-date-check/` into your Cline
  skills directory and point Cline at the SKILL.md.
- **Continue:** add the `skills/persian-date-check/` directory as a
  rule/context path in `config.yaml`, or paste the SKILL.md
  contract into a `.continue/rules/` file.
