#!/bin/bash
# Claude Code status line — two lines:
#   Line 1: [Model]  folder  on branch  +staged ~modified
#   Line 2: ████░░░░░░  42%  |  $0.12  |  5m 23s

input=$(cat)

# Parse JSON fields in one pass
MODEL=$(echo "$input" | jq -r '.model.display_name // "Claude"')
DIR=$(echo "$input"   | jq -r '.workspace.current_dir // env.PWD')
PCT=$(echo "$input"   | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
COST=$(echo "$input"  | jq -r '.cost.total_cost_usd // 0')
DUR=$(echo "$input"   | jq -r '.cost.total_duration_ms // 0')

# Colors
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

# --- Line 1: model · folder · git ---
FOLDER="${DIR##*/}"
BRANCH_PART=""
if git -C "$DIR" rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null)
    STAGED=$(git -C "$DIR" diff --cached --numstat 2>/dev/null | grep -c .)
    MODIFIED=$(git -C "$DIR" diff --numstat 2>/dev/null | grep -c .)
    GIT_STATUS=""
    [ "$STAGED" -gt 0 ]   && GIT_STATUS="${GIT_STATUS} ${GREEN}+${STAGED}${RESET}"
    [ "$MODIFIED" -gt 0 ] && GIT_STATUS="${GIT_STATUS} ${YELLOW}~${MODIFIED}${RESET}"
    BRANCH_PART="  ${DIM}on${RESET} ${GREEN}${BRANCH}${RESET}${GIT_STATUS}"
fi

echo -e "${CYAN}[${MODEL}]${RESET}  ${FOLDER}${BRANCH_PART}"

# --- Line 2: context bar · cost · duration ---
[ -z "$PCT" ] && PCT=0
if   [ "$PCT" -ge 90 ]; then BAR_COLOR="$RED"
elif [ "$PCT" -ge 70 ]; then BAR_COLOR="$YELLOW"
else                         BAR_COLOR="$GREEN"
fi

FILLED=$((PCT / 10))
[ "$FILLED" -gt 10 ] && FILLED=10
EMPTY=$((10 - FILLED))
BAR=""
[ "$FILLED" -gt 0 ] && BAR=$(printf "%${FILLED}s" | tr ' ' '█')
[ "$EMPTY"  -gt 0 ] && BAR="${BAR}$(printf "%${EMPTY}s" | tr ' ' '░')"

COST_FMT=$(printf '$%.2f' "$COST")
TOTAL_SECS=$((DUR / 1000))
DAYS=$((TOTAL_SECS / 86400))
HOURS=$(( (TOTAL_SECS % 86400) / 3600 ))
MINS=$(( (TOTAL_SECS % 3600) / 60 ))
SECS=$((TOTAL_SECS % 60))
DUR_FMT=""
[ "$DAYS"  -gt 0 ] && DUR_FMT="${DAYS}d "
[ "$HOURS" -gt 0 ] && DUR_FMT="${DUR_FMT}${HOURS}h "
[ "$MINS"  -gt 0 ] && DUR_FMT="${DUR_FMT}${MINS}m "
DUR_FMT="${DUR_FMT}${SECS}s"

echo -e "${BAR_COLOR}${BAR}${RESET}  ${PCT}%  |  ${YELLOW}${COST_FMT}${RESET}  |  ${DUR_FMT}"
