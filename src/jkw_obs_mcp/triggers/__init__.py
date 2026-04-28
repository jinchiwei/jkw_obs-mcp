"""launchd / cron entry points for time-based MCP-driven actions.

`daily_review_runner.main()` is invoked by the launchd LaunchAgent every
5 minutes (StartInterval=300). It exits 0 silently if today's daily review
already exists, fires generate_daily_review if not.
"""
