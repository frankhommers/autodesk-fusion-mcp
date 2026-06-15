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


ISO_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3} ")


class LogTimestampTests(unittest.TestCase):
    def setUp(self):
        # Capture whatever dispatch hands to the underlying futil.log.
        self._captured = []
        self._orig_futil_log = dispatch.futil.log
        dispatch.futil.log = lambda *a, **kw: self._captured.append(a[0])
        # Isolate the deferred-message queue from other tests.
        with dispatch._msg_lock:
            dispatch._deferred_messages.clear()

    def tearDown(self):
        dispatch.futil.log = self._orig_futil_log
        with dispatch._msg_lock:
            dispatch._deferred_messages.clear()

    def test_main_thread_message_is_timestamped(self):
        dispatch.log("hello")
        self.assertEqual(len(self._captured), 1)
        self.assertRegex(self._captured[0], ISO_PREFIX_RE)
        self.assertTrue(self._captured[0].endswith(" hello"))

    def test_deferred_message_is_timestamped_at_log_time(self):
        # A background thread defers the message; nothing is logged yet.
        worker = threading.Thread(target=lambda: dispatch.log("deferred"))
        worker.start()
        worker.join()
        self.assertEqual(self._captured, [])
        # Flushing replays the already-stamped message.
        dispatch.drain_logs()
        self.assertEqual(len(self._captured), 1)
        self.assertRegex(self._captured[0], ISO_PREFIX_RE)
        self.assertTrue(self._captured[0].endswith(" deferred"))
