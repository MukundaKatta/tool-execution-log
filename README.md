# tool-execution-log

Structured JSONL log of tool executions with per-tool latency and error stats.

`tool-execution-log` is a tiny, dependency-free Python library for recording how
the tools (functions, API calls, agent actions, ...) in your application behave
over time. Every call is captured as a structured entry — its arguments, result
or error, duration, timestamp, and tags — and the library computes per-tool
aggregates such as average latency and error rate. Entries can optionally be
persisted as newline-delimited JSON (JSONL) so the history survives restarts and
can be processed with any JSONL-aware tool.

It is well suited to instrumenting LLM/agent tool calls, profiling slow tools,
and surfacing flaky tools via their error rate.

## Features

- Record successes and failures with arguments, result/error, duration and tags.
- Query entries by tool, by tag, by error status, or by time window.
- Per-tool and overall aggregate stats: call count, error count, error rate,
  average / min / max latency.
- Optional JSONL persistence with automatic load-on-open and append-on-write.
- Thread-safe: all reads and writes are guarded by an internal lock.
- Pure standard library — no third-party runtime dependencies.

## Install

```
pip install tool-execution-log
```

Requires Python 3.9 or newer.

## Usage

```python
import time
from tool_execution_log import ToolExecutionLog

# Pass a path to persist as JSONL, or omit it for an in-memory log.
log = ToolExecutionLog("/tmp/tool-exec.jsonl")

# Record a successful execution.
log.record("search", args={"query": "python"}, result={"hits": 3}, duration_ms=120.5)

# Record a failure.
log.record("search", args={"query": "rust"}, error="Timeout", duration_ms=5000.0)

# Query the history.
entries = log.by_tool("search")          # all entries for "search"
errors = log.errors("search")            # only the failed ones
recent = log.since(time.time() - 3600)   # entries from the last hour

# Inspect aggregate stats.
stats = log.stats("search")
print(stats.calls, stats.avg_ms, stats.error_rate)

all_stats = log.all_stats()              # {tool_name: ToolStats}
```

### Timing a real call

`record` does not time anything for you — pass the measured duration in
milliseconds. A common pattern:

```python
import time
from tool_execution_log import ToolExecutionLog

log = ToolExecutionLog()


def run_tool(name, fn, **args):
    start = time.perf_counter()
    try:
        result = fn(**args)
    except Exception as exc:
        log.record(name, args=args, error=str(exc),
                   duration_ms=(time.perf_counter() - start) * 1000)
        raise
    log.record(name, args=args, result=result,
               duration_ms=(time.perf_counter() - start) * 1000)
    return result
```

## API

### `ToolExecutionLog(path=None)`

Append-only structured log of tool executions. When `path` is given, existing
entries are loaded on construction and every new entry is appended to the file
as JSONL; a leading `~` is expanded. When `path` is `None`, the log lives only
in memory.

| Method | Description |
| --- | --- |
| `record(tool_name, args=None, result=None, error=None, duration_ms=0.0, tags=None)` | Record a tool execution and return the created `ExecutionEntry`. |
| `by_tool(tool_name)` | List all entries for the given tool. |
| `errors(tool_name=None)` | List failed entries, optionally filtered to one tool. |
| `since(timestamp)` | List entries recorded at or after a Unix timestamp. |
| `by_tag(tag)` | List entries carrying the given tag. |
| `stats(tool_name=None)` | Aggregate `ToolStats` for a tool, or across all tools when `None`. |
| `all_stats()` | `dict` of `{tool_name: ToolStats}`, sorted by tool name. |
| `clear()` | Drop all in-memory entries and return how many were removed. |
| `len(log)` | Number of entries currently held in memory. |

### `ExecutionEntry`

Dataclass describing a single execution.

- Fields: `entry_id`, `tool_name`, `args`, `result`, `error`, `duration_ms`,
  `timestamp`, `tags`.
- `ok` — `True` when `error is None`.
- `to_dict()` / `to_json()` — serialize the entry.
- `ExecutionEntry.from_dict(d)` — rebuild an entry from a dict (missing optional
  keys fall back to defaults).

### `ToolStats`

Dataclass with aggregate statistics for a tool.

- Fields: `tool_name`, `calls`, `errors`, `total_ms`, `min_ms`, `max_ms`.
- `avg_ms` — mean duration (`0.0` when there are no calls).
- `error_rate` — fraction of calls that errored, in `[0.0, 1.0]`.
- `to_dict()` — summary dict including the derived fields.

## Development

Run the test suite with the standard library only — no extra dependencies:

```
python -m unittest discover -s tests
```

## License

MIT
