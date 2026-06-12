#!/usr/bin/env python3
"""Convert times between a local timezone and UTC.

Gmail stores per-field timestamps in UTC, but email bodies and human requests
usually talk in local time. This helper does the conversion both directions so
an agent never has to do timezone math in its head.

Three directions:
  to-utc     local wall-clock time  ->  UTC   (default)
  to-local   UTC time               ->  a local timezone
  to-zone    a wall-clock in one zone -> the same instant in another zone
             (used to anchor a flight's arrival end to its departure zone)

The input time can be:
  * an ISO-8601 string            e.g. "2026-06-08 14:30", "2026-06-08T14:30:00"
  * an RFC-2822 email Date header e.g. "Mon, 8 Jun 2026 14:30:00 -0700"
  * "now"

Timezones are IANA names (e.g. America/Los_Angeles, Europe/London, UTC).

Examples
--------
  # 2:30pm in LA -> UTC
  python convert_time.py to-utc "2026-06-08 14:30" --tz America/Los_Angeles

  # A UTC timestamp from Gmail -> New York wall-clock
  python convert_time.py to-local "2026-06-08T21:30:00Z" --tz America/New_York

  # An email's Date: header (carries its own offset) -> UTC
  python convert_time.py to-utc "Mon, 8 Jun 2026 14:30:00 -0700"

  # Machine-readable output for piping into other tools
  python convert_time.py to-utc "2026-06-08 14:30" --tz Europe/Berlin --json

  # Arrival 1:01pm Central, re-expressed in the departure (Mountain) zone so a
  # single calendar event can carry one TZID for both ends:
  python convert_time.py to-zone "2026-06-26 13:01" --from America/Chicago \
      --to America/Denver
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def add_days(date_str: str, n: int) -> str:
    """Return the date `n` days after `date_str` (both `YYYY-MM-DD`).

    Used to turn an inclusive end date (hotel checkout / car dropoff) into the
    EXCLUSIVE all-day DTEND the calendar wants: Nextcloud all-day events end the
    day before DTEND, so a stay through 06-11 must be created with end 06-12 to
    render check-in..checkout inclusive. Also makes a same-day item (start==end)
    a valid 1-day event. Keeps date math out of the model's head.
    """
    try:
        d = date.fromisoformat(date_str.strip())
    except ValueError:
        raise ValueError(f"Could not parse date: {date_str!r}. Use YYYY-MM-DD.")
    return (d + timedelta(days=n)).isoformat()


def parse_input_time(value: str) -> tuple[datetime, bool]:
    """Parse a time string into a datetime.

    Returns (dt, had_offset) where had_offset is True if the input itself
    specified a UTC offset (so the --tz flag should not override it).
    """
    value = value.strip()

    if value.lower() == "now":
        return datetime.now(timezone.utc), True

    # Try ISO-8601 first: it's the more constrained, unambiguous grammar, so it
    # can't silently misread (e.g. RFC-2822 windows two-digit years like
    # "Jun 70" into 1970). Accept a trailing "Z" as UTC; normalize it so 3.9/3.10
    # fromisoformat (which doesn't grok "Z") still works.
    iso = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(iso)
        return dt, dt.tzinfo is not None
    except ValueError:
        pass

    # Fall back to RFC-2822 for email Date headers,
    # e.g. "Mon, 8 Jun 2026 14:30:00 -0700".
    try:
        dt = parsedate_to_datetime(value)
        if dt is not None:
            # parsedate_to_datetime returns naive when no offset is present.
            return dt, dt.tzinfo is not None
    except (TypeError, ValueError):
        pass

    raise ValueError(
        f"Could not parse time: {value!r}. "
        "Use ISO-8601 (2026-06-08 14:30), an email Date header, or 'now'."
    )


def load_zone(name: str) -> ZoneInfo:
    if name is None:
        # Keep the library contract: callers get a clean ValueError, not a
        # TypeError from deep inside ZoneInfo/posixpath, when a zone is missing.
        raise ValueError("a timezone name is required, got None.")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Raise (not sys.exit) so convert() stays usable as a library function;
        # main() turns this into a clean exit. On Windows this also fires for
        # valid names when the `tzdata` package isn't installed.
        raise ValueError(
            f"Unknown timezone: {name!r}. Use an IANA name like "
            "'America/Los_Angeles', 'Europe/London', or 'UTC'."
        )


def looks_date_only(value: str) -> bool:
    """True if `value` carries a date but no clock time.

    A date-only input (e.g. "2026-07-01") would otherwise silently convert to
    local midnight, producing a confident-but-wrong instant. The orchestrator
    needs an explicit signal to skip such legs rather than inventing a time.
    Inputs that carry an offset/zone or the literal "now" are never date-only.
    """
    v = value.strip()
    if v.lower() == "now":
        return False
    # Any clock component (a colon-separated time, or a 'T'/space-delimited
    # time piece) means it is not date-only. We detect the *absence* of digits
    # that form a time. Simplest robust check: does the parsed datetime fall on
    # an exact midnight AND the string contains no ':' and no time-of-day token?
    if ":" in v:
        return False
    # Strip a leading date (YYYY-MM-DD or similar) and see if anything time-like
    # remains. If after the date there is no 'T'/space+digits, it's date-only.
    # Heuristic: a bare date has no whitespace/'T' followed by a digit.
    for sep in ("T", "t", " "):
        idx = v.find(sep)
        if idx != -1 and idx + 1 < len(v) and v[idx + 1].isdigit():
            return False
    return True


def pretty_local(dt: datetime) -> str:
    """Format an aware datetime as e.g. "8:30a PDT" (no leading zero on hour).

    `dt` must carry tzinfo so %Z resolves to the zone abbreviation. Minutes are
    always shown; the meridiem is a single lowercase letter (a/p) to match the
    compact title style the orchestrator wants.
    """
    hour12 = dt.hour % 12 or 12
    meridiem = "a" if dt.hour < 12 else "p"
    abbrev = dt.strftime("%Z")
    return f"{hour12}:{dt.minute:02d}{meridiem} {abbrev}".rstrip()


def dst_warning(dt: datetime, zone: ZoneInfo) -> str | None:
    """Flag a wall-clock time that is nonexistent or ambiguous in `zone`.

    `dt` must already carry tzinfo=zone. Returns a human-readable warning, or
    None for an ordinary unambiguous time. The conversion still proceeds (with
    Python's deterministic fold=0 choice) — this only surfaces the hazard so an
    LLM caller doesn't trust a silently-guessed instant.
    """
    # Nonexistent (spring-forward gap): the wall-clock round-trips to a
    # different wall-clock, i.e. this local time never actually occurs.
    roundtrip = dt.astimezone(timezone.utc).astimezone(zone)
    if roundtrip.replace(tzinfo=None) != dt.replace(tzinfo=None):
        return (
            "nonexistent local time (clocks spring forward across this hour); "
            f"interpreted as {dt.isoformat()}"
        )
    # Ambiguous (fall-back): the same wall-clock happens twice with different
    # offsets. fold=0 picks the earlier (pre-transition) occurrence.
    if dt.replace(fold=0).utcoffset() != dt.replace(fold=1).utcoffset():
        return (
            "ambiguous local time (clocks fall back, so this hour occurs twice); "
            "used the earlier occurrence (fold=0)"
        )
    return None


def convert(
    value: str,
    direction: str,
    tz_name: str = "UTC",
    from_tz: str | None = None,
    to_tz: str | None = None,
) -> dict:
    dt, had_offset = parse_input_time(value)
    warning = None

    # Flag a date-only input regardless of direction. We still convert (to local
    # midnight) so the JSON is well-formed, but the warning lets the caller skip
    # rather than trust an invented time. A string carrying its own offset can't
    # be date-only here (it would have a clock time alongside the offset).
    if not had_offset and looks_date_only(value):
        warning = (
            "date-only input (no clock time); converted to local midnight — "
            "do NOT trust this instant, supply a time of day"
        )

    if direction == "to-zone":
        # Re-express a wall-clock from one zone into another (same instant).
        src = load_zone(from_tz)
        out_zone = load_zone(to_tz)
        out_tz = to_tz
        if not had_offset:
            # Interpret a bare wall-clock as being in the SOURCE zone; that is
            # where any DST ambiguity lives.
            dt = dt.replace(tzinfo=src)
            if warning is None:
                warning = dst_warning(dt, src)
        result = dt.astimezone(out_zone)
        local = result
    else:
        zone = load_zone(tz_name)
        out_tz = tz_name
        if direction == "to-utc":
            if not had_offset:
                # Interpret a bare wall-clock time as being in --tz.
                dt = dt.replace(tzinfo=zone)
                if warning is None:
                    warning = dst_warning(dt, zone)
            result = dt.astimezone(timezone.utc)
            # The local side of a to-utc conversion is the input zone itself.
            local = dt.astimezone(zone)
        elif direction == "to-local":
            if not had_offset:
                # A bare time with no offset is assumed to already be UTC.
                dt = dt.replace(tzinfo=timezone.utc)
            result = dt.astimezone(zone)
            local = result
        else:  # pragma: no cover - argparse restricts choices
            raise ValueError(f"Unknown direction: {direction}")

    return {
        "input": value,
        "direction": direction,
        "tz": out_tz,
        "interpreted_as": dt.isoformat(),
        "result": result.isoformat(),
        "result_utc": result.astimezone(timezone.utc).isoformat(),
        "local_iso": local.isoformat(),
        "local_pretty": pretty_local(local),
        "tzabbrev": local.strftime("%Z"),
        "warning": warning,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert times between a local timezone and UTC.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "direction",
        choices=["to-utc", "to-local", "to-zone", "add-days"],
        help="to-utc: local -> UTC.  to-local: UTC -> local.  "
        "to-zone: re-express a wall-clock from --from into --to (same instant).  "
        "add-days: shift a YYYY-MM-DD date by --days (for exclusive all-day ends).",
    )
    parser.add_argument(
        "time",
        help="Time/date to operate on: ISO-8601, an email Date header, 'now', "
        "or a YYYY-MM-DD date for add-days.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="add-days only: number of days to shift the date (default 1).",
    )
    parser.add_argument(
        "--tz",
        default="UTC",
        help="IANA timezone for the local side (default: UTC). "
        "For to-utc it's the input's zone; for to-local it's the output's zone. "
        "Ignored when the input string already carries a UTC offset. "
        "Not used by to-zone (use --from/--to).",
    )
    parser.add_argument(
        "--from",
        dest="from_tz",
        help="to-zone only: IANA source zone the wall-clock is written in.",
    )
    parser.add_argument(
        "--to",
        dest="to_tz",
        help="to-zone only: IANA target zone to re-express the instant in.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full result as JSON (for scripting).",
    )
    args = parser.parse_args(argv)

    if args.direction == "add-days":
        try:
            print(add_days(args.time, args.days))
        except ValueError as exc:
            sys.exit(str(exc))
        return 0

    if args.direction == "to-zone" and not (args.from_tz and args.to_tz):
        sys.exit("to-zone requires both --from and --to IANA timezones.")

    try:
        out = convert(
            args.time, args.direction, args.tz, args.from_tz, args.to_tz
        )
    except ValueError as exc:
        sys.exit(str(exc))

    if out["warning"]:
        print(f"warning: {out['warning']}", file=sys.stderr)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(out["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
