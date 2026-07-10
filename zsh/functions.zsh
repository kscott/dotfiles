# Personal shell functions

# claude: wraps the real binary so every entry point (this, c, gc, ai, pv, ...)
# goes through the same pull-before/push-after sync of ~/claude-projects
# (memory + session transcripts, symlinked at ~/.claude/projects). Refuses to
# start on unsynced local state rather than silently building on top of it —
# see kscott/claude-projects README for the full reasoning.
claude() {
  local repo="$HOME/claude-projects"

  if [[ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ]]; then
    echo "claude: $repo has uncommitted changes from a previous session." >&2
    echo "        Resolve first: cd $repo && git status" >&2
    return 1
  fi

  local ahead
  ahead=$(git -C "$repo" rev-list '@{u}..' --count 2>/dev/null) || ahead=0
  if [[ "$ahead" -gt 0 ]]; then
    echo "claude: $repo has unpushed commits from a previous session." >&2
    echo "        Resolve first: cd $repo && git push" >&2
    return 1
  fi

  if ! git -C "$repo" pull --ff-only --quiet; then
    echo "claude: failed to pull latest state into $repo." >&2
    return 1
  fi

  # not `local` — EXIT traps fire after the function's own locals are torn
  # down, so _claude_sync_back needs a variable that outlives claude() itself.
  _claude_repo="$repo"

  _claude_sync_back() {
    if [[ -n "$(git -C "$_claude_repo" status --porcelain 2>/dev/null)" ]]; then
      git -C "$_claude_repo" add -A
      git -C "$_claude_repo" commit -m "session $(date '+%Y-%m-%d %H:%M:%S')" --quiet
      if ! git -C "$_claude_repo" push --quiet; then
        echo "" >&2
        echo "claude: WARNING — failed to push session/memory updates from $_claude_repo." >&2
        echo "        Do NOT use claude for this project from another machine until resolved." >&2
        echo "        Fix: cd $_claude_repo && git push" >&2
      fi
    fi
    unset _claude_repo
  }
  trap _claude_sync_back EXIT

  command "$HOME/.local/bin/claude" "$@"
}

# Create directory (including parents) and cd into it
mkcd() { mkdir -p "$@" && cd "$@" }

# Insert current time at cursor (e.g. 3:15pm) — bound to Ctrl+]
_insert_time() { LBUFFER+=$(date '+%I:%M%p' | sed 's/^0//' | tr '[:upper:]' '[:lower:]') }
zle -N _insert_time
bindkey '^]' _insert_time

# Edit a chflags-uchg-protected file: unlock, edit, relock. Used for protected
# research files like those under ~/ai/content-server/. Quoted name because `!`
# is special in zsh; safe to call as `edit! file` at the prompt.
'edit!'() {
  if [[ -z "$1" ]]; then
    echo "usage: edit! <file>" >&2
    return 1
  fi
  chflags nouchg "$1" && chmod u+w "$1" && ${EDITOR:-vim} "$1"
  local status=$?
  chmod a-w "$1" && chflags uchg "$1"
  return $status
}
