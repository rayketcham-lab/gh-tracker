"""Probe a self-hosted runner: listener/worker PIDs, log tail, current step."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.runners_config import RunnerTarget

PROBE_SCRIPT = r"""
set -u
DIR=__DIR__
SVC=__SVC__

svc_state=unknown
if [ -n "$SVC" ]; then
  svc_state=$(systemctl is-active "$SVC" 2>/dev/null || echo unknown)
fi

listener_pid=""; worker_pid=""
if command -v pgrep >/dev/null 2>&1; then
  listener_pid=$(pgrep -f "[R]unner\.Listener" 2>/dev/null | head -1)
  worker_pid=$(pgrep -f "[R]unner\.Worker" 2>/dev/null | head -1)
fi

proc_info() {
  local pid="$1"
  if [ -z "$pid" ] || [ ! -d "/proc/$pid" ]; then
    echo "null"; return
  fi
  read age cpu rss < <(ps -o etimes= -o %cpu= -o rss= -p "$pid" 2>/dev/null | awk '{print $1,$2,$3}')
  printf '{"pid":%s,"ageSec":%s,"cpu":%s,"rssKb":%s}' \
    "$pid" "${age:-0}" "${cpu:-0}" "${rss:-0}"
}

latest_worker_log=""
last_line=""
last_line_age=-1
if [ -d "$DIR/_diag" ]; then
  latest_worker_log=$(ls -1t "$DIR"/_diag/Worker_*.log 2>/dev/null | head -1)
  if [ -n "$latest_worker_log" ]; then
    last_line=$(tail -n 1 "$latest_worker_log" 2>/dev/null | tr -d '\r' | tr -d '\n')
    mtime=$(stat -c %Y "$latest_worker_log" 2>/dev/null || echo 0)
    now=$(date +%s)
    last_line_age=$(( now - mtime ))
  fi
fi

log_tail=""
if [ -n "$latest_worker_log" ]; then
  log_tail=$(tail -n 40 "$latest_worker_log" 2>/dev/null | base64 -w0 2>/dev/null || tail -n 40 "$latest_worker_log" 2>/dev/null | base64)
fi

last_line_b64=$(printf '%s' "$last_line" | base64 -w0 2>/dev/null || printf '%s' "$last_line" | base64)

cat <<EOF
{"svcState":"$svc_state","listener":$(proc_info "$listener_pid"),"worker":$(proc_info "$worker_pid"),"latestWorkerLog":"$latest_worker_log","lastLineB64":"$last_line_b64","lastLineAgeSec":$last_line_age,"logTailB64":"$log_tail"}
EOF
"""


_STEP_PATTERNS = [
    re.compile(r"Step:\s+(.+)$"),
    re.compile(r"Running step:\s+(.+)$"),
    re.compile(r"##\[group\](.+)$"),
    re.compile(r"Executing step:\s+(.+?)\s*$"),
]


@dataclass
class RunnerState:
    name: str
    kind: str
    host: str
    runner_dir: str
    service: str | None
    updated_at: str
    reachable: bool
    error: str | None
    svc_state: str
    listener: dict | None
    worker: dict | None
    latest_worker_log: str | None
    last_line: str
    last_line_age_sec: int
    current_step: str | None
    log_tail: str


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _build_script(runner: RunnerTarget) -> str:
    return (
        PROBE_SCRIPT
        .replace("__DIR__", _shell_quote(runner.runner_dir))
        .replace("__SVC__", _shell_quote(runner.service or ""))
    )


_spawn = asyncio.create_subprocess_exec


async def _run(cmd: list[str], timeout: float = 8.0) -> tuple[bool, str, str]:
    try:
        proc = await _spawn(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            return False, "", f"timed out after {timeout}s"
        if proc.returncode != 0:
            stderr = err.decode(errors="replace") or f"exit {proc.returncode}"
            return False, out.decode(errors="replace"), stderr
        return True, out.decode(errors="replace"), ""
    except FileNotFoundError as e:
        return False, "", str(e)


async def _run_local(script: str) -> tuple[bool, str, str]:
    return await _run(["bash", "-lc", script])


async def _run_ssh(host: str, script: str) -> tuple[bool, str, str]:
    args = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=10",
        host,
        script,
    ]
    return await _run(args)


def _parse_probe(stdout: str) -> dict | None:
    trimmed = stdout.strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(trimmed[start : end + 1])
    except json.JSONDecodeError:
        return None


def _decode_b64(b64: str | None) -> str:
    if not b64:
        return ""
    try:
        return base64.b64decode(b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_current_step(tail: str) -> str | None:
    if not tail:
        return None
    lines = [line for line in tail.splitlines() if line]
    for line in reversed(lines):
        for pattern in _STEP_PATTERNS:
            m = pattern.search(line)
            if m:
                return m.group(1).strip()
    return None


async def probe_runner(runner: RunnerTarget) -> dict:
    script = _build_script(runner)
    if runner.kind == "ssh":
        assert runner.ssh_host, "ssh runner needs ssh_host"
        ok, out, err = await _run_ssh(runner.ssh_host, script)
        host = runner.ssh_host
    else:
        ok, out, err = await _run_local(script)
        host = "local"

    now = datetime.now(UTC).isoformat(timespec="seconds")

    base = RunnerState(
        name=runner.name,
        kind=runner.kind,
        host=host,
        runner_dir=runner.runner_dir,
        service=runner.service,
        updated_at=now,
        reachable=ok,
        error=None if ok else (err or "unknown error").strip()[:500],
        svc_state="unknown",
        listener=None,
        worker=None,
        latest_worker_log=None,
        last_line="",
        last_line_age_sec=-1,
        current_step=None,
        log_tail="",
    )

    if not ok:
        return asdict(base)

    parsed = _parse_probe(out) or {}
    log_tail = _decode_b64(parsed.get("logTailB64"))
    base.svc_state = parsed.get("svcState") or "unknown"
    base.listener = parsed.get("listener") or None
    base.worker = parsed.get("worker") or None
    base.latest_worker_log = parsed.get("latestWorkerLog") or None
    base.last_line = _decode_b64(parsed.get("lastLineB64"))
    raw_age = parsed.get("lastLineAgeSec")
    base.last_line_age_sec = int(raw_age) if isinstance(raw_age, int | float) else -1
    base.log_tail = log_tail
    base.current_step = _extract_current_step(log_tail)
    return asdict(base)
