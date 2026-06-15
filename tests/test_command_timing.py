"""Tests for log timestamps and per-command duration logging."""

import re
import threading
import time
import unittest
from datetime import datetime

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
        # Log from a background thread so the message is deferred, then wait
        # before flushing. If the stamp were computed in drain_logs() (flush
        # time) instead of at log time, it would land ~after `flush_marker`;
        # proving a comfortable gap rules that out.
        worker = threading.Thread(target=lambda: dispatch.log("deferred"))
        worker.start()
        worker.join()
        self.assertEqual(self._captured, [])  # deferred: nothing logged yet

        time.sleep(0.05)
        flush_marker = datetime.now()
        dispatch.drain_logs()

        self.assertEqual(len(self._captured), 1)
        captured = self._captured[0]
        self.assertRegex(captured, ISO_PREFIX_RE)
        self.assertTrue(captured.endswith(" deferred"))

        stamped_at = datetime.fromisoformat(captured.split(" ", 1)[0])
        gap_seconds = (flush_marker - stamped_at).total_seconds()
        self.assertGreaterEqual(
            gap_seconds,
            0.02,
            "deferred message must be stamped at log time, not flush time "
            f"(gap was {gap_seconds:.3f}s)",
        )
