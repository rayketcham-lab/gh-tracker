"""Stuck-runner heuristic. Flag when worker is long-lived AND (log silent OR low CPU)."""

from __future__ import annotations

from app.runners_config import StuckRules


def _worker_status(state: dict) -> str:
    if not state.get("reachable"):
        return "unreachable"
    svc = state.get("svc_state") or "unknown"
    if svc not in ("active", "unknown"):
        return svc
    listener = state.get("listener")
    worker = state.get("worker")
    if listener and not worker:
        return "idle"
    if not listener and not worker:
        return "offline"
    return "unknown"


def evaluate_stuck(state: dict, rules: StuckRules) -> dict:
    worker = state.get("worker")
    if not worker:
        return {"flagged": False, "reasons": [], "status": _worker_status(state)}

    age_sec = float(worker.get("ageSec") or 0)
    age_min = age_sec / 60.0
    cpu_raw = worker.get("cpu")
    cpu = float(cpu_raw) if isinstance(cpu_raw, int | float) else None
    silence = int(state.get("last_line_age_sec") or -1)

    reasons: list[str] = []
    if age_min >= rules.worker_age_minutes:
        reasons.append(
            f"worker alive for {age_min:.1f}m (threshold {rules.worker_age_minutes:.0f}m)"
        )
    if silence >= 0 and silence >= rules.log_silence_seconds:
        reasons.append(
            f"log silent for {silence}s (threshold {rules.log_silence_seconds:.0f}s)"
        )
    if cpu is not None and cpu < rules.low_cpu_percent and age_min >= 2:
        reasons.append(
            f"cpu {cpu}% < {rules.low_cpu_percent:.0f}% for {age_min:.1f}m"
        )

    flagged = age_min >= rules.worker_age_minutes or (
        age_min >= 2
        and (
            (silence >= 0 and silence >= rules.log_silence_seconds)
            or (cpu is not None and cpu < rules.low_cpu_percent)
        )
    )
    return {"flagged": flagged, "reasons": reasons, "status": "busy"}
