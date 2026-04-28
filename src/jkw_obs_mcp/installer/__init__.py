"""Platform-aware installer for jkw-obs-mcp.

`jkw-obs-mcp-setup` is the entry point. It runs shared setup steps unconditionally
and Mac-only steps (launchd, Gmail OAuth) only on Darwin.
"""
