"""Tests for runner-target configuration resolution.

Runner targets describe the operator's own machines — hostnames, filesystem
paths, systemd unit names — so they are configuration rather than code and are
not committed. The loader therefore has to find them reliably, and degrade to
"no runners" rather than crashing when it cannot.
"""

import json

import pytest

from app import runners_config
from app.runners_config import RunnerTarget, load_config


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("GH_TRACKER_RUNNERS_CONFIG", raising=False)


def _write(path, runners, **top):
    payload = {"runners": runners, **top}
    path.write_text(json.dumps(payload))
    return path


SAMPLE = [{
    "name": "box-a",
    "kind": "ssh",
    "sshHost": "buildbox",
    "runnerDir": "/home/someone/actions-runner",
    "service": "actions.runner.org.box-a.service",
}]


class TestNoConfiguration:
    def test_ships_with_no_runners(self, monkeypatch, tmp_path):
        """The repository must not carry anyone's runner topology."""
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", tmp_path / "absent.json")
        assert load_config().runners == []

    def test_default_runners_constant_is_empty(self):
        assert runners_config.DEFAULT_RUNNERS == []


class TestDefaultPath:
    def test_loads_runners_json_beside_the_repo(self, monkeypatch, tmp_path):
        """A native deploy only has to drop the file — no env var, no unit edit."""
        cfg_file = _write(tmp_path / "runners.json", SAMPLE, pollIntervalMs=1500)
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", cfg_file)

        cfg = load_config()

        assert [r.name for r in cfg.runners] == ["box-a"]
        assert cfg.runners[0].ssh_host == "buildbox"
        assert cfg.poll_interval_ms == 1500

    def test_env_var_takes_precedence(self, monkeypatch, tmp_path):
        default_file = _write(tmp_path / "runners.json", [dict(SAMPLE[0], name="from-default")])
        env_file = _write(tmp_path / "override.json", [dict(SAMPLE[0], name="from-env")])
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", default_file)
        monkeypatch.setenv("GH_TRACKER_RUNNERS_CONFIG", str(env_file))

        assert [r.name for r in load_config().runners] == ["from-env"]

    def test_falls_back_when_env_path_is_missing(self, monkeypatch, tmp_path):
        """A stale env var must not mask a perfectly good default file."""
        default_file = _write(tmp_path / "runners.json", SAMPLE)
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", default_file)
        monkeypatch.setenv("GH_TRACKER_RUNNERS_CONFIG", str(tmp_path / "nope.json"))

        assert [r.name for r in load_config().runners] == ["box-a"]


class TestMalformedConfig:
    def test_invalid_json_degrades_to_no_runners(self, monkeypatch, tmp_path):
        """A broken runner pane must not take the analytics API down with it."""
        bad = tmp_path / "runners.json"
        bad.write_text("{ this is not json")
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", bad)

        assert load_config().runners == []

    def test_missing_required_key_degrades_to_no_runners(self, monkeypatch, tmp_path):
        bad = _write(tmp_path / "runners.json", [{"name": "x", "kind": "local"}])  # no runnerDir
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", bad)

        assert load_config().runners == []


class TestStuckRules:
    def test_thresholds_are_read_from_file(self, monkeypatch, tmp_path):
        cfg_file = _write(
            tmp_path / "runners.json", SAMPLE,
            stuck={"workerAgeMinutes": 5, "logSilenceSeconds": 15, "lowCpuPercent": 1},
        )
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", cfg_file)

        rules = load_config().rules
        assert (rules.worker_age_minutes, rules.log_silence_seconds, rules.low_cpu_percent) == (
            5.0, 15.0, 1.0,
        )

    def test_thresholds_have_defaults(self, monkeypatch, tmp_path):
        cfg_file = _write(tmp_path / "runners.json", SAMPLE)
        monkeypatch.setattr(runners_config, "DEFAULT_CONFIG_PATH", cfg_file)

        rules = load_config().rules
        assert (rules.worker_age_minutes, rules.log_silence_seconds, rules.low_cpu_percent) == (
            20.0, 90.0, 2.0,
        )


class TestRunnerTarget:
    def test_is_immutable(self):
        """Targets are shared across concurrent probes; they must not be mutated."""
        target = RunnerTarget(name="a", kind="local", runner_dir="/tmp")
        with pytest.raises(Exception):
            target.name = "b"
