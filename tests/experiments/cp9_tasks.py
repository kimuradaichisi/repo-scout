"""CP9 task family: one fixed decision, applied to a variable number of sites.

CP8's T1/T2/T3 rose in the *kind* of judgement they needed and stayed at
essentially one execution volume, which is why CP8 could not see a
volume effect at all. CP9 inverts that: the design decision is stated in
identical words at all three sizes and is declared to apply repository-wide,
while only the list of sites it is implemented at changes. That is what makes
S/M/L "the same problem, more of it" rather than three different problems.

Everything here is fixed before any run and is not adjusted afterwards. In
particular the volume vector (V1..V5) is declared here, never derived from
what a model happened to produce: deriving size from changed LoC after the
fact would let the axis be redrawn around the result.

Scope is measured against `allowed_paths`, not `forbidden_paths`. A forbidden
prefix list shrinks as the task grows -- six prefixes at S, two at L -- so it
carried most of its power where the least work happened and almost none where
the most did, and CP9 compares across sizes. An allowlist means the same thing
at every size: a Small run that "helpfully" converts every executor, and a run
that leaves a scratch file behind, are both visible as the same kind of
violation. `forbidden_paths` is kept, reported, and no longer primary.
"""

from typing import Any

# Stated identically at every size, and deliberately scoped to the whole
# repository: the judgement is meant to cost the same whether one site or five
# are implemented afterwards. Only the SCOPE block that follows it varies.
DECISION_STATEMENT = """\
RepoScout の evidence には「その evidence を得るのにどれだけ時間がかかったか」が\
記録されていない。実行時間を evidence として残せるようにしたい。

まず、実行時間を**ドメインモデル上でどう表現するか**を決めること。これは設計判断であり、\
以下の4点を自分で決める必要がある:

  1. ドメインモデル上の表現
     (EvidenceResult に持たせるか / 別のモデルを作るか / ドメインモデルには置かないか)
  2. 計測の責務をどこに置くか
     (各 executor が自分で計測 / 共通ヘルパが計測 / runner が計測)
  3. 既存の構築箇所との互換性をどう保つか
     (既定値や省略可能フィールドにするか / 必須にして全構築箇所を直すか)
  4. この表現をどう波及させるか
     (全 executor に一律 / 列挙された対象のみに適用し残りは後続作業とする)

この判断は**リポジトリ全体に適用される前提**で行うこと。CLAUDE.md の依存方向\
(Domain → Application → Infrastructure)と 300 行 / 30 行 / 5 引数の制約に従うこと。"""

SCOPE_STATEMENT = """\
ただし**今回実装するのは以下に列挙した対象のみ**とする。列挙外のファイルは今回のスコープ外\
であり、変更してはならない(後続作業として残すこと)。

対象:
{targets}"""

GATE_CRITERIA = (
    "`uv run pytest -q` passes, with no previously passing test now failing",
    "`uv run ruff check .` reports no findings",
    "`uv run ruff format --check .` reports no reformatting needed",
    "`uv run mypy src` reports no issues",
    "every changed file stays within CLAUDE.md's 300 line / 30 line / 5 parameter limits",
)

# Never in scope at any size: these are the paths that would turn the task
# into a different design problem rather than a larger one.
ALWAYS_FORBIDDEN = ("src/reposcout/cli.py", "src/reposcout/runner.py")

TASKS: list[dict[str, Any]] = [
    {
        "key": "s_duration_ripgrep",
        "label": "S — duration on the domain model, ripgrep only",
        "size": "S",
        "decision_count": 1,
        "volume": {"v1": 3, "v2": 2, "v3": 1, "v4": 3, "v5": 2},
        "targets": (
            "src/reposcout/models.py",
            "src/reposcout/executors/ripgrep.py",
            "tests/unit/test_ripgrep_duration.py",
        ),
        "expected_changed_files": [
            "src/reposcout/models.py",
            "src/reposcout/executors/ripgrep.py",
            "tests/unit/test_ripgrep_duration.py",
        ],
        "forbidden_paths": [
            "src/reposcout/executors/git_log.py",
            "src/reposcout/executors/read_file.py",
            "src/reposcout/ornith/",
            "src/reposcout/evidence.py",
            *ALWAYS_FORBIDDEN,
        ],
        "outcome_criteria": (
            "RipgrepExecutor.execute() の結果から、その実行に要した時間が取得できる",
            "実行時間を記録しない既存の構築箇所が壊れず、既存テストがすべて通る",
            "既定構築時の rg コマンドと status/evidence/error の挙動が変更前と同一である",
        ),
        "contract_criteria": (
            "src/reposcout/models.py が変更されている",
            "src/reposcout/executors/ripgrep.py が変更されている",
            "tests/unit/test_ripgrep_duration.py が新規に存在する",
            "DECISION RECORD の4項目がすべて記載されている",
            "スコープ外(git_log / read_file / ornith / evidence / cli / runner)が変更されていない",
        ),
    },
    {
        "key": "m_duration_two_executors",
        "label": "M — same decision, ripgrep + git_log + evidence rendering",
        "size": "M",
        "decision_count": 1,
        "volume": {"v1": 6, "v2": 4, "v3": 2, "v4": 6, "v5": 4},
        "targets": (
            "src/reposcout/models.py",
            "src/reposcout/executors/ripgrep.py",
            "src/reposcout/executors/git_log.py",
            "src/reposcout/evidence.py",
            "tests/unit/test_ripgrep_duration.py",
            "tests/unit/test_git_log_duration.py",
        ),
        "expected_changed_files": [
            "src/reposcout/models.py",
            "src/reposcout/executors/ripgrep.py",
            "src/reposcout/executors/git_log.py",
            "src/reposcout/evidence.py",
            "tests/unit/test_ripgrep_duration.py",
            "tests/unit/test_git_log_duration.py",
        ],
        "forbidden_paths": [
            "src/reposcout/executors/read_file.py",
            "src/reposcout/ornith/",
            *ALWAYS_FORBIDDEN,
        ],
        "outcome_criteria": (
            "RipgrepExecutor.execute() の結果から、その実行に要した時間が取得できる",
            "GitLogExecutor.execute() の結果から、その実行に要した時間が取得できる",
            "evidence.md に実行時間が出力される",
            "実行時間を記録しない既存の構築箇所が壊れず、既存テストがすべて通る",
            "既定構築時の rg / git log コマンドと status/evidence/error の挙動が変更前と同一である",
            "実行時間の表現が2つの executor で同一の方式になっている",
        ),
        "contract_criteria": (
            "src/reposcout/models.py が変更されている",
            "src/reposcout/executors/ripgrep.py が変更されている",
            "src/reposcout/executors/git_log.py が変更されている",
            "src/reposcout/evidence.py が変更されている",
            "tests/unit/test_ripgrep_duration.py が新規に存在する",
            "tests/unit/test_git_log_duration.py が新規に存在する",
            "DECISION RECORD の4項目がすべて記載されている",
            "スコープ外(read_file / ornith / cli / runner)が変更されていない",
        ),
    },
    {
        "key": "l_duration_all_executors",
        "label": "L — same decision, all four executors + evidence rendering",
        "size": "L",
        "decision_count": 1,
        "volume": {"v1": 11, "v2": 6, "v3": 5, "v4": 11, "v5": 7},
        "targets": (
            "src/reposcout/models.py",
            "src/reposcout/executors/ripgrep.py",
            "src/reposcout/executors/git_log.py",
            "src/reposcout/executors/read_file.py",
            "src/reposcout/ornith/client.py",
            "src/reposcout/evidence.py",
            "tests/unit/test_ripgrep_duration.py",
            "tests/unit/test_git_log_duration.py",
            "tests/unit/test_read_file_duration.py",
            "tests/unit/test_ornith_duration.py",
            "tests/unit/test_evidence_duration.py",
        ),
        "expected_changed_files": [
            "src/reposcout/models.py",
            "src/reposcout/executors/ripgrep.py",
            "src/reposcout/executors/git_log.py",
            "src/reposcout/executors/read_file.py",
            "src/reposcout/ornith/client.py",
            "src/reposcout/evidence.py",
            "tests/unit/test_ripgrep_duration.py",
            "tests/unit/test_git_log_duration.py",
            "tests/unit/test_read_file_duration.py",
            "tests/unit/test_ornith_duration.py",
            "tests/unit/test_evidence_duration.py",
        ],
        "forbidden_paths": list(ALWAYS_FORBIDDEN),
        "outcome_criteria": (
            "RipgrepExecutor.execute() の結果から、その実行に要した時間が取得できる",
            "GitLogExecutor.execute() の結果から、その実行に要した時間が取得できる",
            "FileReadExecutor.execute() の結果から、その実行に要した時間が取得できる",
            "OrnithWorker.execute() の結果から、その実行に要した時間が取得できる",
            "エラー経路(status=ERROR)でも実行時間が記録される",
            "evidence.md に実行時間が出力される",
            "実行時間を記録しない既存の構築箇所が壊れず、既存テストがすべて通る",
            "既定構築時の各 executor の挙動が変更前と同一である",
            "実行時間の表現が4つの executor すべてで同一の方式になっている",
            "計測の責務が DECISION RECORD で宣言した場所に一貫して置かれている",
            "evidence.md の出力形式が既存セクション構造を壊していない",
        ),
        "contract_criteria": (
            "src/reposcout/models.py が変更されている",
            "src/reposcout/executors/ripgrep.py が変更されている",
            "src/reposcout/executors/git_log.py が変更されている",
            "src/reposcout/executors/read_file.py が変更されている",
            "src/reposcout/ornith/client.py が変更されている",
            "src/reposcout/evidence.py が変更されている",
            "tests/unit/test_ripgrep_duration.py が新規に存在する",
            "tests/unit/test_git_log_duration.py が新規に存在する",
            "tests/unit/test_read_file_duration.py が新規に存在する",
            "tests/unit/test_ornith_duration.py が新規に存在する",
            "tests/unit/test_evidence_duration.py が新規に存在する",
            "DECISION RECORD の4項目がすべて記載されている",
            "スコープ外(cli / runner)が変更されていない",
        ),
    },
]


# The primary scope metric is changed_paths - allowed_paths, and allowed_paths
# is exactly the declared targets: a task's targets are the complete list of
# repository files it is entitled to leave changed. Fixed at import, before any
# run, and asserted against `targets` by the Step 0 checks so the two cannot
# drift apart. forbidden_paths is kept as a secondary, reported-only signal --
# it was the first Step 0.5's primary metric and lost almost all of its power
# at L, where only two prefixes are out of scope.
for _task in TASKS:
    _task["allowed_paths"] = list(_task["targets"])


def get_task(key: str) -> dict[str, Any]:
    for task in TASKS:
        if task["key"] == key:
            return task
    raise KeyError(f"unknown CP9 task: {key!r}")


def get_size(size: str) -> dict[str, Any]:
    for task in TASKS:
        if task["size"] == size:
            return task
    raise KeyError(f"unknown CP9 size: {size!r}")


def render_goal(task: dict[str, Any]) -> str:
    """Decision text first, identical at every size; scope list second."""
    targets = "\n".join(f"  - {path}" for path in task["targets"])
    return f"{DECISION_STATEMENT}\n\n{SCOPE_STATEMENT.format(targets=targets)}"


def all_criteria(task: dict[str, Any]) -> tuple[str, ...]:
    return (*task["outcome_criteria"], *task["contract_criteria"], *GATE_CRITERIA)


def render_acceptance_criteria(task: dict[str, Any]) -> str:
    return "\n".join(f"- {item}" for item in all_criteria(task))


def scope_violations(changed_paths: list[str], task: dict[str, Any]) -> list[str]:
    forbidden: list[str] = task["forbidden_paths"]
    return [path for path in changed_paths if any(path.startswith(bad) for bad in forbidden)]
