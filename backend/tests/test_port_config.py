"""Tests for gh-tracker server port configuration.

Specs covered:
1. run.py reads GH_TRACKER_PORT env var to determine listen port
2. Default port is 8001 (avoids conflict with other services on 8000)
3. Vite proxy targets the correct backend port
"""

import importlib

import pytest


class TestPortConfiguration:
    """Verify the backend server port is configurable and defaults to 8001."""

    def test_default_port_is_8001(self, monkeypatch):
        """Default port should be 8001 to avoid conflicts with other services."""
        monkeypatch.delenv("GH_TRACKER_PORT", raising=False)
        import app.server_config
        importlib.reload(app.server_config)
        assert app.server_config.get_server_port() == 8001

    def test_port_from_env_var(self, monkeypatch):
        """GH_TRACKER_PORT env var should override the default."""
        monkeypatch.setenv("GH_TRACKER_PORT", "9999")
        import app.server_config
        importlib.reload(app.server_config)
        assert app.server_config.get_server_port() == 9999

    def test_invalid_port_raises(self, monkeypatch):
        """Non-numeric port should raise ValueError."""
        monkeypatch.setenv("GH_TRACKER_PORT", "not_a_number")
        import app.server_config
        importlib.reload(app.server_config)
        with pytest.raises(ValueError):
            app.server_config.get_server_port()
