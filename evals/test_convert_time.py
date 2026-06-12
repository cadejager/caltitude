#!/usr/bin/env python3
"""Deterministic unit tests for scripts/convert_time.py.

Run from anywhere:

    python3 evals/test_convert_time.py
    python3 -m unittest evals.test_convert_time   # if run as a module

These exercise the `convert()` library function directly (the same code path
the CLI uses) so the assertions are exact and machine-checkable. They cover:

  * local -> UTC and UTC -> local, both directions
  * DST boundaries (summer vs winter offsets for America/New_York)
  * the spring-forward gap (nonexistent local time) and fall-back ambiguity
  * the RFC-2822 email Date-header path
  * the "now" input
  * inputs that already carry an offset (--tz must be ignored)
  * invalid timezone and unparseable time handling
  * an overnight / timezone-crossing flight (date rolls forward)
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from datetime import datetime, timezone

# Load the script as a module by path so this test file does not depend on the
# plugin being installed/importable as a package.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, os.pardir, "scripts", "convert_time.py")
_spec = importlib.util.spec_from_file_location("convert_time", _SCRIPT)
convert_time = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert_time)

convert = convert_time.convert
parse_input_time = convert_time.parse_input_time


class LocalToUtc(unittest.TestCase):
    def test_la_afternoon_to_utc_pdt(self):
        # 2:30pm PDT (summer, -07:00) -> 21:30 UTC
        out = convert("2026-06-08 14:30", "to-utc", "America/Los_Angeles")
        self.assertEqual(out["result_utc"], "2026-06-08T21:30:00+00:00")
        self.assertEqual(out["interpreted_as"], "2026-06-08T14:30:00-07:00")
        self.assertIsNone(out["warning"])

    def test_berlin_to_utc(self):
        # 14:30 CEST (summer, +02:00) -> 12:30 UTC
        out = convert("2026-06-08 14:30", "to-utc", "Europe/Berlin")
        self.assertEqual(out["result_utc"], "2026-06-08T12:30:00+00:00")

    def test_utc_input_is_identity(self):
        out = convert("2026-06-08 14:30", "to-utc", "UTC")
        self.assertEqual(out["result_utc"], "2026-06-08T14:30:00+00:00")


class UtcToLocal(unittest.TestCase):
    def test_utc_to_new_york_summer(self):
        # 21:30 UTC -> 17:30 EDT (-04:00)
        out = convert("2026-06-08T21:30:00Z", "to-local", "America/New_York")
        self.assertEqual(out["result"], "2026-06-08T17:30:00-04:00")
        self.assertEqual(out["result_utc"], "2026-06-08T21:30:00+00:00")

    def test_bare_time_assumed_utc(self):
        # to-local with no offset on the input: treated as already-UTC.
        out = convert("2026-06-08 21:30", "to-local", "America/New_York")
        self.assertEqual(out["interpreted_as"], "2026-06-08T21:30:00+00:00")
        self.assertEqual(out["result"], "2026-06-08T17:30:00-04:00")

    def test_utc_to_tokyo_crosses_date(self):
        # 23:00 UTC -> 08:00 JST next calendar day (+09:00)
        out = convert("2026-12-31T23:00:00Z", "to-local", "Asia/Tokyo")
        self.assertEqual(out["result"], "2027-01-01T08:00:00+09:00")


class DstBoundaries(unittest.TestCase):
    def test_new_york_summer_offset_is_minus_4(self):
        out = convert("2026-07-01 12:00", "to-utc", "America/New_York")
        self.assertEqual(out["interpreted_as"], "2026-07-01T12:00:00-04:00")
        self.assertEqual(out["result_utc"], "2026-07-01T16:00:00+00:00")

    def test_new_york_winter_offset_is_minus_5(self):
        out = convert("2026-01-15 12:00", "to-utc", "America/New_York")
        self.assertEqual(out["interpreted_as"], "2026-01-15T12:00:00-05:00")
        self.assertEqual(out["result_utc"], "2026-01-15T17:00:00+00:00")

    def test_spring_forward_gap_is_flagged_nonexistent(self):
        # 02:30 on 2026-03-08 does not exist in America/New_York (clocks jump
        # 02:00 -> 03:00). Conversion still proceeds deterministically.
        out = convert("2026-03-08 02:30", "to-utc", "America/New_York")
        self.assertIsNotNone(out["warning"])
        self.assertIn("nonexistent", out["warning"])
        self.assertEqual(out["result_utc"], "2026-03-08T07:30:00+00:00")

    def test_fall_back_ambiguous_is_flagged(self):
        # 01:30 on 2026-11-01 happens twice; fold=0 picks the earlier (EDT)
        # occurrence (-04:00).
        out = convert("2026-11-01 01:30", "to-utc", "America/New_York")
        self.assertIsNotNone(out["warning"])
        self.assertIn("ambiguous", out["warning"])
        self.assertEqual(out["interpreted_as"], "2026-11-01T01:30:00-04:00")
        self.assertEqual(out["result_utc"], "2026-11-01T05:30:00+00:00")

    def test_ordinary_time_has_no_warning(self):
        out = convert("2026-06-15 12:00", "to-utc", "America/New_York")
        self.assertIsNone(out["warning"])


class Rfc2822DateHeader(unittest.TestCase):
    def test_date_header_carries_own_offset(self):
        out = convert("Mon, 8 Jun 2026 14:30:00 -0700", "to-utc", "UTC")
        self.assertEqual(out["interpreted_as"], "2026-06-08T14:30:00-07:00")
        self.assertEqual(out["result_utc"], "2026-06-08T21:30:00+00:00")

    def test_date_header_tz_flag_is_ignored(self):
        # The header carries -0700, so --tz Asia/Tokyo must NOT override it.
        out = convert("Mon, 8 Jun 2026 14:30:00 -0700", "to-utc", "Asia/Tokyo")
        self.assertEqual(out["interpreted_as"], "2026-06-08T14:30:00-07:00")
        self.assertEqual(out["result_utc"], "2026-06-08T21:30:00+00:00")


class InputCarriesOffset(unittest.TestCase):
    def test_iso_offset_ignores_tz_flag(self):
        # +02:00 in the string wins over --tz Asia/Tokyo.
        out = convert("2026-06-08T14:30:00+02:00", "to-utc", "Asia/Tokyo")
        self.assertEqual(out["interpreted_as"], "2026-06-08T14:30:00+02:00")
        self.assertEqual(out["result_utc"], "2026-06-08T12:30:00+00:00")

    def test_trailing_z_is_utc(self):
        dt, had_offset = parse_input_time("2026-06-08T14:30:00Z")
        self.assertTrue(had_offset)
        self.assertEqual(dt.utcoffset().total_seconds(), 0)


class NowInput(unittest.TestCase):
    def test_now_parses_as_aware_utc(self):
        dt, had_offset = parse_input_time("now")
        self.assertTrue(had_offset)
        self.assertIsNotNone(dt.tzinfo)
        self.assertEqual(dt.utcoffset().total_seconds(), 0)

    def test_now_is_close_to_real_now(self):
        before = datetime.now(timezone.utc)
        out = convert("now", "to-utc", "UTC")
        after = datetime.now(timezone.utc)
        result = datetime.fromisoformat(out["result_utc"])
        # "now" must land within the wall-clock window of the call.
        self.assertGreaterEqual(result, before.replace(microsecond=0))
        self.assertLessEqual(result, after)


class InvalidInputs(unittest.TestCase):
    def test_unknown_timezone_raises_valueerror(self):
        with self.assertRaises(ValueError):
            convert("2026-06-08 14:30", "to-utc", "Not/AZone")

    def test_unparseable_time_raises_valueerror(self):
        with self.assertRaises(ValueError):
            parse_input_time("garbage")

    def test_unknown_direction_raises(self):
        with self.assertRaises(ValueError):
            convert("2026-06-08 14:30", "sideways", "UTC")


class OvernightFlight(unittest.TestCase):
    """A real timezone-crossing red-eye: SFO 22:00 PDT -> JFK 06:30 EDT next day.

    Both legs are reported in local wall-clock time; converting each to UTC must
    yield the correct absolute instants and a ~5h30m wall duration."""

    def test_overnight_leg_utc_instants(self):
        dep = convert("2026-08-15 22:00", "to-utc", "America/Los_Angeles")
        arr = convert("2026-08-16 06:30", "to-utc", "America/New_York")
        self.assertEqual(dep["result_utc"], "2026-08-16T05:00:00+00:00")
        self.assertEqual(arr["result_utc"], "2026-08-16T10:30:00+00:00")
        d0 = datetime.fromisoformat(dep["result_utc"])
        d1 = datetime.fromisoformat(arr["result_utc"])
        self.assertEqual((d1 - d0).total_seconds(), 5.5 * 3600)
        self.assertGreater(d1, d0)


class PrettyLocalAndAbbrev(unittest.TestCase):
    """The pretty local string + zone abbreviation used to build event titles."""

    def test_to_utc_carries_local_pretty_pdt(self):
        # 8:30am in LA (summer) -> the local side is PDT.
        out = convert("2026-06-08 08:30", "to-utc", "America/Los_Angeles")
        self.assertEqual(out["tzabbrev"], "PDT")
        self.assertEqual(out["local_pretty"], "8:30a PDT")
        self.assertEqual(out["local_iso"], "2026-06-08T08:30:00-07:00")
        self.assertEqual(out["result_utc"], "2026-06-08T15:30:00+00:00")

    def test_to_utc_pm_meridiem_edt(self):
        # 5:05pm in NY (summer) -> EDT, pm meridiem.
        out = convert("2026-06-08 17:05", "to-utc", "America/New_York")
        self.assertEqual(out["tzabbrev"], "EDT")
        self.assertEqual(out["local_pretty"], "5:05p EDT")

    def test_to_local_pretty_matches_result(self):
        out = convert("2026-06-08T21:30:00Z", "to-local", "America/New_York")
        self.assertEqual(out["tzabbrev"], "EDT")
        self.assertEqual(out["local_pretty"], "5:30p EDT")
        self.assertEqual(out["local_iso"], out["result"])

    def test_winter_abbrev_is_standard(self):
        out = convert("2026-01-15 12:00", "to-utc", "America/New_York")
        self.assertEqual(out["tzabbrev"], "EST")
        self.assertEqual(out["local_pretty"], "12:00p EST")

    def test_noon_and_midnight_meridiem(self):
        noon = convert("2026-06-08 12:00", "to-utc", "UTC")
        mid = convert("2026-06-08 00:00", "to-utc", "UTC")
        self.assertEqual(noon["local_pretty"], "12:00p UTC")
        self.assertEqual(mid["local_pretty"], "12:00a UTC")


class DateOnlyInput(unittest.TestCase):
    """A date with no clock time must be flagged, not silently set to midnight."""

    def test_date_only_to_utc_is_flagged(self):
        out = convert("2026-07-01", "to-utc", "America/Los_Angeles")
        self.assertIsNotNone(out["warning"])
        self.assertIn("date-only", out["warning"])

    def test_date_only_to_local_is_flagged(self):
        out = convert("2026-07-01", "to-local", "America/New_York")
        self.assertIsNotNone(out["warning"])
        self.assertIn("date-only", out["warning"])

    def test_normal_time_not_flagged_date_only(self):
        out = convert("2026-07-01 09:00", "to-utc", "America/Los_Angeles")
        self.assertIsNone(out["warning"])

    def test_offset_input_not_flagged_date_only(self):
        out = convert("2026-06-08T14:30:00+02:00", "to-utc", "Asia/Tokyo")
        self.assertIsNone(out["warning"])

    def test_looks_date_only_helper(self):
        f = convert_time.looks_date_only
        self.assertTrue(f("2026-07-01"))
        self.assertFalse(f("2026-07-01 09:00"))
        self.assertFalse(f("2026-07-01T09:00"))
        self.assertFalse(f("now"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
