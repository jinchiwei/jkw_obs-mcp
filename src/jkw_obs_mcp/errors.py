"""Domain-specific errors raised by jkw_obs_mcp."""


class JkwObsMcpError(Exception):
    """Base class for all jkw_obs_mcp errors."""


class UnknownMachineError(JkwObsMcpError):
    """Raised when the current host doesn't match any machine in machines.toml."""

    def __init__(self, hostname: str, os_name: str) -> None:
        self.hostname = hostname
        self.os_name = os_name
        super().__init__(
            f"hostname {hostname!r} (os={os_name!r}) does not match any entry in "
            f"machines.toml. Add an alias or set machine.id explicitly in config.toml."
        )


class SandboxViolationError(JkwObsMcpError):
    """Raised when a write would land outside the allowed kb/<machine_id>/ root."""

    def __init__(self, attempted_path: str, allowed_root: str) -> None:
        self.attempted_path = attempted_path
        self.allowed_root = allowed_root
        super().__init__(
            f"refusing to write to {attempted_path!r}: outside allowed root {allowed_root!r}"
        )
