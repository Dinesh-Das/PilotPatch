# Sample repository

Run tests with `python -m pytest -q` (pytest is supplied by PilotPatch's dev install).

Try: `copilot-agent --project . "Add subtract(left, right) with tests and run them."`
Approve the command shown, or configure an exact `unit` test command in your operator YAML.

For a repair exercise, manually change `return left + right` to `return left - right`,
then ask PilotPatch to fix the failing tests. This fixture ships with passing tests.
