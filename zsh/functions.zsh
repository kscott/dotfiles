# Personal shell functions

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
