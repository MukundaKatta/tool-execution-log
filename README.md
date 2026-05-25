# tool-execution-log

Structured JSONL log of tool executions with per-tool latency and error stats.

## Install

```
pip install tool-execution-log
```

## Usage

```python
from tool_execution_log import ToolExecutionLog

log = ToolExecutionLog("/tmp/tool-exec.jsonl")

entry = log.record("search", args={"query": "python"}, result={...}, duration_ms=120.5)
log.record("search", args={"query": "rust"}, error="Timeout", duration_ms=5000.0)

entries = log.by_tool("search")
errors  = log.errors("search")
recent  = log.since(time.time() - 3600)

stats = log.stats("search")
print(stats.calls, stats.avg_ms, stats.error_rate)

all_stats = log.all_stats()   # {tool_name: ToolStats}
```
