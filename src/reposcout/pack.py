from pathlib import Path

from reposcout.executors.common import content_hash
from reposcout.models import EvidencePack, PackedSource, PackMetrics, SourceRange
from reposcout.scope import RepositoryFileScope


def _group_by_path(requests: list[SourceRange]) -> dict[str, list[tuple[int, int]]]:
    grouped: dict[str, list[tuple[int, int]]] = {}
    for item in requests:
        grouped.setdefault(item.path, []).append((item.start_line, item.end_line))
    return grouped


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    # Two ranges merge when they overlap OR sit back-to-back with no gap
    # (next start <= previous end + 1) -- that covers both "duplicate /
    # overlap" and "contiguous" from the same rule.
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _slice_range(lines: list[str], start: int, end: int) -> str:
    selected = lines[start - 1 : end]
    numbered = (f"{number}:{text}" for number, text in enumerate(selected, start=start))
    return "\n".join(numbered)


def _pack_range(path: str, lines: list[str], start: int, end: int) -> PackedSource:
    content = _slice_range(lines, start, end)
    return PackedSource(
        path=path,
        start_line=start,
        end_line=end,
        content=content,
        sha256=content_hash(content),
    )


class EvidencePackBuilder:
    """Pack First: merge/dedup requested source ranges before Strong Model sees them.

    No summarization, ranking, or path inference happens here -- only
    deterministic range normalization and content retrieval. Nonexistent or
    untracked paths fail closed rather than being silently corrected.
    """

    def __init__(self, scope: RepositoryFileScope | None = None) -> None:
        self._scope = scope or RepositoryFileScope()

    def build(self, root: Path, requests: list[SourceRange]) -> EvidencePack:
        by_path = _group_by_path(requests)
        lines_by_path = {path: self._read_lines(root, path) for path in by_path}
        sources = self._pack_sources(by_path, lines_by_path)
        metrics = self._metrics(requests, sources, by_path, lines_by_path)
        return EvidencePack(sources=sources, metrics=metrics)

    def _read_lines(self, root: Path, path: str) -> list[str]:
        if not self._scope.contains(root, path):
            raise ValueError(f"not in scope: {path}")
        return (root / path).read_text(encoding="utf-8", errors="replace").splitlines()

    def _pack_sources(
        self,
        by_path: dict[str, list[tuple[int, int]]],
        lines_by_path: dict[str, list[str]],
    ) -> list[PackedSource]:
        sources: list[PackedSource] = []
        for path in sorted(by_path):
            for start, end in _merge_ranges(by_path[path]):
                sources.append(_pack_range(path, lines_by_path[path], start, end))
        return sources

    def _metrics(
        self,
        requests: list[SourceRange],
        sources: list[PackedSource],
        by_path: dict[str, list[tuple[int, int]]],
        lines_by_path: dict[str, list[str]],
    ) -> PackMetrics:
        requested_bytes = self._requested_bytes(requests, lines_by_path)
        packed_bytes = sum(len(item.content.encode("utf-8")) for item in sources)
        return PackMetrics(
            requested_ranges=len(requests),
            packed_ranges=len(sources),
            requested_source_bytes=requested_bytes,
            packed_source_bytes=packed_bytes,
            duplicate_or_overlap_bytes_eliminated=requested_bytes - packed_bytes,
            unique_paths=len(by_path),
            pack_chars=sum(len(item.content) for item in sources),
        )

    def _requested_bytes(
        self, requests: list[SourceRange], lines_by_path: dict[str, list[str]]
    ) -> int:
        total = 0
        for item in requests:
            content = _slice_range(lines_by_path[item.path], item.start_line, item.end_line)
            total += len(content.encode("utf-8"))
        return total
