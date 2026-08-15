"""Prompts shared by the Claude Code / RepoScout comparison experiment."""

TARGET_SYMBOL = "InvestigationRunner"

# --- Pattern A: Claude Code alone -------------------------------------------

BASELINE_PROMPT = """\
InvestigationRunner の変更影響範囲を調査してください。

確認対象:
- 定義箇所
- 参照箇所
- 関連テスト
- 依存クラス
- 変更時に確認すべきファイル

実装はしないでください。
"""

# --- Pattern B: Claude Code + RepoScout -------------------------------------

PLAN_PROMPT = """\
InvestigationRunner の変更影響範囲を調査するための
RepoScout Investigation Planを生成してください。

自分では grep/read を実行しないでください。

利用可能なtool:
- rg
- read
- git_log

YAMLのみ出力してください。

スキーマ:
goal: <調査目的>
queries:
  - id: Q1
    tool: rg            # rg | read | git_log のいずれかを必ず指定する
    pattern: <検索文字列>
    paths: [<検索対象パス>]
  - id: Q2
    tool: read
    file: <ファイルパス>
    start_line: <開始行>
    end_line: <終了行>
  - id: Q3
    tool: git_log
    git_args: [<git log に渡す引数>]
"""

ANALYSIS_PROMPT_TEMPLATE = """\
このEvidenceを使って変更影響範囲を分析してください。
不足している場合のみ追加調査してください。

調査対象: InvestigationRunner の変更影響範囲

確認対象:
- 定義箇所
- 参照箇所
- 関連テスト
- 依存クラス
- 変更時に確認すべきファイル

実装はしないでください。

--- EVIDENCE START ---
{evidence}
--- EVIDENCE END ---
"""

# --- Pattern B2: Claude Code + RepoScout + Repository Files skeleton --------
#
# B2 tests one hypothesis only: does telling Claude which file paths actually
# exist, before it writes the plan, stop it from inventing paths and thereby
# reduce the fallback re-exploration seen in B1? No new RepoScout analysis
# code is involved — Repository Files below comes from a plain
# `git ls-files src tests/unit` against the snapshot.

PLAN_PROMPT_WITH_SKELETON = """\
InvestigationRunner の変更影響範囲を調査するための
RepoScout Investigation Planを生成してください。

自分では grep/read を実行しないでください。

利用可能なtool:
- rg
- read
- git_log

Repository Files:
{repository_files}

Plan生成ルール:
- 存在しないfile pathを推測しない
- read は Repository Files に存在するpathだけに対して行う
- symbolの所在が不明な場合は、pathを推測せず最初に rg を使う
- git_log も実在確認済みpathだけに使う
- 独立した検索は可能な限りbatchでPlanに含める

YAMLのみ出力してください。

スキーマ:
goal: <調査目的>
queries:
  - id: Q1
    tool: rg            # rg | read | git_log のいずれかを必ず指定する
    pattern: <検索文字列>
    paths: [<検索対象パス>]
  - id: Q2
    tool: read
    file: <ファイルパス>
    start_line: <開始行>
    end_line: <終了行>
  - id: Q3
    tool: git_log
    git_args: [<git log に渡す引数>]
"""

ANALYSIS_PROMPT_TEMPLATE_B2 = """\
このEvidenceを使って変更影響範囲を分析してください。
不足している場合のみ追加調査してください。

調査対象: InvestigationRunner の変更影響範囲

確認対象:
- 定義箇所
- 参照箇所
- 関連テスト
- 依存クラス
- 変更時に確認すべきファイル

分析ルール:
- RepoScout Evidenceが十分ならClaude側で同じ検索を繰り返さない
- 最終的なbehavior/design判断に必要なsourceだけClaudeが直接読む

実装はしないでください。

--- EVIDENCE START ---
{evidence}
--- EVIDENCE END ---
"""

# --- Pattern B3: Main(Opus) / Explorer(Sonnet) split, RepoScout unchanged ---
#
# B3 tests whether splitting exploration off the expensive model reduces what
# Main has to hold and reason over, without losing B2's quality. Main never
# sees a transcript — only the Brief it wrote going out, and the Evidence
# Pack coming back. Explorer runs B2's plan -> RepoScout -> evidence flow
# under Sonnet instead of Opus; RepoScout itself is untouched.

REPOSITORY_FILES_PLACEHOLDER = "<REPOSITORY_FILES>"

MAIN_BRIEF_PROMPT = """\
あなたはMain Agent(Opus)です。これから Sonnet Explorer Subagent に
Repository探索を委任します。Explorerには会話履歴を一切渡しません。
あなたがこれから出力する Investigation Brief だけが、Explorerに渡る
唯一の情報になります。

調査目的: InvestigationRunner の変更影響範囲を調査する

確認したい観点:
- 定義箇所
- 参照箇所
- 関連テスト
- 依存クラス
- 変更時に確認すべきファイル

以下の5セクションを、この見出しのまま・この順序で出力してください。
見出し以外の文章やコードフェンスは付けないでください。
REPOSITORY FILES セクションの本文には "<<<PLACEHOLDER>>>" という1行だけを
書いてください（実際のファイル一覧は後で機械的に差し込まれます）。

TASK
<Explorerが実行すべき調査タスクを1〜2文で>

INVESTIGATION POLICY
<Explorerが守るべきルールを箇条書きで。次を必ず含める:
存在しないfile pathを推測しない/
read は REPOSITORY FILES に存在するpathだけに対して行う/
symbolの所在が不明な場合はpathを推測せず最初にrgを使う/
git_logも実在確認済みpathだけに使う/
独立した検索は可能な限りbatchでRepoScout Planに含める/
RepoScoutのdeterministic query(rg/read/git_log)だけでEvidenceを収集し、自由な広域探索は行わない/
RepoScout Evidenceが十分なら追加のgrep/readを行わない>

REPOSITORY FILES
<<<PLACEHOLDER>>>

REQUIRED EVIDENCE
<Explorerが収集すべきEvidenceを箇条書きで。上記の確認したい観点を反映する>

OUTPUT CONTRACT
Explorerは以下の4セクションだけをMainへ返すこと。それ以外の文章や
subagent内の会話ログ・transcriptを含めてはならない。
FACTS
RELATIONS
SOURCE LOCATIONS
UNKNOWN
""".replace("<<<PLACEHOLDER>>>", REPOSITORY_FILES_PLACEHOLDER)

EXPLORER_PLAN_PROMPT_TEMPLATE = """\
{handoff}

---

あなたはSonnet Explorer Subagentです。上記のBriefだけが渡されている
情報のすべてです。Briefに従い、RepoScout Investigation Planを
生成してください。

自分では grep/read を実行しないでください。

利用可能なtool:
- rg
- read
- git_log

YAMLのみ出力してください。

スキーマ:
goal: <調査目的>
queries:
  - id: Q1
    tool: rg            # rg | read | git_log のいずれかを必ず指定する
    pattern: <検索文字列>
    paths: [<検索対象パス>]
  - id: Q2
    tool: read
    file: <ファイルパス>
    start_line: <開始行>
    end_line: <終了行>
  - id: Q3
    tool: git_log
    git_args: [<git log に渡す引数>]
"""

EXPLORER_SYNTHESIS_PROMPT_TEMPLATE = """\
{handoff}

---

あなたはSonnet Explorer Subagentです。上記のBriefと、RepoScoutが
収集した以下のEvidenceを使って、Structured Evidence Packを
作成してください。

Evidenceが不足している場合のみ、追加でtool(rg/read/grep)を使って
構いません。ただし広域探索は避け、Brief記載のREPOSITORY FILESと
INVESTIGATION POLICYの範囲内に留めてください。Evidenceが十分な場合は
追加探索を行わないでください。

出力は次の4セクションだけとし、この見出しのまま・この順序で
出力してください。Main Agentに会話ログやtranscriptを渡す必要は
ありません。この4セクションの本文だけが、Mainに渡る唯一の情報です。

FACTS
<確認できた事実を箇条書きで>

RELATIONS
<InvestigationRunnerと他コンポーネントの依存/呼び出し関係を箇条書きで>

SOURCE LOCATIONS
<各事実の裏付けとなる file:行番号 または file:行範囲>

UNKNOWN
<Evidenceだけでは判断できなかった点。なければ「なし」>

--- EVIDENCE START ---
{evidence}
--- EVIDENCE END ---
"""

MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE = """\
Sonnet Explorer Subagentから、以下のStructured Evidence Packが
返されました。あなたはMain Agent(Opus)です。Explorerとの会話履歴は
一切持っていません。このEvidence Packだけを根拠に、
InvestigationRunner の変更影響範囲を分析してください。

確認対象:
- 定義箇所
- 参照箇所
- 関連テスト
- 依存クラス
- 変更時に確認すべきファイル

実装はしないでください。

--- EVIDENCE PACK START ---
{evidence_pack}
--- EVIDENCE PACK END ---
"""

# --- Pattern B3.1: drop the Explorer synthesis call, Main reads raw ---------
# RepoScout evidence directly (Brief -> Sonnet plan -> RepoScout -> Main
# final, no intermediate Sonnet summarisation step).

MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1 = """\
RepoScoutが収集した以下のEvidenceを使って、下記Investigation Brief
記載の調査目的に沿って変更影響範囲を分析してください。あなたは
Main Agent(Opus)です。Explorerとの会話履歴は持っていません。この
Briefと生のRepoScout Evidenceだけが根拠です(要約は挟まれていません)。

確認対象:
- 定義箇所
- 参照箇所
- 関連テスト
- 依存クラス
- 変更時に確認すべきファイル

実装はしないでください。

--- BRIEF START ---
{handoff}
--- BRIEF END ---

--- EVIDENCE START ---
{evidence}
--- EVIDENCE END ---
"""

# --- CP7: Task Generalization -------------------------------------------
#
# Same B3.2 architecture and same wording as MAIN_BRIEF_PROMPT /
# MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1, just with the investigation
# target and confirmation points parameterized instead of hardcoded to
# InvestigationRunner. No prompt engineering changes — this is the same
# structure applied to a different question, which is exactly what CP7
# tests.

MAIN_BRIEF_PROMPT_TEMPLATE = """\
あなたはMain Agent(Opus)です。これから Sonnet Explorer Subagent に
Repository探索を委任します。Explorerには会話履歴を一切渡しません。
あなたがこれから出力する Investigation Brief だけが、Explorerに渡る
唯一の情報になります。

調査目的: {investigation_goal}

確認したい観点:
{confirmation_points}

以下の5セクションを、この見出しのまま・この順序で出力してください。
見出し以外の文章やコードフェンスは付けないでください。
REPOSITORY FILES セクションの本文には "<<<PLACEHOLDER>>>" という1行だけを
書いてください（実際のファイル一覧は後で機械的に差し込まれます）。

TASK
<Explorerが実行すべき調査タスクを1〜2文で>

INVESTIGATION POLICY
<Explorerが守るべきルールを箇条書きで。次を必ず含める:
存在しないfile pathを推測しない/
read は REPOSITORY FILES に存在するpathだけに対して行う/
symbolの所在が不明な場合はpathを推測せず最初にrgを使う/
git_logも実在確認済みpathだけに使う/
独立した検索は可能な限りbatchでRepoScout Planに含める/
RepoScoutのdeterministic query(rg/read/git_log)だけでEvidenceを収集し、自由な広域探索は行わない/
RepoScout Evidenceが十分なら追加のgrep/readを行わない>

REPOSITORY FILES
<<<PLACEHOLDER>>>

REQUIRED EVIDENCE
<Explorerが収集すべきEvidenceを箇条書きで。上記の確認したい観点を反映する>

OUTPUT CONTRACT
Explorerは以下の4セクションだけをMainへ返すこと。それ以外の文章や
subagent内の会話ログ・transcriptを含めてはならない。
FACTS
RELATIONS
SOURCE LOCATIONS
UNKNOWN
""".replace("<<<PLACEHOLDER>>>", REPOSITORY_FILES_PLACEHOLDER)

MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_GENERIC = """\
RepoScoutが収集した以下のEvidenceを使って、下記Investigation Brief
記載の調査目的に沿って分析してください。あなたはMain Agent(Opus)
です。Explorerとの会話履歴は持っていません。この
Briefと生のRepoScout Evidenceだけが根拠です(要約は挟まれていません)。

確認対象:
{confirmation_points}

実装はしないでください。

--- BRIEF START ---
{handoff}
--- BRIEF END ---

--- EVIDENCE START ---
{evidence}
--- EVIDENCE END ---
"""

# --- CP7.1: Change-Scope Planning Policy ---------------------------------
#
# CP7's change-scope task stopped at direct references to the changed
# implementation detail and never searched for the symbol that owns it, so
# it missed that symbol's consumers. This is a Plan-generation instruction
# only -- it names no concrete symbol, so it generalizes to any "what do I
# need to touch to change X" task rather than encoding this one case.
CHANGE_SCOPE_POLICY = """
Change-Scope Policy(このPlanに必ず反映すること):
1. 変更対象のdirect referencesを確認するクエリを含める。
2. 変更対象が constant / field / private function / helper 等の
   局所implementation detailである場合、それを所有する
   enclosing class / function / module を特定するクエリを含める。
3. そのenclosing symbol自体の利用箇所(consumer)を検索するクエリを含める
   (定数名ではなく、enclosing symbolの名前で検索すること)。
4. consumer側のbehavior/contractへの影響を確認できるクエリを含める。
5. 関連testの有無を確認するクエリを含める。
direct referencesが局所的であることだけを理由に調査を終了しないこと。
"""

# --- CP7-E: Main-Owned Investigation Planning ----------------------------
#
# CP7-D showed the Plan quality gap was the planner model, not the
# Investigation Policy wording. Rather than pay for a second Opus call, the
# Main agent writes the Brief and the RepoScout Plan in its first call --
# it already holds the task context that the Brief exists to transfer.
#
# Two structural consequences of merging the calls, both forced:
#   - Main must see REPOSITORY FILES up front, since it now writes the Plan.
#     The file list itself is unchanged (`git ls-files src tests/unit`); only
#     the stage it is injected at moves.
#   - The Brief's OUTPUT CONTRACT section addressed the Explorer, which no
#     longer exists. It now names the same four evidence facets for Main's
#     own final analysis, so the handoff keeps the same five-section shape.
# The INVESTIGATION POLICY rules are carried over verbatim, and no
# change-scope-specific guidance is added.

MAIN_BRIEF_AND_PLAN_PROMPT_TEMPLATE = """\
あなたはMain Agent(Opus)です。今回はExplorer Subagentを使いません。
あなた自身が Investigation Brief と RepoScout Investigation Plan の
両方を、この1回の出力で生成します。

調査目的: {investigation_goal}

確認したい観点:
{confirmation_points}

REPOSITORY FILES(実在するファイルはこれがすべてです):
{repository_files}

出力は必ず次の2部構成とし、この順序・この区切り行のまま出力してください。

=== BRIEF ===
以下の5セクションを、この見出しのまま・この順序で出力してください。
見出し以外の文章やコードフェンスは付けないでください。
REPOSITORY FILES セクションの本文には "<<<PLACEHOLDER>>>" という1行だけを
書いてください（実際のファイル一覧は後で機械的に差し込まれます）。

TASK
<実行すべき調査タスクを1〜2文で>

INVESTIGATION POLICY
<調査で守るべきルールを箇条書きで。次を必ず含める:
存在しないfile pathを推測しない/
read は REPOSITORY FILES に存在するpathだけに対して行う/
symbolの所在が不明な場合はpathを推測せず最初にrgを使う/
git_logも実在確認済みpathだけに使う/
独立した検索は可能な限りbatchでRepoScout Planに含める/
RepoScoutのdeterministic query(rg/read/git_log)だけでEvidenceを収集し、自由な広域探索は行わない/
RepoScout Evidenceが十分なら追加のgrep/readを行わない>

REPOSITORY FILES
<<<PLACEHOLDER>>>

REQUIRED EVIDENCE
<収集すべきEvidenceを箇条書きで。上記の確認したい観点を反映する>

OUTPUT CONTRACT
RepoScoutが返すEvidenceは、最終分析で次の4観点に整理して用いる。
FACTS
RELATIONS
SOURCE LOCATIONS
UNKNOWN

=== PLAN ===
上記Briefに従い、RepoScout Investigation Planを生成してください。
この時点では grep/read を自分で実行しないでください。

利用可能なtool:
- rg
- read
- git_log

この区切り行の後はYAMLのみ出力してください。

スキーマ:
goal: <調査目的>
queries:
  - id: Q1
    tool: rg            # rg | read | git_log のいずれかを必ず指定する
    pattern: <検索文字列>
    paths: [<検索対象パス>]
  - id: Q2
    tool: read
    file: <ファイルパス>
    start_line: <開始行>
    end_line: <終了行>
  - id: Q3
    tool: git_log
    git_args: [<git log に渡す引数>]
""".replace("<<<PLACEHOLDER>>>", REPOSITORY_FILES_PLACEHOLDER)

BRIEF_PLAN_SEPARATOR = "=== PLAN ==="
BRIEF_SECTION_HEADER = "=== BRIEF ==="
