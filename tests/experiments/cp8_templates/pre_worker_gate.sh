#!/usr/bin/env bash
# CP8 pre_worker_diff_empty gate.
#
# Fires on every Agent / Task call. Config B claims that the diff produced in
# a run is the Sonnet Worker's diff; that claim only holds if the tree was
# clean at the moment Main delegated. This hook enforces that at the point of
# delegation rather than checking for it afterwards.
#
# It only ever denies. On a clean tree it stays silent so that the normal
# permission system -- the --allowedTools list -- remains the single thing
# deciding what is allowed to run.
set -uo pipefail

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
log_dir="$project_dir/.cp8"
log="$log_dir/pre_worker_gate.log"
mkdir -p "$log_dir"

dirty="$(git -C "$project_dir" status --porcelain 2>&1)"
status=$?

if [ "$status" -ne 0 ]; then
  printf '%s\tERROR\t%s\n' "$(date -Iseconds)" "$dirty" >>"$log"
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"CP8 pre_worker_diff_empty gate could not read the working tree state. Delegation is refused because the gate cannot be shown to have passed."}}
JSON
  exit 0
fi

if [ -n "$dirty" ]; then
  printf '%s\tDENY\n%s\n' "$(date -Iseconds)" "$dirty" >>"$log"
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"CP8 pre_worker_diff_empty gate: the working tree is not clean at the point of delegation. Main must not modify the tree before handing work to the Worker. Do not retry and do not implement the change yourself; report this and stop."}}
JSON
  exit 0
fi

printf '%s\tALLOW\n' "$(date -Iseconds)" >>"$log"
exit 0
