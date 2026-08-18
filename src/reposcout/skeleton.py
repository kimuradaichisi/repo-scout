from reposcout.scope import FileScopeMode, RepositoryFileScope


class RepositorySkeleton(RepositoryFileScope):
    """The Repository Skeleton: RepositoryFileScope, defaulting to tracked-only.

    Kept as its own name/class -- rather than calling RepositoryFileScope
    directly -- because it is the public surface `reposcout skeleton` and
    EvidencePackBuilder's default validation source were already built on;
    the tracked-only default must not change.
    """

    def __init__(self, mode: FileScopeMode = FileScopeMode.TRACKED_ONLY) -> None:
        super().__init__(mode)
