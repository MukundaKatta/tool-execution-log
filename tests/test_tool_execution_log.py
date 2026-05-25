import time
import pytest
from tool_execution_log import ToolExecutionLog, ExecutionEntry, ToolStats


def test_record_ok():
    log = ToolExecutionLog()
    e = log.record("search", args={"q": "python"}, result={"hits": 3}, duration_ms=50.0)
    assert e.tool_name == "search"
    assert e.ok
    assert e.duration_ms == 50.0


def test_record_error():
    log = ToolExecutionLog()
    e = log.record("fetch", error="Timeout", duration_ms=5000.0)
    assert not e.ok
    assert e.error == "Timeout"


def test_record_returns_entry():
    log = ToolExecutionLog()
    e = log.record("tool")
    assert isinstance(e, ExecutionEntry)


def test_by_tool():
    log = ToolExecutionLog()
    log.record("a")
    log.record("b")
    log.record("a")
    assert len(log.by_tool("a")) == 2
    assert len(log.by_tool("b")) == 1


def test_errors_all():
    log = ToolExecutionLog()
    log.record("a", error="boom")
    log.record("a")
    log.record("b", error="bang")
    assert len(log.errors()) == 2


def test_errors_filtered_by_tool():
    log = ToolExecutionLog()
    log.record("a", error="boom")
    log.record("b", error="bang")
    assert len(log.errors("a")) == 1
    assert log.errors("a")[0].tool_name == "a"


def test_since():
    log = ToolExecutionLog()
    t0 = time.time()
    log.record("old")
    # Manually backdate the first entry
    log._entries[0].timestamp = t0 - 3600
    log.record("new")
    recent = log.since(t0 - 1)
    assert len(recent) == 1
    assert recent[0].tool_name == "new"


def test_by_tag():
    log = ToolExecutionLog()
    log.record("a", tags=["important"])
    log.record("b")
    log.record("c", tags=["important", "debug"])
    tagged = log.by_tag("important")
    assert len(tagged) == 2


def test_stats():
    log = ToolExecutionLog()
    log.record("s", duration_ms=100.0)
    log.record("s", duration_ms=200.0, error="oops")
    s = log.stats("s")
    assert s.calls == 2
    assert s.errors == 1
    assert s.avg_ms == 150.0
    assert s.min_ms == 100.0
    assert s.max_ms == 200.0
    assert s.error_rate == 0.5


def test_stats_no_calls():
    log = ToolExecutionLog()
    s = log.stats("nonexistent")
    assert s.calls == 0
    assert s.avg_ms == 0.0


def test_stats_all_tools():
    log = ToolExecutionLog()
    log.record("a", duration_ms=10.0)
    log.record("b", duration_ms=20.0)
    s = log.stats()
    assert s.calls == 2


def test_all_stats():
    log = ToolExecutionLog()
    log.record("a")
    log.record("b")
    stats = log.all_stats()
    assert "a" in stats
    assert "b" in stats


def test_len():
    log = ToolExecutionLog()
    assert len(log) == 0
    log.record("x")
    assert len(log) == 1


def test_clear():
    log = ToolExecutionLog()
    log.record("x")
    count = log.clear()
    assert count == 1
    assert len(log) == 0


def test_entry_to_dict():
    log = ToolExecutionLog()
    e = log.record("tool", args={"k": "v"}, result="ok", duration_ms=1.0)
    d = e.to_dict()
    assert d["tool_name"] == "tool"
    assert d["args"] == {"k": "v"}
    assert d["result"] == "ok"
    assert d["error"] is None


def test_entry_to_json():
    log = ToolExecutionLog()
    e = log.record("tool")
    j = e.to_json()
    import json
    parsed = json.loads(j)
    assert parsed["tool_name"] == "tool"


def test_entry_from_dict():
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
    assert e.entry_id == "x-1"
    assert e.tool_name == "x"


def test_stats_to_dict():
    s = ToolStats(tool_name="x", calls=2, errors=1, total_ms=100.0, min_ms=40.0, max_ms=60.0)
    d = s.to_dict()
    assert d["calls"] == 2
    assert d["error_rate"] == 0.5


def test_persistence(tmp_path):
    path = str(tmp_path / "log.jsonl")
    log1 = ToolExecutionLog(path)
    log1.record("search", args={"q": "py"}, result={"n": 1}, duration_ms=10.0)

    log2 = ToolExecutionLog(path)
    assert len(log2) == 1
    assert log2._entries[0].tool_name == "search"
