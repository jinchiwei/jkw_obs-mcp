import pytest

from jkw_obs_mcp.errors import (
    UnknownMachineError,
    SandboxViolationError,
)


def test_unknown_machine_error_carries_hostname_and_os():
    err = UnknownMachineError(hostname="strange-host", os_name="linux")
    assert err.hostname == "strange-host"
    assert err.os_name == "linux"
    assert "strange-host" in str(err)
    assert "linux" in str(err)


def test_sandbox_violation_error_carries_attempted_path():
    err = SandboxViolationError(attempted_path="/tmp/escape", allowed_root="/vault/kb/mac")
    assert err.attempted_path == "/tmp/escape"
    assert err.allowed_root == "/vault/kb/mac"
    assert "/tmp/escape" in str(err)
