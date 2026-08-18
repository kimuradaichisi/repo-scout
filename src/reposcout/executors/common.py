import hashlib
import subprocess
from pathlib import Path


def run_command(root: Path, command: list[str], timeout: int = 30) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        cwd=root,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
