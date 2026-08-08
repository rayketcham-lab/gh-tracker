"""Tests verifying CI workflow YAML structure and correctness.

These tests parse the actual workflow files and assert the jobs,
matrix configurations, and steps we expect to see.
"""

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


@pytest.fixture
def ci_workflow():
    with open(WORKFLOW_DIR / "ci.yml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def codeql_workflow():
    with open(WORKFLOW_DIR / "codeql.yml") as f:
        return yaml.safe_load(f)


class TestCIWorkflowStructure:
    def test_triggers_on_push_and_pr(self, ci_workflow):
        triggers = ci_workflow.get("on") or ci_workflow.get(True, {})
        assert "push" in triggers
        assert "pull_request" in triggers

    def test_backend_job_exists(self, ci_workflow):
        assert "backend" in ci_workflow["jobs"]

    def test_backend_uses_python_matrix(self, ci_workflow):
        backend = ci_workflow["jobs"]["backend"]
        matrix = backend.get("strategy", {}).get("matrix", {})
        versions = matrix.get("python-version", [])
        assert "3.12" in versions
        assert "3.13" in versions

    def test_backend_runs_lint(self, ci_workflow):
        backend = ci_workflow["jobs"]["backend"]
        step_names = [s.get("name", "") for s in backend["steps"]]
        assert any("ruff" in n.lower() or "lint" in n.lower() for n in step_names)

    def test_backend_runs_tests(self, ci_workflow):
        backend = ci_workflow["jobs"]["backend"]
        step_names = [s.get("name", "") for s in backend["steps"]]
        assert any("pytest" in n.lower() or "test" in n.lower() for n in step_names)

    def test_backend_excludes_live_tests(self, ci_workflow):
        backend = ci_workflow["jobs"]["backend"]
        for step in backend["steps"]:
            run_cmd = step.get("run", "")
            if "pytest" in run_cmd:
                assert "test_live_collect" in run_cmd

    def test_frontend_job_exists(self, ci_workflow):
        assert "frontend" in ci_workflow["jobs"]

    def test_frontend_runs_lint(self, ci_workflow):
        frontend = ci_workflow["jobs"]["frontend"]
        step_names = [s.get("name", "") for s in frontend["steps"]]
        assert any("lint" in n.lower() for n in step_names)

    def test_frontend_runs_build(self, ci_workflow):
        frontend = ci_workflow["jobs"]["frontend"]
        step_names = [s.get("name", "") for s in frontend["steps"]]
        assert any("build" in n.lower() for n in step_names)

    def test_frontend_runs_tests(self, ci_workflow):
        frontend = ci_workflow["jobs"]["frontend"]
        step_names = [s.get("name", "") for s in frontend["steps"]]
        assert any("test" in n.lower() for n in step_names)

    def test_dependency_audit_job_exists(self, ci_workflow):
        assert "audit" in ci_workflow["jobs"]

    def test_audit_runs_pip_audit(self, ci_workflow):
        audit = ci_workflow["jobs"]["audit"]
        step_runs = [s.get("run", "") for s in audit["steps"]]
        assert any("pip-audit" in r for r in step_runs)

    def test_audit_runs_npm_audit(self, ci_workflow):
        audit = ci_workflow["jobs"]["audit"]
        step_runs = [s.get("run", "") for s in audit["steps"]]
        assert any("npm audit" in r for r in step_runs)


class TestCodeQLWorkflow:
    def test_codeql_workflow_exists(self, codeql_workflow):
        assert codeql_workflow is not None

    def test_codeql_runs_on_schedule(self, codeql_workflow):
        triggers = codeql_workflow.get("on") or codeql_workflow.get(True, {})
        assert "schedule" in triggers

    def test_codeql_analyzes_javascript(self, codeql_workflow):
        analyze_job = codeql_workflow["jobs"].get("analyze", {})
        matrix = analyze_job.get("strategy", {}).get("matrix", {})
        languages = matrix.get("language", [])
        assert "javascript-typescript" in languages

    def test_codeql_analyzes_python(self, codeql_workflow):
        analyze_job = codeql_workflow["jobs"].get("analyze", {})
        matrix = analyze_job.get("strategy", {}).get("matrix", {})
        languages = matrix.get("language", [])
        assert "python" in languages
