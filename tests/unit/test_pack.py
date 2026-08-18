import hashlib
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from reposcout.models import SourceRange
from reposcout.pack import EvidencePackBuilder


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _add_source(root: Path, relative: str, line_count: int) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"line{n}" for n in range(1, line_count + 1)) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", relative], cwd=root, check=True)


def _repo(tmp_path: Path, **files: int) -> Path:
    _init_repo(tmp_path)
    for relative, line_count in files.items():
        _add_source(tmp_path, relative, line_count)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_single_range(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 60})

    pack = EvidencePackBuilder().build(
        root, [SourceRange(path="src/a.py", start_line=1, end_line=5)]
    )

    assert len(pack.sources) == 1
    assert pack.sources[0].start_line == 1
    assert pack.sources[0].end_line == 5


def test_duplicate_range_packs_once(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 60})
    requests = [
        SourceRange(path="src/a.py", start_line=10, end_line=20),
        SourceRange(path="src/a.py", start_line=10, end_line=20),
    ]

    pack = EvidencePackBuilder().build(root, requests)

    assert len(pack.sources) == 1


def test_overlap_merge(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 60})
    requests = [
        SourceRange(path="src/a.py", start_line=20, end_line=40),
        SourceRange(path="src/a.py", start_line=35, end_line=55),
    ]

    pack = EvidencePackBuilder().build(root, requests)

    assert len(pack.sources) == 1
    assert (pack.sources[0].start_line, pack.sources[0].end_line) == (20, 55)


def test_contiguous_merge(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 60})
    requests = [
        SourceRange(path="src/a.py", start_line=20, end_line=40),
        SourceRange(path="src/a.py", start_line=41, end_line=50),
    ]

    pack = EvidencePackBuilder().build(root, requests)

    assert len(pack.sources) == 1
    assert (pack.sources[0].start_line, pack.sources[0].end_line) == (20, 50)


def test_separate_ranges_stay_separate(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 60})
    requests = [
        SourceRange(path="src/a.py", start_line=1, end_line=5),
        SourceRange(path="src/a.py", start_line=20, end_line=25),
    ]

    pack = EvidencePackBuilder().build(root, requests)

    assert len(pack.sources) == 2
    assert [(s.start_line, s.end_line) for s in pack.sources] == [(1, 5), (20, 25)]


def test_separate_paths_stay_separate(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 10, "src/b.py": 10})
    requests = [
        SourceRange(path="src/b.py", start_line=1, end_line=3),
        SourceRange(path="src/a.py", start_line=1, end_line=3),
    ]

    pack = EvidencePackBuilder().build(root, requests)

    assert [s.path for s in pack.sources] == ["src/a.py", "src/b.py"]


def test_stable_ordering_regardless_of_request_order(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 10, "src/b.py": 10})
    forward = [
        SourceRange(path="src/a.py", start_line=1, end_line=3),
        SourceRange(path="src/b.py", start_line=1, end_line=3),
    ]
    reversed_requests = list(reversed(forward))

    pack_forward = EvidencePackBuilder().build(root, forward)
    pack_reversed = EvidencePackBuilder().build(root, reversed_requests)

    assert pack_forward.sources == pack_reversed.sources


def test_sha256_is_stable_across_calls(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 10})
    request = [SourceRange(path="src/a.py", start_line=1, end_line=5)]

    first = EvidencePackBuilder().build(root, request)
    second = EvidencePackBuilder().build(root, request)

    assert first.sources[0].sha256 == second.sources[0].sha256
    assert (
        first.sources[0].sha256
        == hashlib.sha256(first.sources[0].content.encode("utf-8")).hexdigest()
    )


def test_rejects_nonexistent_path(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 10})

    with pytest.raises(ValueError):
        EvidencePackBuilder().build(
            root, [SourceRange(path="src/missing.py", start_line=1, end_line=1)]
        )


def test_rejects_untracked_path(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 10})
    (root / "src/untracked.py").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError):
        EvidencePackBuilder().build(
            root, [SourceRange(path="src/untracked.py", start_line=1, end_line=1)]
        )


def test_rejects_start_line_below_one() -> None:
    with pytest.raises(ValidationError):
        SourceRange(path="src/a.py", start_line=0, end_line=1)


def test_rejects_end_line_before_start_line() -> None:
    with pytest.raises(ValidationError):
        SourceRange(path="src/a.py", start_line=5, end_line=1)


def test_content_matches_source_file(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 10})

    pack = EvidencePackBuilder().build(
        root, [SourceRange(path="src/a.py", start_line=2, end_line=4)]
    )

    assert pack.sources[0].content == "2:line2\n3:line3\n4:line4"


def test_metrics_are_correct(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"src/a.py": 60})
    requests = [
        SourceRange(path="src/a.py", start_line=20, end_line=40),  # 21 lines
        SourceRange(
            path="src/a.py", start_line=35, end_line=55
        ),  # 21 lines, overlaps -> merges to 20-55
    ]

    pack = EvidencePackBuilder().build(root, requests)
    metrics = pack.metrics

    assert metrics.requested_ranges == 2
    assert metrics.packed_ranges == 1
    assert metrics.unique_paths == 1
    assert metrics.packed_source_bytes == len(pack.sources[0].content.encode("utf-8"))
    assert metrics.pack_chars == len(pack.sources[0].content)
    assert metrics.requested_source_bytes > metrics.packed_source_bytes
    assert (
        metrics.duplicate_or_overlap_bytes_eliminated
        == metrics.requested_source_bytes - metrics.packed_source_bytes
    )
