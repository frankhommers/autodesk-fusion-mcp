"""Tests for log timestamps and per-command duration logging."""

import re
import threading
import unittest

import _fusion_test_bootstrap  # noqa: F401  (installs adsk mock + parent pkg shim)

from fusion_bridge import dispatch


class FormatDurationTests(unittest.TestCase):
    def test_sub_millisecond_shows_zero_ms(self):
        self.assertEqual(dispatch.format_duration(0), "0ms")

    def test_under_one_second_shows_integer_ms(self):
        self.assertEqual(dispatch.format_duration(122), "122ms")
        self.assertEqual(dispatch.format_duration(999), "999ms")

    def test_one_second_boundary_shows_seconds(self):
        self.assertEqual(dispatch.format_duration(1000), "1.00s")

    def test_large_value_shows_seconds_two_decimals(self):
        self.assertEqual(dispatch.format_duration(4520), "4.52s")
