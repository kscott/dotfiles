#!/bin/bash
# brew-update.sh — weekly Homebrew and gem update
# Scheduled via crontab (see dotfiles/crontab)

PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

LOG="$HOME/logs/brew-update.log"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")

mkdir -p "$HOME/logs"

# Keep log under 2000 lines
if [[ -f "$LOG" ]] && [[ $(wc -l < "$LOG") -gt 2000 ]]; then
  echo "$(tail -n 1000 "$LOG")" > "$LOG"
fi

echo "[$TIMESTAMP] brew-update started" >> "$LOG"

brew update >> "$LOG" 2>&1 && \
brew upgrade >> "$LOG" 2>&1 && \
echo "[$TIMESTAMP] brew upgrade OK" >> "$LOG" || \
echo "[$TIMESTAMP] brew upgrade FAILED" >> "$LOG"

gem update >> "$LOG" 2>&1 && \
echo "[$TIMESTAMP] gem update OK" >> "$LOG" || \
echo "[$TIMESTAMP] gem update FAILED" >> "$LOG"

echo "[$TIMESTAMP] brew-update complete" >> "$LOG"
