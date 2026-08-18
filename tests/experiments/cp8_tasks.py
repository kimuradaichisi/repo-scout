"""CP8: the three implementation tasks, with acceptance criteria fixed here.

Written by reading the source once, before any CP8 run, and not adjusted
afterwards -- same discipline as cp7_tasks.py. Config A and Config B are
graded against exactly this text, so neither config can be credited for
meeting a bar that moved.

The three rise in the kind of judgement they need, not merely in size:

    T1  a test for behaviour that is already decided and already read
    T2  a test for a subsystem no CP7 task ever touched, so the behaviour has
        to be established from the code before it can be asserted
    T3  a real source change whose blast radius is a decision -- the consumer
        in runner.py may or may not need to change, and saying which is the
        work

`forbidden_paths` is a prefix list: any changed path starting with one of them
is a scope violation, whichever config produced it.
"""

from typing import Any

GATE_CRITERIA = (
    "`uv run pytest -q` passes, with no previously passing test now failing",
    "`uv run ruff check .` reports no findings",
    "`uv run ruff format --check .` reports no reformatting needed",
    "`uv run mypy src` reports no issues",
    "every changed file stays within CLAUDE.md's 300 line / 30 line / 5 parameter limits",
)

TASKS: list[dict[str, Any]] = [
    {
        "key": "t1_ripgrep_tests",
        "label": "T1 — RipgrepExecutor unit tests",
        "goal": (
            "src/reposcout/executors/ripgrep.py の RipgrepExecutor に対する "
            "unit test を tests/unit/test_ripgrep.py として追加する。"
            "本番コード(src/ 配下)は変更しない。"
        ),
        "expected_changed_files": ["tests/unit/test_ripgrep.py"],
        "forbidden_paths": ["src/"],
        "acceptance_criteria": (
            "tests/unit/test_ripgrep.py が新規に存在し、RipgrepExecutor を対象とする",
            "paths が 1〜3 件のとき rg コマンドに --context 5 が付与されることを検証する",
            "paths が空のとき --context が付与されないことを検証する",
            "paths が 4 件以上のとき --context が付与されないことを検証する",
            "rg の終了コード 1(マッチなし)が status=PASS になることを検証する",
            "rg の終了コード 2 以上が status=ERROR となり stderr が error に入ることを検証する",
            "src/ 配下のファイルが一切変更されていない",
            *GATE_CRITERIA,
        ),
    },
    {
        "key": "t2_git_log_tests",
        "label": "T2 — GitLogExecutor unit tests",
        "goal": (
            "src/reposcout/executors/git_log.py の GitLogExecutor に対する "
            "unit test を tests/unit/test_git_log.py として追加する。"
            "本番コード(src/ 配下)は変更しない。"
        ),
        "expected_changed_files": ["tests/unit/test_git_log.py"],
        "forbidden_paths": ["src/"],
        "acceptance_criteria": (
            "tests/unit/test_git_log.py が新規に存在し、GitLogExecutor を対象とする",
            "実行されるコマンドが git log --oneline -20 を基底とすることを検証する",
            "query.git_args が基底コマンドの後ろに追加されることを検証する",
            "終了コード 0 のとき status=PASS となり stdout が strip されて "
            "evidence に入ることを検証する",
            "終了コード非 0 のとき status=ERROR となり stderr が error に入ることを検証する",
            "src/ 配下のファイルが一切変更されていない",
            *GATE_CRITERIA,
        ),
    },
    {
        "key": "t3_injectable_context",
        "label": "T3 — injectable rg context settings",
        "goal": (
            "RipgrepExecutor のクラス変数 CONTEXT_LINES / NARROW_PATH_THRESHOLD を "
            "コンストラクタ引数として注入可能にする。既定値は現行値(5 / 3)を維持し、"
            "既定構築時の挙動を一切変えない。唯一の利用者である "
            "src/reposcout/runner.py の QueryRunner を変更するかどうかは判断して決める。"
        ),
        "expected_changed_files": [
            "src/reposcout/executors/ripgrep.py",
            "tests/unit/test_ripgrep_injection.py",
        ],
        "forbidden_paths": [
            "src/reposcout/evidence.py",
            "src/reposcout/cli.py",
            "src/reposcout/models.py",
            "src/reposcout/ornith/",
        ],
        "acceptance_criteria": (
            "RipgrepExecutor がコンテキスト行数としきい値をコンストラクタで受け取れる",
            "引数を省略した場合の既定値が 5 と 3 であり、現行の挙動と完全に一致する",
            "execute() がクラス変数ではなくインスタンスの値を参照する",
            "注入した値が rg コマンドに反映されることを検証するテストが存在する",
            "既定構築時の rg コマンドが変更前と同一であることを検証するテストが存在する",
            "QueryRunner を変更した場合、その判断理由が DECISIONS に記録されている",
            "QueryRunner を変更しない場合も既定の RepoScout 挙動が変わらない",
            *GATE_CRITERIA,
        ),
    },
]


def get_task(key: str) -> dict[str, Any]:
    for task in TASKS:
        if task["key"] == key:
            return task
    raise KeyError(f"unknown CP8 task: {key!r}")


def render_acceptance_criteria(task: dict[str, Any]) -> str:
    return "\n".join(f"- {item}" for item in task["acceptance_criteria"])


def scope_violations(changed_paths: list[str], task: dict[str, Any]) -> list[str]:
    """Changed paths the task forbids touching."""
    forbidden: list[str] = task["forbidden_paths"]
    return [path for path in changed_paths if any(path.startswith(bad) for bad in forbidden)]
