set -Eeuo pipefail
cutoff_epoch=$(($(date +%s) + 355 * 60))
umask 077
# Kilo uses only the repository-scoped GITHUB_TOKEN. Workflow definitions are maintainer-managed because this token cannot grant workflows permission.
export HOME="$RUNNER_TEMP/kilo-home"
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export TMPDIR="$RUNNER_TEMP/kilo-tmp"
mkdir -p "$XDG_CONFIG_HOME/kilo" "$XDG_DATA_HOME/kilo" "$XDG_CACHE_HOME/kilo" "$TMPDIR" "$RUNNER_TEMP/kilo"
for directory in "$HOME" "$XDG_CONFIG_HOME/kilo" "$XDG_DATA_HOME/kilo" "$XDG_CACHE_HOME/kilo" "$TMPDIR" "$RUNNER_TEMP/kilo"; do
  if ! ( : > "$directory/.kilo-write-test" ) 2>/dev/null; then
    echo "::error::Runtime directory is not writable: $directory."
    exit 1
  fi
  rm -f "$directory/.kilo-write-test"
done

# A durable marker opts this single activation into exactly two sessions.
one_shot_mode=0
if [ -f ".kilo/TWO_AGENT_ONCE" ]; then
  one_shot_mode=1
  echo "::notice::One-shot marker detected; setting the sequential session count to exactly two."
fi
# A queued schedule may check out an older commit containing the sentinel.
# Require it to exist on the live default branch before spending the allowance.
if [ "$one_shot_mode" -eq 1 ]; then
  DEFAULT_BRANCH="$KILO_DEFAULT_BRANCH"
  if [ -z "$DEFAULT_BRANCH" ] || ! git fetch origin "$DEFAULT_BRANCH"; then
    echo "::warning::Could not verify the one-shot marker on the remote branch; deferring this activation safely."
    exit 0
  fi
  if ! git cat-file -e "origin/$DEFAULT_BRANCH:.kilo/TWO_AGENT_ONCE" 2>/dev/null; then
    echo "::notice::The one-shot marker is absent from origin/$DEFAULT_BRANCH; this is a stale/duplicate activation, exiting without invoking Kilo."
    exit 0
  fi
fi

if [ "$one_shot_mode" -eq 0 ] && [ "${GITHUB_EVENT_NAME:-${KILO_TRIGGER_EVENT:-}}" = "schedule" ] && [ -f ".kilo/SKIP_NEXT_ROUTINE_KILO" ]; then
  echo "::notice::Consuming the one-time post-smoke skip; this activation will not start Kilo."
  git config user.name "kilo-autonomous"
  git config user.email "kilo-autonomous@users.noreply.github.com"
  DEFAULT_BRANCH="$KILO_DEFAULT_BRANCH"
  if [ -z "$DEFAULT_BRANCH" ]; then
    echo "::warning::Default branch is unavailable; retaining the skip marker for a later activation."
    exit 0
  fi
  if ! git rm -f -- .kilo/SKIP_NEXT_ROUTINE_KILO || ! git commit -m "chore(kilo): consume one-time post-run skip"; then
    echo "::warning::Could not create the skip-marker consumption commit; the next routine activation will retry."
    exit 0
  fi
  delay=5
  while true; do
    remaining=$((cutoff_epoch - $(date +%s)))
    if [ "$remaining" -le 0 ]; then
      echo "::warning::Could not verify skip-marker persistence before the cutoff; stopping safely."
      exit 0
    fi
    if git fetch origin "$DEFAULT_BRANCH" && git merge-base --is-ancestor "origin/$DEFAULT_BRANCH" HEAD && git push origin "HEAD:$DEFAULT_BRANCH"; then
      remote_sha="$(git ls-remote origin "refs/heads/$DEFAULT_BRANCH" 2>/dev/null | awk 'NR==1 {print $1}')"
      local_sha="$(git rev-parse HEAD)"
      if [ -n "$remote_sha" ] && [ "$remote_sha" = "$local_sha" ]; then
        echo "Verified one-time skip-marker removal at $remote_sha."
        break
      fi
    fi
    echo "::warning::Could not verify skip-marker removal; retrying without a fixed attempt limit."
    remaining=$((cutoff_epoch - $(date +%s)))
    if [ "$remaining" -le 0 ]; then exit 0; fi
    if [ "$delay" -gt "$remaining" ]; then delay="$remaining"; fi
    sleep "$delay"
    if [ "$delay" -lt 30 ]; then delay=$((delay * 2)); if [ "$delay" -gt 30 ]; then delay=30; fi; fi
  done
  exit 0
fi

cat > "$HOME/.config/kilo/kilo.json" <<'EOF'
{"$schema":"https://app.kilo.ai/config.json","permission":"allow"}
EOF

install_attempt=0
install_backoff=5
until timeout --signal=TERM --kill-after=10s 180s npm install --no-audit --no-fund --prefix "$RUNNER_TEMP/kilo" @kilocode/cli@7.7.1; do
  install_attempt=$((install_attempt + 1))
  remaining=$((cutoff_epoch - $(date +%s)))
  if [ "$remaining" -le 0 ]; then
    echo "::error::Kilo installation did not recover before the 355-minute cutoff; no agent session was started."
    exit 1
  fi
  delay="$install_backoff"
  if [ "$remaining" -lt "$delay" ]; then delay="$remaining"; fi
  echo "::warning::Kilo CLI installation attempt $install_attempt failed; retrying in ${delay}s (no attempt-count cap)."
  sleep "$delay"
  if [ "$install_backoff" -lt 60 ]; then
    install_backoff=$((install_backoff * 2))
    if [ "$install_backoff" -gt 60 ]; then install_backoff=60; fi
  fi
done
export PATH="$RUNNER_TEMP/kilo/node_modules/.bin:$PATH"

git config user.name "kilo-autonomous"
git config user.email "kilo-autonomous@users.noreply.github.com"

agents="${KILO_INPUT_AGENTS:-1000}"
if ! [[ "$agents" =~ ^[0-9]+$ ]]; then
  echo "::warning::Invalid agent count; using a safe value."
  agents=1
fi
if [ "$agents" -lt 1 ]; then agents=1; fi
if [ "$agents" -gt 1000 ]; then agents=1000; fi
if [ "$one_shot_mode" -eq 1 ]; then agents=2; fi
echo "Configured sequential Kilo sessions: $agents (one-shot mode: $one_shot_mode)."
command=$(cat <<'PROMPT'
Execute the task assigned by the previous agent and prepare a task for the next agent!

If no prior agent assignment or handoff exists, inspect the repository and select one bounded, high-value task that can be implemented and verified in this session. Do not wait passively for an assignment that does not exist. Do not count control-marker-only commits as project progress.

GENERAL RELIABILITY AND PROGRESS RULES

1. PRESERVE THE WORKING BASELINE
- Keep the existing project and workflow architecture stable.
- Prefer the smallest reversible change that solves a demonstrated problem.
- Do not introduce parallel execution, redesign orchestration, or weaken permissions and safety controls merely because a task failed.
- Prioritize useful, durable progress over infrastructure perfection.

2. CHANGE APPROACH AFTER REPEATED FAILURE
- Track consecutive failures caused by the same underlying problem and approach.
- After five consecutive failures, do not repeat that same approach unchanged a sixth time.
- Record the observed failures and evidence, then choose a materially different approach.
- Changing wording, waiting, or retrying an identical operation with unchanged assumptions is not a materially different approach.
- Do not make speculative changes merely to satisfy this rule. If no safe, evidence-based alternative exists, stop that line of work and prepare a clear handoff.
- Distinguish a recurring deterministic blocker from unrelated transient errors.

3. HANDLE ERRORS PROPORTIONATELY
- For transient network, provider, rate-limit, timeout, and service errors, preserve progress, use bounded backoff, and honor available retry instructions.
- Avoid amplifying service outages with unnecessary parallel requests.
- For reproducible errors, investigate and fix the root cause with the smallest verifiable change.
- Do not repeatedly retry an operation when its prerequisites are known to be missing.

4. INSPECT AND VERIFY
- Inspect relevant error messages, logs, configuration, dependencies, and project conventions before changing things.
- Reproduce the smallest failure when practical and verify prerequisites before relying on them.
- Never claim a test, deployment, log review, or other check passed without evidence.
- After a change, rerun the focused check; run broader checks when useful.
- Never delete user data, disable validation, or weaken safety controls simply to make an error disappear.

5. PRESERVE DURABLE PROGRESS
- Inspect repository status and diffs before checkpointing.
- Preserve useful partial work and avoid unrelated modifications.
- Exclude secrets, credentials, caches, generated runtime data, and environment directories as appropriate.
- Use available formatting and whitespace checks.
- Respect repository boundaries and collaboration conventions.
- Reconcile remote changes instead of blindly overwriting them. When committing or pushing is part of the task, verify persistence.

6. PRIORITIZE RESULTS OVER ACTIVITY
- An unsuccessful session can still produce useful findings if they are recorded durably.
- A successful process exit does not prove the task was completed correctly.
- Fix cheap, deterministic blockers; tolerate isolated recoverable failures.
- Do not turn every operational imperfection into an infrastructure project.
- Prefer accumulated, verified improvements over optimizing solely for successful session exits.

7. USE SAFEGUARDS PROPORTIONATELY
- Encode critical, repeatable invariants in executable checks when practical.
- Use agent instructions for judgment and decisions that cannot reliably be reduced to deterministic checks.
- Preserve existing automation, permissions, checkpoint controls, and safety policies unless the assigned task explicitly requires a change and the change is justified.
- Avoid elaborate machinery for hypothetical failures without evidence that its benefits justify the complexity.
- Do not treat a prompt instruction as an independently enforced guarantee.

8. END EVERY SESSION WITH A USEFUL HANDOFF
State:
- What changed.
- What was actually verified.
- What remains unresolved.
- Which approaches have already failed and why.
- One precise next task, with relevant evidence and constraints.

If blocked, preserve useful progress and leave an evidence-based handoff. The next session must inspect that evidence rather than blindly repeating failed attempts.

DEFAULT OPERATING PRINCIPLE
Make progress despite imperfection. Fix cheap, deterministic blockers. Tolerate isolated recoverable failures. Protect durable progress and critical invariants. Change approach when evidence shows the current one is not working.
PROMPT
)
DEFAULT_BRANCH="$KILO_DEFAULT_BRANCH"

if [ -z "$DEFAULT_BRANCH" ]; then
  echo "::warning::GitHub did not provide the default branch; preserving the repository and ending this activation safely."
  exit 0
fi

echo "Repository default branch: $DEFAULT_BRANCH"

# Deterministic preflight for the reported SQLite failure: create the
# expected project data directory before any Kilo agent can run migrations.
# This is runtime preparation only; database files remain excluded from commits.
if ! mkdir -p data || [ ! -d data ] || [ ! -w data ]; then
  echo "::error::Repository data directory is not available and writable; refusing to start sessions that would predictably fail SQLite access."
  exit 1
fi

heartbeat() {
  while true; do
    printf '[heartbeat] %sZ\n' "$(date -u +%Y-%m-%dT%H:%M:%S)"
    sleep 60
  done
}

heartbeat &
heartbeat_pid=$!
trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT

failed_sessions=0
consecutive_failures=0
idle_timeout_retry_count=0
project_progress=0
provider_pressure_streak=0
cutoff=0

for agent_index in $(seq 1 "$agents"); do
  remaining=$((cutoff_epoch - $(date +%s)))
  if [ "$remaining" -le 0 ]; then
    cutoff=1
    break
  fi
  WORKFLOW_BASE_SHA="$(git rev-parse HEAD)"
  session_log="$RUNNER_TEMP/kilo-session-${agent_index}.log"
  : > "$session_log"
  provider_pressure=0
  transient_retry_backoff=15
  session_attempt=0
  echo "Starting sequential Kilo session ${agent_index}/${agents}; remaining safety budget ${remaining}s."
  while true; do
    session_attempt=$((session_attempt + 1))
    attempt_log="$RUNNER_TEMP/kilo-session-${agent_index}-attempt-${session_attempt}.log"
    remaining_global=$((cutoff_epoch - $(date +%s)))
    if [ "$remaining_global" -le 0 ]; then rc=124; echo "::warning::355-minute workflow cutoff reached before attempt ${session_attempt}."; break; fi
    echo "Kilo invocation attempt ${session_attempt} for session ${agent_index}; transient upstream failures retry without an attempt-count limit."
    set +e
    timeout --signal=TERM --kill-after=10s "${remaining_global}s" kilo run --model kilo/kilo-auto/free --auto "$command" 2>&1 | tee "$attempt_log" | tee -a "$session_log"
    rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" -eq 0 ]; then break; fi
    normalized_attempt_log="$attempt_log.normalized"
    python - "$attempt_log" "$normalized_attempt_log" <<'PY'
import re
import sys
from pathlib import Path
source, target = map(Path, sys.argv[1:3])
text = source.read_text(encoding="utf-8", errors="replace")
text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
target.write_text(text, encoding="utf-8")
PY
    if grep -Eiq 'Upstream idle timeout exceeded|upstream.{0,40}idle.{0,40}timeout|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|ENETUNREACH|EHOSTUNREACH|socket hang up|fetch failed|temporary failure in name resolution|gateway timeout|bad gateway|service unavailable|too many requests|rate[ _-]?limit|resource[_ -]?exhausted|temporarily unavailable|HTTP.{0,12}(429|500|502|503|504)|status.{0,12}(429|500|502|503|504)' "$normalized_attempt_log"; then
      idle_timeout_retry_count=$((idle_timeout_retry_count + 1))
      retry_delay="$transient_retry_backoff"
      remaining_global=$((cutoff_epoch - $(date +%s)))
      if [ "$remaining_global" -le "$retry_delay" ]; then echo "::warning::Transient upstream/network failure detected, but insufficient workflow time remains for another retry."; break; fi
      echo "::warning::Transient upstream/network failure in session ${agent_index}; retry #${idle_timeout_retry_count} after ${retry_delay}s. No attempt-count limit; retries continue until the 355-minute workflow cutoff."
      sleep "$retry_delay"
      if [ "$transient_retry_backoff" -lt 300 ]; then
        transient_retry_backoff=$((transient_retry_backoff * 2))
        if [ "$transient_retry_backoff" -gt 300 ]; then transient_retry_backoff=300; fi
      fi
      continue
    fi
    break
  done
  if [ "$rc" -ne 0 ]; then
    mkdir -p "$RUNNER_TEMP/kilo-failure-logs"
    tail -n 2000 "$session_log" > "$RUNNER_TEMP/kilo-failure-logs/session-${agent_index}.log" || true
    if grep -Eiq '(^|[^0-9])429([^0-9]|$)|rate[ _-]?limit|resource[_ -]?exhausted|quota.*(exceed|limit)|current[:= ]*402.*limit[:= ]*400' "$session_log"; then
      provider_pressure=1
      provider_pressure_streak=$((provider_pressure_streak + 1))
      echo "::warning::Provider quota/capacity failure detected; applying a longer cooldown."
    fi
  elif [ "$rc" -eq 0 ]; then
    provider_pressure_streak=0
  fi

  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
    if [ "$(date +%s)" -ge "$cutoff_epoch" ]; then
      cutoff=1
      echo "::warning::355-minute safety cutoff reached; saving the last possible checkpoint."
    else
      consecutive_failures=$((consecutive_failures + 1))
      failed_sessions=$((failed_sessions + 1))
      echo "::warning::Kilo invocation returned timeout status before the global cutoff or was terminated (failure streak: $consecutive_failures); continuing with a fresh session when time remains."
    fi
  elif [ "$rc" -ne 0 ]; then
    consecutive_failures=$((consecutive_failures + 1))
    failed_sessions=$((failed_sessions + 1))
    echo "::warning::Kilo session exited with status $rc (failure streak: $consecutive_failures; no failure-count cutoff)."
  else
    consecutive_failures=0
  fi

  # Keep Actions workflow definitions maintainer-managed. Restore tracked
  # workflow files to the revision at session start and remove agent-created
  # workflow files before creating the checkpoint commit.
  if ! git restore --source="$WORKFLOW_BASE_SHA" --staged --worktree -- .github/workflows; then
    echo "::warning::Could not fully restore workflow files; workflow paths remain excluded."
  fi
  git clean -fd -- .github/workflows || true

  # Signal routine activations to skip after session two (or if the global
  # cutoff ends this one-shot early). The skip marker is written first.
  if [ "$one_shot_mode" -eq 1 ] && { [ "$agent_index" -eq 2 ] || [ "$(date +%s)" -ge "$cutoff_epoch" ]; }; then
    mkdir -p .kilo
    if printf '%s\n' 'Skip one routine Kilo activation after the one-shot two-agent reliability run.' > .kilo/SKIP_NEXT_ROUTINE_KILO; then
      rm -f -- .kilo/TWO_AGENT_ONCE || echo "::warning::Could not remove the one-shot marker; routine activations remain safely gated."
    else
      echo "::warning::Could not write the post-run skip marker; retaining the one-shot marker for recovery."
    fi
  fi

  stage_repository_changes() {
    git add -A -- . \
      ':(exclude).github/workflows/**' \
      ':(exclude).venv/**' ':(exclude)**/.venv/**' \
      ':(exclude)venv/**' ':(exclude)**/venv/**' \
      ':(exclude)__pycache__/**' ':(exclude)**/__pycache__/**' \
      ':(exclude).pytest_cache/**' ':(exclude)**/.pytest_cache/**' \
      ':(exclude).mypy_cache/**' ':(exclude)**/.mypy_cache/**' \
      ':(exclude).ruff_cache/**' ':(exclude)**/.ruff_cache/**' \
      ':(exclude).tox/**' ':(exclude)**/.tox/**' \
      ':(exclude)node_modules/**' ':(exclude)**/node_modules/**' \
      ':(exclude)**/*.pyc' ':(exclude)**/*.pyo' \
      ':(exclude)**/*.sqlite' ':(exclude)**/*.sqlite3' ':(exclude)**/*.db' \
      ':(exclude)**/*.sqlite-wal' ':(exclude)**/*.sqlite-shm' \
      ':(exclude)**/*.sqlite3-wal' ':(exclude)**/*.sqlite3-shm' \
      ':(exclude)**/*.db-wal' ':(exclude)**/*.db-shm' \
      ':(exclude)**/*.tmp' ':(exclude)**/coverage.xml' ':(exclude)**/.coverage' \
      ':(exclude)**/kilo-session-*.log'
  }
  checkpoint_ready=1
  if ! stage_repository_changes; then
    echo "::warning::Staging failed; preserving worktree and allowing the next session to retry."
    checkpoint_ready=0
  fi

  # Repair generated trailing whitespace and extra blank lines at EOF
  # before enforcing the staged-diff check.
  if ! git diff --cached --check; then
    echo "::warning::Normalizing trailing whitespace and blank lines at EOF in changed text files."
    if ! python - <<'PY'
import os
import re
import subprocess
from pathlib import Path

staged_paths = subprocess.check_output(
    ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
).split(b"\0")

for raw_path in staged_paths:
    if not raw_path:
        continue
    path = Path(os.fsdecode(raw_path))
    if path.is_symlink() or not path.is_file():
        continue

    content = path.read_bytes()
    if b"\0" in content:
        continue

    cleaned = re.sub(rb"[ \t]+(?=\r?$)", b"", content, flags=re.MULTILINE)
    # Collapse trailing empty/whitespace-only lines to a single final newline.
    cleaned = re.sub(rb"(?:[ \t]*\r?\n)+\Z", b"\n", cleaned)
    if cleaned != content:
        path.write_bytes(cleaned)
PY
    then
      echo "::warning::Whitespace normalizer failed; deferring checkpoint to a fresh session."
      checkpoint_ready=0
    else
    if ! stage_repository_changes; then
      echo "::warning::Restaging after whitespace repair failed; deferring this checkpoint."
      checkpoint_ready=0
    fi
    fi
  fi

  if [ "$checkpoint_ready" -eq 1 ] && ! git diff --cached --check; then
    echo "::warning::Whitespace check still fails after normalization; deferring this checkpoint and continuing with a fresh session."
    checkpoint_ready=0
  fi

  checkpoint_has_project_changes=0
  if [ "$checkpoint_ready" -eq 1 ] && ! git diff --cached --quiet; then
    while IFS= read -r -d '' changed_path; do
      case "$changed_path" in
        .kilo/TWO_AGENT_ONCE|.kilo/SKIP_NEXT_ROUTINE_KILO) ;;
        *) checkpoint_has_project_changes=1 ;;
      esac
    done < <(git diff --cached --name-only -z)
  fi
  committed_this_iteration=0
  if [ "$checkpoint_ready" -eq 1 ] && ! git diff --cached --quiet; then
    if git commit --allow-empty-message -m ""; then
      committed_this_iteration=1
    else
      echo "::warning::Checkpoint commit failed; retaining worktree for the next session."
      checkpoint_ready=0
    fi
  fi

  # Deterministic repository-level persistence: reconcile any remote
  # advancement before every push, then verify that the remote points
  # to exactly the commit produced by this runner.
  persisted=1
  if [ "$checkpoint_ready" -eq 1 ] && [ "$committed_this_iteration" -eq 1 ]; then
    persisted=0
    push_attempt=0
    delay=5
    while [ "$persisted" -ne 1 ]; do
      remaining=$((cutoff_epoch - $(date +%s)))
      if [ "$remaining" -le 0 ]; then
        cutoff=1
        echo "::warning::Safety cutoff reached before checkpoint persistence could be confirmed."
        break
      fi
      push_attempt=$((push_attempt + 1))
      if ! git fetch origin "$DEFAULT_BRANCH"; then
        echo "::warning::Fetch failed on persistence attempt $push_attempt; retrying."
      elif ! git merge-base --is-ancestor "origin/$DEFAULT_BRANCH" HEAD; then
        if ! git rebase --autostash "origin/$DEFAULT_BRANCH"; then
          git rebase --abort >/dev/null 2>&1 || true
          echo "::warning::Rebase conflict during persistence attempt $push_attempt; preserving worktree and retrying with fresh remote state."
        fi
      elif git push origin "HEAD:$DEFAULT_BRANCH"; then
        remote_sha="$(git ls-remote origin "refs/heads/$DEFAULT_BRANCH" 2>/dev/null | awk 'NR==1 {print $1}')"
        local_sha="$(git rev-parse HEAD)"
        if [ -n "$remote_sha" ] && [ "$remote_sha" = "$local_sha" ]; then
          persisted=1
          echo "Repository persistence verified at $remote_sha after $push_attempt attempt(s)."
          break
        fi
        echo "::warning::Remote head did not match the local checkpoint after attempt $push_attempt; refetching."
      else
        echo "::warning::Push failed on persistence attempt $push_attempt; fetching and reconciling again."
      fi
      remaining=$((cutoff_epoch - $(date +%s)))
      if [ "$remaining" -le 0 ]; then cutoff=1; break; fi
      if [ "$delay" -gt "$remaining" ]; then delay="$remaining"; fi
      if [ "$delay" -gt 0 ]; then sleep "$delay"; fi
      if [ "$delay" -lt 30 ]; then delay=$((delay * 2)); if [ "$delay" -gt 30 ]; then delay=30; fi; fi
    done
  fi
  if [ "$persisted" -ne 1 ]; then
    echo "::warning::Checkpoint persistence was not confirmed. No success claim is made; stopping edits and preserving diagnostics before the cutoff."
    cutoff=1
  fi
  if [ "$persisted" -eq 1 ] && [ "$committed_this_iteration" -eq 1 ] && [ "$checkpoint_has_project_changes" -eq 1 ]; then
    project_progress=1
    echo "Meaningful repository progress checkpoint verified at $(git rev-parse HEAD)."
  fi
  if [ "$cutoff" -eq 1 ]; then
    break
  fi

  if [ "$provider_pressure" -eq 1 ]; then
    case "$provider_pressure_streak" in
      1) backoff_seconds=300 ;;
      2) backoff_seconds=600 ;;
      *) backoff_seconds=900 ;;
    esac
    remaining=$((cutoff_epoch - $(date +%s)))
    if [ "$backoff_seconds" -gt "$remaining" ]; then backoff_seconds="$remaining"; fi
    if [ "$backoff_seconds" -gt 0 ]; then
      echo "Provider cooldown: waiting ${backoff_seconds}s; no fixed failure-count limit."
      sleep "$backoff_seconds"
    fi
  elif [ "$consecutive_failures" -gt 0 ]; then
    case "$consecutive_failures" in
      1) backoff_seconds=15 ;;
      2) backoff_seconds=30 ;;
      3) backoff_seconds=60 ;;
      *) backoff_seconds=120 ;;
    esac
    jitter_seconds=$((RANDOM % 8))
    backoff_seconds=$((backoff_seconds + jitter_seconds))
    echo "Waiting ${backoff_seconds}s before the next agent session to reduce transient provider/network contention."
    sleep "$backoff_seconds"
  fi
done

if [ "$cutoff" -eq 1 ]; then
  echo "::warning::The 355-minute safety cutoff was reached; see checkpoint verification messages above."
fi
printf 'project_progress=%s\n' "$project_progress" >> "$GITHUB_OUTPUT"
printf 'failed_sessions=%s\n' "$failed_sessions" >> "$GITHUB_OUTPUT"
printf 'idle_timeout_retries=%s\n' "$idle_timeout_retry_count" >> "$GITHUB_OUTPUT"
if [ "$project_progress" -ne 1 ]; then
  echo "::error::No meaningful repository change or durable handoff was committed and verified in this activation. Control-marker-only commits do not count as progress."
  exit 1
fi
if [ "$failed_sessions" -gt 0 ]; then echo "::warning::Useful progress was persisted, but $failed_sessions Kilo session(s) failed. Upstream idle/network retries: $idle_timeout_retry_count."; fi
echo "Kilo controller completed with verified repository progress. Failed sessions: $failed_sessions; upstream idle/network retries: $idle_timeout_retry_count."
