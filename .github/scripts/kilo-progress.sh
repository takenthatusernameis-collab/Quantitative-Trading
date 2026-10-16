# Shared Kilo progress telemetry.
# Source after cutoff_epoch is initialized; set WORKFLOW_STARTED_EPOCH at controller startup.
# Telemetry must never abort the controller or interrupt checkpoint persistence.

WORKFLOW_STARTED_EPOCH="${WORKFLOW_STARTED_EPOCH:-$(date +%s)}"
KILO_PROGRESS_STATE_FILE="${KILO_PROGRESS_STATE_FILE:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/kilo-progress-state-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.txt}"
KILO_PROGRESS_LOG="${KILO_PROGRESS_LOG:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/kilo-progress-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.log}"
: >> "$KILO_PROGRESS_LOG" 2>/dev/null || true

write_progress() {
  local phase="${1:-unknown}" detail="${2:-}" now elapsed remaining head_sha tmp line state_written
  now="$(date +%s)"
  elapsed=$((now - ${WORKFLOW_STARTED_EPOCH:-$now}))
  remaining=$(( ${cutoff_epoch:-$now} - now ))
  if [ "$remaining" -lt 0 ]; then remaining=0; fi
  detail="$(printf '%s' "$detail" | tr '\r\n' '  ' | cut -c1-160)"
  head_sha="$(git rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
  tmp="${KILO_PROGRESS_STATE_FILE}.tmp.$$"
  state_written=0

  if ! {
    printf 'updated_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'phase=%s\n' "$phase"
    printf 'detail=%s\n' "$detail"
    printf 'session=%s\n' "${agent_index:-0}"
    printf 'session_limit=%s\n' "${SESSION_LIMIT_POLICY:-${KILO_INPUT_AGENTS:-unknown}}"
    printf 'attempt=%s\n' "${session_attempt:-0}"
    printf 'completed=%s\n' "${sessions_completed:-0}"
    printf 'failed=%s\n' "${failed_sessions:-0}"
    printf 'checkpoints=%s\n' "${persisted_checkpoints:-0}"
    printf 'verified_checkpoint_sha=%s\n' "${last_verified_checkpoint_sha:-none}"
    printf 'head=%s\n' "$head_sha"
    printf 'elapsed_seconds=%s\n' "$elapsed"
    printf 'remaining_seconds=%s\n' "$remaining"
  } > "$tmp" 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null || true
  elif mv -f "$tmp" "$KILO_PROGRESS_STATE_FILE" 2>/dev/null; then
    state_written=1
  else
    rm -f "$tmp" 2>/dev/null || true
  fi

  line="[progress] $(date -u +%Y-%m-%dT%H:%M:%SZ) phase=${phase} session=${agent_index:-0}/${SESSION_LIMIT_POLICY:-${KILO_INPUT_AGENTS:-unknown}} attempt=${session_attempt:-0} completed=${sessions_completed:-0} failed=${failed_sessions:-0} checkpoints=${persisted_checkpoints:-0} verified_sha=${last_verified_checkpoint_sha:-none} head=${head_sha} elapsed=${elapsed}s remaining=${remaining}s state_written=${state_written} detail=${detail}"
  printf '%s\n' "$line" | tee -a "$KILO_PROGRESS_LOG" || true
  return 0
}
