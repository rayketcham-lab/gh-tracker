"""Meta-check: CI configuration must not relax the npm audit gate.

Reciprocal guard that prevents the audit-level silently being raised from
'high' to 'critical' (the fake-green pattern removed in commit fix/ci-legit).
Runs as a normal pytest unit test — no server, no DB, no fixtures needed.
"""

from pathlib import Path


def _ci_yml_path() -> Path:
    """Locate ci.yml relative to this test file (works from any cwd)."""
    return Path(__file__).parent.parent.parent / ".github" / "workflows" / "ci.yml"


def test_npm_audit_gate_not_relaxed_to_critical() -> None:
    """ci.yml must not contain 'npm audit --audit-level=critical'.

    Using --audit-level=critical silently lets HIGH severity vulnerabilities
    pass undetected. The gate must stay at 'high' or stricter.
    """
    ci_yml = _ci_yml_path()
    assert ci_yml.exists(), f"ci.yml not found at {ci_yml}"

    content = ci_yml.read_text()
    bad_pattern = "npm audit --audit-level=critical"
    assert bad_pattern not in content, (
        f"Found '{bad_pattern}' in {ci_yml}. "
        "The npm audit gate must stay at --audit-level=high or stricter. "
        "Do not raise it to 'critical' to dodge HIGH severity findings."
    )


def test_ci_yml_exists_and_is_not_empty() -> None:
    """ci.yml must exist and contain content (sanity guard for the meta-check itself)."""
    ci_yml = _ci_yml_path()
    assert ci_yml.exists(), f"ci.yml not found at {ci_yml}"
    assert ci_yml.stat().st_size > 0, "ci.yml is empty"
