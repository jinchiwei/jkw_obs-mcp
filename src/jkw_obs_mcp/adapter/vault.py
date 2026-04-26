"""Filesystem adapter for the Obsidian vault.

Encapsulates ALL vault filesystem ops. Sandbox enforcement lives here:
writes go only to <vault_root>/kb/<machine_id>/. Reads are unrestricted
within <vault_root>.
"""

from __future__ import annotations

from pathlib import Path

from jkw_obs_mcp.errors import SandboxViolationError


class VaultAdapter:
    """Reads and writes scoped to one vault + one machine."""

    def __init__(self, vault_root: Path, machine_id: str) -> None:
        self.vault_root = vault_root.resolve()
        self.machine_id = machine_id
        self.kb_root = (self.vault_root / "kb" / machine_id).resolve()

    def read_note(self, rel_path: str) -> str:
        """Read a note at vault-relative path. Returns text content."""
        target = self._resolve_safe(rel_path, allowed_root=self.vault_root)
        return target.read_text(encoding="utf-8")

    def list_notes(self, subdir: str = "") -> list[Path]:
        """List all .md files under vault_root/<subdir>/, recursively.

        Returns vault-relative paths (e.g. "Admin/Saiyan.md").
        """
        if subdir:
            base = self._resolve_safe(subdir, allowed_root=self.vault_root)
        else:
            base = self.vault_root

        return sorted(
            p.relative_to(self.vault_root)
            for p in base.rglob("*.md")
            if p.is_file()
        )

    def write_kb_note(self, filename: str, content: str, subdir: str = "ad-hoc") -> Path:
        """Write a note into <vault_root>/kb/<machine_id>/<subdir>/<filename>.

        Rejects path traversal and writes outside kb/<machine_id>/.
        Returns the absolute path written.
        """
        # Resolve subdir relative to kb_root, refusing escape.
        target_dir = self._resolve_safe(subdir, allowed_root=self.kb_root)
        # Resolve filename relative to target_dir, refusing escape.
        target = self._resolve_safe(filename, allowed_root=target_dir)
        # Ensure final path is still under kb_root (defense in depth).
        try:
            target.relative_to(self.kb_root)
        except ValueError:
            raise SandboxViolationError(
                attempted_path=str(target), allowed_root=str(self.kb_root)
            ) from None

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def _resolve_safe(self, rel_path: str, *, allowed_root: Path) -> Path:
        """Resolve rel_path against allowed_root, refusing path traversal."""
        candidate = (allowed_root / rel_path).resolve()
        try:
            candidate.relative_to(allowed_root)
        except ValueError:
            raise SandboxViolationError(
                attempted_path=str(candidate), allowed_root=str(allowed_root)
            ) from None
        return candidate
