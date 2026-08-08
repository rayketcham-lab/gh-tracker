"""Self-hosted runner configuration for the live runner-pane feature."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunnerTarget:
    name: str
    kind: str  # "local" | "ssh"
    runner_dir: str
    service: str | None = None
    ssh_host: str | None = None


@dataclass(frozen=True)
class StuckRules:
    worker_age_minutes: float = 20.0
    log_silence_seconds: float = 90.0
    low_cpu_percent: float = 2.0


@dataclass(frozen=True)
class RunnersConfig:
    runners: list[RunnerTarget]
    rules: StuckRules
    poll_interval_ms: int = 2000


# Empty by default: runner targets describe the operator's own machines
# (hostnames, filesystem paths, systemd unit names), so they are configuration
# rather than code and must not be baked into the repository.
#
# Point GH_TRACKER_RUNNERS_CONFIG at a JSON file to enable the runner pane.
# `name` should match the GitHub-registered runner name exactly, so a future
# merge-with-GitHub-API step can key on it without translation.
#
#   {
#     "pollIntervalMs": 2000,
#     "stuck": {"workerAgeMinutes": 20, "logSilenceSeconds": 90, "lowCpuPercent": 2},
#     "runners": [
#       {
#         "name": "my-local-runner",
#         "kind": "local",
#         "runnerDir": "/opt/actions-runner",
#         "service": "actions.runner.<org>.<name>.service"
#       },
#       {
#         "name": "my-remote-runner",
#         "kind": "ssh",
#         "sshHost": "buildbox",
#         "runnerDir": "/home/<user>/actions-runner",
#         "service": "actions.runner.<org>.<name>.service"
#       }
#     ]
#   }
#
# With no config file the pane simply reports no runners.
DEFAULT_RUNNERS: list[RunnerTarget] = []


def _from_dict(d: dict) -> RunnersConfig:
    runners = [
        RunnerTarget(
            name=r["name"],
            kind=r["kind"],
            runner_dir=r["runnerDir"],
            service=r.get("service"),
            ssh_host=r.get("sshHost"),
        )
        for r in d.get("runners", [])
    ]
    stuck = d.get("stuck", {})
    rules = StuckRules(
        worker_age_minutes=float(stuck.get("workerAgeMinutes", 20)),
        log_silence_seconds=float(stuck.get("logSilenceSeconds", 90)),
        low_cpu_percent=float(stuck.get("lowCpuPercent", 2)),
    )
    return RunnersConfig(
        runners=runners or DEFAULT_RUNNERS,
        rules=rules,
        poll_interval_ms=int(d.get("pollIntervalMs", 2000)),
    )


def load_config() -> RunnersConfig:
    path = os.environ.get("GH_TRACKER_RUNNERS_CONFIG")
    if path and Path(path).is_file():
        try:
            return _from_dict(json.loads(Path(path).read_text()))
        except Exception:
            pass
    return RunnersConfig(runners=DEFAULT_RUNNERS, rules=StuckRules())
