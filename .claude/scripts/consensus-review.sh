#!/usr/bin/env bash
# Consensus review loop: Claude writes → Codex/Gemini review → iterate until approved
# Called by Stop hook. Exits 0 = approved, 1 = rejected (block stop)

set -euo pipefail

SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%s)}"
MAX_ROUNDS=3
ROUND=1
PREV_FINDINGS=""

echo "🔍 Starting consensus review (session: $SESSION_ID)"

while (( ROUND <= MAX_ROUNDS )); do
  echo "=== Round $ROUND / $MAX_ROUNDS ==="

  # Build context from previous findings
  CONTEXT=""
  if [[ -n "$PREV_FINDINGS" ]]; then
    CONTEXT="Previous round findings to address: $PREV_FINDINGS"
  fi

  # Call review_precommit via MCP (auto-captures staged diff)
  RESULT=$(npx -y codex-claude-bridge@latest review_precommit -- "{
    \"sessionId\": \"$SESSION_ID\",
    \"context\": \"$CONTEXT\",
    \"mode\": \"deliberate-deep\"
  }" 2>&1) || {
    echo "⚠️ Review call failed (continuing): $RESULT"
    exit 0  # Don't block on infrastructure failures
  }

  VERDICT=$(echo "$RESULT" | jq -r '.verdict // "unknown"')
  FINDINGS=$(echo "$RESULT" | jq -c '.findings // []')

  echo "Verdict: $VERDICT"
  echo "Findings count: $(echo "$FINDINGS" | jq 'length')"

  if [[ "$VERDICT" == "approved" ]]; then
    echo "✅ Consensus reached — approved"
    exit 0
  fi

  if [[ "$VERDICT" == "rejected" || "$VERDICT" == "changes_requested" ]]; then
    echo "❌ Changes requested:"
    echo "$FINDINGS" | jq -r '.[] | "  - \(.file // "general"):\(.line // 0) \(.message)"'
    PREV_FINDINGS="$FINDINGS"
  fi

  ((ROUND++))
done

echo "⚠️ Max rounds ($MAX_ROUNDS) reached without consensus"
echo "📋 Final findings:"
echo "$PREV_FINDINGS" | jq -r '.[] | "  - \(.file // "general"):\(.line // 0) \(.message)"'
exit 1