"""
tool-execution-log: Structured JSONL log of tool executions with per-tool stats.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExecutionEntry:
    """A single recorded tool execution.

    Attributes:
        entry_id: Unique identifier of the form ``"{tool_name}-{n}"``.
        tool_name: Name of the tool that was executed.
        args: Arguments passed to the tool.
        result: Value returned by the tool (``None`` when the call errored).
        error: Error message if the call failed, otherwise ``None``.
        duration_ms: Wall-clock execution time in milliseconds.
        timestamp: Unix epoch time (seconds) when the entry was recorded.
        tags: Free-form labels attached to the entry.
    """

    entry_id: str
    tool_name: str
    args: dict[str, Any]
    result: Any
    error: Optional[str]
    duration_ms: float
    timestamp: float          # Unix epoch
    tags: list[str]

    @property
    def ok(self) -> bool:
        """``True`` when the execution completed without an error."""
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-``dict`` representation of the entry."""
        return {
            "entry_id": self.entry_id,
            "tool_name": self.tool_name,
            "args": self.args,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }

    def to_json(self) -> str:
        """Serialize the entry to a single-line JSON string."""
        return json.dumps(self.to_dict())

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ExecutionEntry":
        """Reconstruct an :class:`ExecutionEntry` from a ``dict``.

        Missing optional keys fall back to sensible defaults so that
        partially-formed records (e.g. from older log files) still load.
        """
        return ExecutionEntry(
            entry_id=d["entry_id"],
            tool_name=d["tool_name"],
            args=d.get("args", {}),
            result=d.get("result"),
            error=d.get("error"),
            duration_ms=d.get("duration_ms", 0.0),
            timestamp=d.get("timestamp", 0.0),
            tags=d.get("tags", []),
        )


@dataclass
class ToolStats:
    """Aggregate latency and error statistics for a tool.

    Attributes:
        tool_name: Name of the tool the stats describe (``"_all_"`` for the
            combined statistics across every tool).
        calls: Total number of recorded executions.
        errors: Number of executions that ended with an error.
        total_ms: Sum of all execution durations in milliseconds.
        min_ms: Fastest recorded execution in milliseconds.
        max_ms: Slowest recorded execution in milliseconds.
    """

    tool_name: str
    calls: int = 0
    errors: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        """Mean execution time in milliseconds (``0.0`` when no calls)."""
        return self.total_ms / self.calls if self.calls else 0.0

    @property
    def error_rate(self) -> float:
        """Fraction of calls that errored, in ``[0.0, 1.0]``."""
        return self.errors / self.calls if self.calls else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-``dict`` summary, including derived fields."""
        return {
            "tool_name": self.tool_name,
            "calls": self.calls,
            "errors": self.errors,
            "error_rate": self.error_rate,
            "avg_ms": self.avg_ms,
            "min_ms": self.min_ms if self.calls else 0.0,
            "max_ms": self.max_ms,
        }


class ToolExecutionLog:
    """
    Append-only structured log of tool executions.

    Usage::

        log = ToolExecutionLog("/tmp/tool-exec.jsonl")
        entry = log.record("search", args={"query": "python"}, result={...}, duration_ms=120)
        log.record("search", args={"query": "rust"}, error="Timeout", duration_ms=5000)

        entries = log.by_tool("search")
        stats   = log.stats("search")
        recent  = log.since(time.time() - 3600)
    """

    def __init__(self, path: Optional[str] = None) -> None:
        """Create a log.

        Args:
            path: Optional path to a JSONL file. When provided, every recorded
                entry is appended to the file, and any existing entries in the
                file are loaded into memory on construction. A leading ``~`` is
                expanded to the user's home directory. When ``None``, the log is
                kept purely in memory.
        """
        self._path = os.path.expanduser(path) if path else None
        self._lock = threading.Lock()
        self._entries: list[ExecutionEntry] = []
        self._counter = 0
        if self._path and os.path.exists(self._path):
            self._load()

    def _load(self) -> None:
        try:
            with open(self._path) as f:  # type: ignore[arg-type]
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(ExecutionEntry.from_dict(json.loads(line)))
        except (OSError, json.JSONDecodeError):
            pass
        # Advance the counter past any loaded entries so that new entries do
        # not receive ``entry_id`` values that collide with persisted ones.
        self._counter = len(self._entries)

    def _append(self, entry: ExecutionEntry) -> None:
        if self._path:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "a") as f:
                f.write(entry.to_json() + "\n")

    def record(
        self,
        tool_name: str,
        args: Optional[dict[str, Any]] = None,
        result: Any = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        tags: Optional[list[str]] = None,
    ) -> ExecutionEntry:
        """Record a tool execution. Returns the created entry."""
        with self._lock:
            self._counter += 1
            entry = ExecutionEntry(
                entry_id=f"{tool_name}-{self._counter}",
                tool_name=tool_name,
                args=args or {},
                result=result,
                error=error,
                duration_ms=duration_ms,
                timestamp=time.time(),
                tags=tags or [],
            )
            self._entries.append(entry)
            self._append(entry)
            return entry

    def by_tool(self, tool_name: str) -> list[ExecutionEntry]:
        """All entries for a given tool."""
        with self._lock:
            return [e for e in self._entries if e.tool_name == tool_name]

    def errors(self, tool_name: Optional[str] = None) -> list[ExecutionEntry]:
        """All error entries, optionally filtered by tool."""
        with self._lock:
            return [
                e for e in self._entries
                if not e.ok and (tool_name is None or e.tool_name == tool_name)
            ]

    def since(self, timestamp: float) -> list[ExecutionEntry]:
        """Entries recorded at or after the given Unix timestamp."""
        with self._lock:
            return [e for e in self._entries if e.timestamp >= timestamp]

    def by_tag(self, tag: str) -> list[ExecutionEntry]:
        """All entries carrying the given tag."""
        with self._lock:
            return [e for e in self._entries if tag in e.tags]

    def stats(self, tool_name: Optional[str] = None) -> ToolStats:
        """Aggregate stats for a tool (or all tools if None)."""
        label = tool_name or "_all_"
        s = ToolStats(tool_name=label)
        with self._lock:
            for e in self._entries:
                if tool_name is not None and e.tool_name != tool_name:
                    continue
                s.calls += 1
                s.total_ms += e.duration_ms
                s.min_ms = min(s.min_ms, e.duration_ms)
                s.max_ms = max(s.max_ms, e.duration_ms)
                if not e.ok:
                    s.errors += 1
        return s

    def all_stats(self) -> dict[str, ToolStats]:
        """Per-tool stats dict."""
        names: set[str] = set()
        with self._lock:
            names = {e.tool_name for e in self._entries}
        return {n: self.stats(n) for n in sorted(names)}

    def clear(self) -> int:
        """Remove all in-memory entries. Returns count cleared."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def __len__(self) -> int:
        """Number of entries currently held in memory."""
        with self._lock:
            return len(self._entries)


__all__ = ["ToolExecutionLog", "ExecutionEntry", "ToolStats"]
