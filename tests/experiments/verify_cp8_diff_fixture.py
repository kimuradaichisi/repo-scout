"""Fixture-only verification of cp8_diff.py. No model calls, no CP8 snapshot.

Each check builds its own throwaway git repository under a temp directory,
exercises diff_against_fixture_commit against it, and asserts the result.
This is what the first Step 1 batch's diff_against_fixture_commit would have
failed on check 2 alone: a brand-new untracked file, which is what every
CP8 task actually produces.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cp8_diff import diff_against_fixture_commit  # noqa: E402

FAILURES: list[str] = []


def _git(args: list[str], repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)


def _init_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="cp8-diff-fixture-"))
    _git(["init", "-q"], repo)
    _git(
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", "init"],
        repo,
    )
    return repo


def _write(repo: Path, relative: str, body: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _commit_tracked(repo: Path, relative: str, body: str) -> None:
    _write(repo, relative, body)
    _git(["add", relative], repo)
    _git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed"], repo)


def _check(number: int, title: str, condition: bool, detail: str) -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  {number}. [{mark}] {title}")
    print(f"        {detail}")
    if not condition:
        FAILURES.append(title)


def check_1_tracked_modify() -> None:
    repo = _init_repo()
    _commit_tracked(repo, "a.txt", "original\n")
    _write(repo, "a.txt", "modified\n")
    diff_text, changed = diff_against_fixture_commit(repo)
    _check(
        1,
        "tracked file modify is detected",
        changed == ["a.txt"] and "modified" in diff_text and "original" in diff_text,
        f"changed_paths={changed}",
    )


def check_2_untracked_new_file() -> None:
    repo = _init_repo()
    _write(repo, "tests/unit/test_new.py", "def test_x():\n    assert True\n")
    diff_text, changed = diff_against_fixture_commit(repo)
    _check(
        2,
        "untracked new file is detected",
        changed == ["tests/unit/test_new.py"] and "def test_x" in diff_text,
        f"changed_paths={changed}",
    )


def check_3_tracked_and_untracked_together() -> None:
    repo = _init_repo()
    _commit_tracked(repo, "src/thing.py", "VALUE = 1\n")
    _write(repo, "src/thing.py", "VALUE = 2\n")
    _write(repo, "tests/unit/test_thing.py", "def test_value():\n    pass\n")
    diff_text, changed = diff_against_fixture_commit(repo)
    _check(
        3,
        "tracked modify + untracked new file both detected",
        set(changed) == {"src/thing.py", "tests/unit/test_thing.py"}
        and "VALUE = 2" in diff_text
        and "def test_value" in diff_text,
        f"changed_paths={changed}",
    )


def check_4_deleted_file() -> None:
    repo = _init_repo()
    _commit_tracked(repo, "gone.txt", "will be deleted\n")
    (repo / "gone.txt").unlink()
    diff_text, changed = diff_against_fixture_commit(repo)
    _check(
        4,
        "deleted tracked file is detected",
        changed == ["gone.txt"]
        and "will be deleted" in diff_text
        and "-will be deleted" in diff_text,
        f"changed_paths={changed}",
    )


def check_5_unchanged_tree() -> None:
    repo = _init_repo()
    _commit_tracked(repo, "steady.txt", "unchanged\n")
    diff_text, changed = diff_against_fixture_commit(repo)
    _check(
        5,
        "unchanged tree yields empty result",
        changed == [] and diff_text == "",
        f"changed_paths={changed!r} diff_text={diff_text!r}",
    )


def check_6_untracked_content_in_diff() -> None:
    repo = _init_repo()
    _write(repo, "note.md", "line one\nline two\nline three\n")
    diff_text, _ = diff_against_fixture_commit(repo)
    lines_present = all(f"+{line}" in diff_text for line in ("line one", "line two", "line three"))
    _check(
        6,
        "untracked file's content appears in the diff text",
        lines_present,
        f"all three lines present in diff_text: {lines_present}",
    )


def check_7_index_unchanged() -> None:
    repo = _init_repo()
    _commit_tracked(repo, "b.txt", "before\n")
    _write(repo, "b.txt", "after\n")
    _write(repo, "c.txt", "new\n")
    before = _git(["status", "--porcelain"], repo).stdout
    diff_against_fixture_commit(repo)
    after = _git(["status", "--porcelain"], repo).stdout
    _check(
        7,
        "git index is unchanged before/after",
        before == after,
        f"before={before!r} after={after!r}",
    )


def main() -> int:
    print("--- cp8_diff.py fixture verification (no model calls) ---")
    check_1_tracked_modify()
    check_2_untracked_new_file()
    check_3_tracked_and_untracked_together()
    check_4_deleted_file()
    check_5_unchanged_tree()
    check_6_untracked_content_in_diff()
    check_7_index_unchanged()
    print(f"\nall_checks_passed: {not FAILURES}")
    if FAILURES:
        print("failed:", FAILURES)
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
