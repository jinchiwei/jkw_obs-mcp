"""Tests for installer.machines_check step."""

from __future__ import annotations

import tomllib
from pathlib import Path

from jkw_obs_mcp.installer.machines_check import (
    append_hostname,
    is_hostname_registered,
)


def _write_machines_toml(path: Path, content: str) -> None:
    path.write_text(content)


def test_returns_true_when_hostname_is_a_machine_id(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    assert is_hostname_registered(machines, hostname="dreamingmachine") is True


def test_returns_true_when_hostname_in_aliases(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[scs]
hostname_aliases = ["callosum"]
os = "linux"
""")
    assert is_hostname_registered(machines, hostname="callosum") is True


def test_returns_false_when_hostname_not_present(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    assert is_hostname_registered(machines, hostname="randomhost") is False


def test_returns_false_when_machines_toml_missing(tmp_path):
    machines = tmp_path / "missing.toml"
    assert is_hostname_registered(machines, hostname="anything") is False


def test_append_hostname_writes_correct_block(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    append_hostname(
        machines,
        machine_id="newcluster",
        os_type="linux",
        hostname="newcluster.example.edu",
    )

    parsed = tomllib.loads(machines.read_text())
    assert "newcluster" in parsed
    assert parsed["newcluster"]["os"] == "linux"
    assert "newcluster.example.edu" in parsed["newcluster"]["hostname_aliases"]


def test_append_hostname_then_is_registered(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    append_hostname(
        machines,
        machine_id="newcluster",
        os_type="linux",
        hostname="newcluster.example.edu",
    )

    assert is_hostname_registered(machines, hostname="newcluster.example.edu") is True
    assert is_hostname_registered(machines, hostname="newcluster") is True
