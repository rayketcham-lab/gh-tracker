"""Meta-checks on CI configuration itself.

These exist because the suite was once green while asserting nothing: the
frontend test step ran `vitest --passWithNoTests` against zero committed test
files, and the npm audit gate had been raised from 'high' to 'critical' so an
existing high-severity ReDoS would stop failing the build.

Guarding the config in a normal pytest run means the next attempt to loosen it
breaks the build instead of passing silently. No server, DB or fixtures needed.

Originally contributed in PR #38.
"""

import re
from pathlib import Path


def _workflow(name: str) -> Path:
    """Locate a workflow file relative to this test (works from any cwd)."""
    return Path(__file__).parent.parent.parent / ".github" / "workflows" / name


def test_ci_yml_exists_and_is_not_empty() -> None:
    """Sanity guard for the meta-checks themselves."""
    ci_yml = _workflow("ci.yml")
    assert ci_yml.exists(), f"ci.yml not found at {ci_yml}"
    assert ci_yml.stat().st_size > 0, "ci.yml is empty"


def test_production_dependencies_audited_at_high_or_stricter() -> None:
    """Shipped dependencies must be gated at 'high' or stricter.

    'critical' alone is not enough: it lets every high-severity advisory
    through. The production audit is the one users are exposed to.
    """
    content = _workflow("ci.yml").read_text()
    pattern = r"npm audit[^\n]*--omit=dev[^\n]*--audit-level=(high|moderate|low)"
    assert re.search(pattern, content), (
        "ci.yml must audit production dependencies at --audit-level=high or "
        "stricter, with --omit=dev. Do not weaken this to 'critical' to make a "
        "high-severity finding stop failing the build — fix or document it."
    )


def test_dev_dependencies_still_have_a_critical_floor() -> None:
    """Dev tooling is not shipped, but a critical there is a build compromise."""
    content = _workflow("ci.yml").read_text()
    pattern = r"npm audit(?![^\n]*--omit=dev)[^\n]*--audit-level=(critical|high|moderate|low)"
    assert re.search(pattern, content), (
        "ci.yml must keep an audit step covering dev dependencies. Removing it "
        "would hide a compromised build toolchain."
    )


def test_frontend_test_step_does_not_pass_with_no_tests() -> None:
    """`--passWithNoTests` on the real test step reports success against nothing."""
    content = _workflow("ci.yml").read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("run:") and "npm test" in stripped:
            assert "--passWithNoTests" not in stripped, (
                "The frontend test step must not use --passWithNoTests: it "
                f"reports success with zero test files. Offending line: {stripped}"
            )


def test_frontend_has_a_test_file_guard() -> None:
    """CI must fail if every frontend test file is deleted."""
    content = _workflow("ci.yml").read_text()
    assert "-name '*.test.*'" in content or '-name "*.test.*"' in content, (
        "ci.yml must keep the step that fails when frontend/src contains no "
        "test files, so zero-coverage runs cannot silently return."
    )


def test_workflows_declare_permissions() -> None:
    """Least privilege: workflows must set an explicit permissions block."""
    for name in ("ci.yml", "codeql.yml"):
        content = _workflow(name).read_text()
        assert re.search(r"^permissions:", content, re.MULTILINE), (
            f"{name} must declare an explicit permissions block "
            "rather than inheriting the default token scope."
        )


def test_workflow_actions_are_sha_pinned() -> None:
    """The repository sets sha_pinning_required; tag refs fail at startup."""
    tag_ref = re.compile(r"uses:\s*\S+@(v\d+(\.\d+)*|main|master)\s*(#.*)?$")
    for name in ("ci.yml", "codeql.yml"):
        for i, line in enumerate(_workflow(name).read_text().splitlines(), 1):
            assert not tag_ref.search(line.strip()), (
                f"{name}:{i} pins an action by tag. This repository enforces "
                f"sha_pinning_required, so the run fails at startup: {line.strip()}"
            )
