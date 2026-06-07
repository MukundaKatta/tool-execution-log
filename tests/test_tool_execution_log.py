"""Standard-library ``unittest`` suite for ``tool_execution_log``.

Run with::

    python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

# Make the ``src/`` layout importable so the suite runs with only the standard
# library via ``python3 -m unittest discover -s tests`` (no install required).
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from tool_execution_log import ExecutionEntry, ToolExecutionLog, ToolStats  # noqa: E402


class RecordTests(unittest.TestCase):
    def test_record_ok(self):
        log = ToolExecutionLog()
        e = log.record("search", args={"q": "python"}, result={"hits": 3}, duration_ms=50.0)
        self.assertEqual(e.tool_name, "search")
        self.assertTrue(e.ok)
        self.assertEqual(e.duration_ms, 50.0)

    def test_record_error(self):
        log = ToolExecutionLog()
        e = log.record("fetch", error="Timeout", duration_ms=5000.0)
        self.assertFalse(e.ok)
        self.assertEqual(e.error, "Timeout")

    def test_record_returns_entry(self):
        log = ToolExecutionLog()
        e = log.record("tool")
        self.assertIsInstance(e, ExecutionEntry)

    def test_record_defaults(self):
        log = ToolExecutionLog()
        e = log.record("tool")
        self.assertEqual(e.args, {})
        self.assertEqual(e.tags, [])
        self.assertIsNone(e.result)
        self.assertIsNone(e.error)

    def test_entry_ids_are_unique(self):
        log = ToolExecutionLog()
        ids = {log.record("t").entry_id for _ in range(5)}
        self.assertEqual(len(ids), 5)


class QueryTests(unittest.TestCase):
    def test_by_tool(self):
        log = ToolExecutionLog()
        log.record("a")
        log.record("b")
        log.record("a")
        self.assertEqual(len(log.by_tool("a")), 2)
        self.assertEqual(len(log.by_tool("b")), 1)

    def test_by_tool_unknown(self):
        log = ToolExecutionLog()
        log.record("a")
        self.assertEqual(log.by_tool("missing"), [])

    def test_errors_all(self):
        log = ToolExecutionLog()
        log.record("a", error="boom")
        log.record("a")
        log.record("b", error="bang")
        self.assertEqual(len(log.errors()), 2)

    def test_errors_filtered_by_tool(self):
        log = ToolExecutionLog()
        log.record("a", error="boom")
        log.record("b", error="bang")
        self.assertEqual(len(log.errors("a")), 1)
        self.assertEqual(log.errors("a")[0].tool_name, "a")

    def test_since(self):
        log = ToolExecutionLog()
        t0 = time.time()
        log.record("old")
        # Manually backdate the first entry.
        log._entries[0].timestamp = t0 - 3600
        log.record("new")
        recent = log.since(t0 - 1)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].tool_name, "new")

    def test_by_tag(self):
        log = ToolExecutionLog()
        log.record("a", tags=["important"])
        log.record("b")
        log.record("c", tags=["important", "debug"])
        self.assertEqual(len(log.by_tag("important")), 2)
        self.assertEqual(len(log.by_tag("debug")), 1)


class StatsTests(unittest.TestCase):
    def test_stats(self):
        log = ToolExecutionLog()
        log.record("s", duration_ms=100.0)
        log.record("s", duration_ms=200.0, error="oops")
        s = log.stats("s")
        self.assertEqual(s.calls, 2)
        self.assertEqual(s.errors, 1)
        self.assertEqual(s.avg_ms, 150.0)
        self.assertEqual(s.min_ms, 100.0)
        self.assertEqual(s.max_ms, 200.0)
        self.assertEqual(s.error_rate, 0.5)

    def test_stats_no_calls(self):
        log = ToolExecutionLog()
        s = log.stats("nonexistent")
        self.assertEqual(s.calls, 0)
        self.assertEqual(s.avg_ms, 0.0)
        self.assertEqual(s.error_rate, 0.0)

    def test_stats_no_calls_min_ms_is_zero_in_dict(self):
        # min_ms defaults to inf; to_dict must surface 0.0 when there are no calls.
        log = ToolExecutionLog()
        d = log.stats("nope").to_dict()
        self.assertEqual(d["min_ms"], 0.0)

    def test_stats_all_tools(self):
        log = ToolExecutionLog()
        log.record("a", duration_ms=10.0)
        log.record("b", duration_ms=20.0)
        s = log.stats()
        self.assertEqual(s.calls, 2)
        self.assertEqual(s.tool_name, "_all_")

    def test_all_stats(self):
        log = ToolExecutionLog()
        log.record("a")
        log.record("b")
        stats = log.all_stats()
        self.assertIn("a", stats)
        self.assertIn("b", stats)
        self.assertIsInstance(stats["a"], ToolStats)

    def test_all_stats_sorted(self):
        log = ToolExecutionLog()
        log.record("z")
        log.record("a")
        log.record("m")
        self.assertEqual(list(log.all_stats().keys()), ["a", "m", "z"])

    def test_stats_to_dict(self):
        s = ToolStats(tool_name="x", calls=2, errors=1, total_ms=100.0, min_ms=40.0, max_ms=60.0)
        d = s.to_dict()
        self.assertEqual(d["calls"], 2)
        self.assertEqual(d["error_rate"], 0.5)
        self.assertEqual(d["avg_ms"], 50.0)


class ContainerTests(unittest.TestCase):
    def test_len(self):
        log = ToolExecutionLog()
        self.assertEqual(len(log), 0)
        log.record("x")
        self.assertEqual(len(log), 1)

    def test_clear(self):
        log = ToolExecutionLog()
        log.record("x")
        count = log.clear()
        self.assertEqual(count, 1)
        self.assertEqual(len(log), 0)


class SerializationTests(unittest.TestCase):
    def test_entry_to_dict(self):
        log = ToolExecutionLog()
        e = log.record("tool", args={"k": "v"}, result="ok", duration_ms=1.0)
        d = e.to_dict()
        self.assertEqual(d["tool_name"], "tool")
        self.assertEqual(d["args"], {"k": "v"})
        self.assertEqual(d["result"], "ok")
        self.assertIsNone(d["error"])

    def test_entry_to_json(self):
        log = ToolExecutionLog()
        e = log.record("tool")
        parsed = json.loads(e.to_json())
        self.assertEqual(parsed["tool_name"], "tool")

    def test_entry_from_dict(self):
        d = {
            "entry_id": "x-1",
            "tool_name": "x",
            "args": {"a": 1},
            "result": "ok",
            "error": None,
            "duration_ms": 5.0,
            "timestamp": 1000.0,
            "tags": ["t"],
        }
        e = ExecutionEntry.from_dict(d)
        self.assertEqual(e.entry_id, "x-1")
        self.assertEqual(e.tool_name, "x")
        self.assertTrue(e.ok)

    def test_entry_from_dict_defaults(self):
        # Only the required keys are present; the rest must fall back gracefully.
        e = ExecutionEntry.from_dict({"entry_id": "y-1", "tool_name": "y"})
        self.assertEqual(e.args, {})
        self.assertEqual(e.tags, [])
        self.assertEqual(e.duration_ms, 0.0)
        self.assertIsNone(e.error)

    def test_entry_round_trip(self):
        log = ToolExecutionLog()
        e = log.record("tool", args={"k": [1, 2]}, result={"n": 3}, tags=["a"], duration_ms=7.0)
        clone = ExecutionEntry.from_dict(json.loads(e.to_json()))
        self.assertEqual(clone.to_dict(), e.to_dict())


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.path = os.path.join(self._dir, "log.jsonl")

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_persistence(self):
        log1 = ToolExecutionLog(self.path)
        log1.record("search", args={"q": "py"}, result={"n": 1}, duration_ms=10.0)

        log2 = ToolExecutionLog(self.path)
        self.assertEqual(len(log2), 1)
        self.assertEqual(log2._entries[0].tool_name, "search")

    def test_persistence_creates_nested_dirs(self):
        nested = os.path.join(self._dir, "a", "b", "log.jsonl")
        log = ToolExecutionLog(nested)
        log.record("x")
        self.assertTrue(os.path.exists(nested))

    def test_counter_does_not_reuse_ids_after_reload(self):
        # Regression: before the fix, reloading reset the counter to 0 and the
        # next recorded entry collided with a persisted entry_id.
        log1 = ToolExecutionLog(self.path)
        log1.record("search", duration_ms=1.0)
        log1.record("search", duration_ms=2.0)

        log2 = ToolExecutionLog(self.path)
        new_entry = log2.record("search", duration_ms=3.0)
        ids = [e.entry_id for e in log2._entries]
        self.assertEqual(len(ids), len(set(ids)), "entry_ids must stay unique after reload")
        self.assertEqual(new_entry.entry_id, "search-3")

    def test_missing_file_is_empty(self):
        log = ToolExecutionLog(self.path)
        self.assertEqual(len(log), 0)

    def test_corrupt_line_is_skipped(self):
        with open(self.path, "w") as f:
            f.write("not json\n")
        # Loading must not raise even when the file is malformed.
        log = ToolExecutionLog(self.path)
        self.assertEqual(len(log), 0)


if __name__ == "__main__":
    unittest.main()
