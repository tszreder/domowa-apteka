"""PostToolUse hook: lint a just-edited Python file with ruff.

Reads the tool-call payload Claude Code sends on stdin, runs `ruff check`
against the edited file, and on failure exits 2 so Claude sees ruff's
output as feedback and can fix it before ending its turn.
"""

import json
import os
import subprocess
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py"):
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    result = subprocess.run(
        ["uv", "run", "ruff", "check", file_path],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
