"""CP7: Task Generalization — three investigation tasks fixed BEFORE running.

Each task targets a different subsystem than the InvestigationRunner task
used through CP0-CP6, and the three tasks target different subsystems from
each other. required evidence / coverage ground truth below was written by
reading the source once, before any B3.2 run against these tasks — it is not
adjusted after seeing results.

CP7-F adds a `planner_route` field. It is a fixed, hand-declared property of
the task, not something inferred at run time: CP7/CP7-D/CP7-E showed that
change-scope investigations need a planner that will climb from the change
target to its enclosing symbol and consumers, while symbol-impact and
behavior-localization investigations reached full coverage with the Sonnet
planner. Routing therefore belongs in the experiment definition, so a task's
planner is auditable from this file alone and no LLM classifier sits in the
measured path. Ground truth below is unchanged by CP7-F.
"""

# Route keys consumed by run_cp7f_task.py.
SONNET_PLANNER = "sonnet_planner"
MAIN_OWNED = "main_owned"

TASKS = [
    {
        "key": "symbol_impact",
        "label": "Symbol impact investigation",
        # Definition/reference lookup: CP7 reached coverage 1.0 with Sonnet.
        "planner_route": SONNET_PLANNER,
        "investigation_goal": "EvidenceWriter の変更影響範囲を調査する",
        "confirmation_points": [
            "定義箇所",
            "参照箇所",
            "関連テスト",
            "依存クラス・依存モジュール",
            "変更時に確認すべきファイル",
        ],
        # Ground truth (read from src/reposcout/evidence.py, runner.py,
        # tests/unit/test_evidence.py before running):
        #   EvidenceWriter は evidence.py で定義され、write_plan/write_result/
        #   write_pack の3メソッドを持つ。runner.py の InvestigationRunner が
        #   唯一の利用者(コンストラクタ引数、デフォルト生成)。
        #   models.py の InvestigationPlan/EvidenceResult/InvestigationQuery
        #   に依存。直接のテストは tests/unit/test_evidence.py のみ。
        "expected_files": ["evidence.py", "runner.py", "test_evidence.py"],
        "expected_symbols": ["write_plan", "write_result", "write_pack", "InvestigationRunner"],
        "expected_extended": ["InvestigationPlan", "EvidenceResult"],
    },
    {
        "key": "behavior_localization",
        "label": "Behavior localization investigation",
        # Locating where an existing behavior is implemented: CP7 reached
        # coverage 1.0 with Sonnet.
        "planner_route": SONNET_PLANNER,
        "investigation_goal": (
            "tool未指定、または対応するexecutorが存在しないqueryが、"
            "どこでどのように処理されるか(fallback挙動)を特定する"
        ),
        "confirmation_points": [
            "fallbackの判定ロジックがどこにあるか",
            "fallback先として呼び出される実装",
            "fallback実装が依存する外部プロセス・設定",
            "この挙動をカバーするテストの有無",
            "変更時に確認すべきファイル",
        ],
        # Ground truth (read from src/reposcout/runner.py,
        # src/reposcout/ornith/client.py before running):
        #   QueryRunner.execute (runner.py) が tool と self._executors 辞書を
        #   照合し、一致しなければ self._ornith.execute (OrnithWorker,
        #   ornith/client.py) にフォールバックする。OrnithWorker は
        #   subprocess で外部プロセス(opencode)を起動し、
        #   ornith/prompt.py の SYSTEM_PROMPT を使う。
        #   QueryRunner のディスパッチ挙動を直接カバーするテストは
        #   tests/unit/ 配下に存在しない。
        "expected_files": ["runner.py", "client.py"],
        "expected_symbols": ["QueryRunner", "OrnithWorker", "_executors"],
        "expected_extended": ["SYSTEM_PROMPT", "subprocess"],
    },
    {
        "key": "change_scope",
        "label": "Change-scope investigation",
        # Impact that depends on indirect consumers: Sonnet stopped at direct
        # references (CP7, coverage 0.667). CP7-E's main-owned Opus planning
        # reached 1.0 without a Change-Scope Policy in the prompt.
        "planner_route": MAIN_OWNED,
        "investigation_goal": (
            "rgクエリに付与するbounded context行数(CONTEXT_LINES)と、"
            "選択的contextのしきい値(NARROW_PATH_THRESHOLD)を変更する場合に、"
            "確認・変更が必要なファイルと箇所を特定する。実装はしない。"
        ),
        "confirmation_points": [
            "定数が定義されている箇所",
            "その定数を使用している箇所",
            "この定数の変更をカバーするテストの有無",
            "変更時に確認すべきファイル",
        ],
        # Ground truth (read from src/reposcout/executors/ripgrep.py,
        # runner.py before running):
        #   CONTEXT_LINES / NARROW_PATH_THRESHOLD は
        #   RipgrepExecutor(ripgrep.py)のクラス変数として定義され、
        #   execute() 内でのみ参照される。RipgrepExecutor の唯一の
        #   利用者は runner.py の QueryRunner (self._executors辞書経由)。
        #   ripgrep.py 単体をカバーする専用テストは
        #   tests/unit/ 配下に存在しない。
        "expected_files": ["ripgrep.py"],
        "expected_symbols": ["CONTEXT_LINES", "NARROW_PATH_THRESHOLD", "RipgrepExecutor"],
        "expected_extended": ["runner.py", "QueryRunner"],
        # CP7.1: apply the generic Change-Scope Plan Policy (prompts.py,
        # CHANGE_SCOPE_POLICY) to this task only. Unchanged from CP7 above.
        "plan_policy": "change_scope",
    },
]
