# Personal shell functions

# Create directory (including parents) and cd into it
mkcd() { mkdir -p "$@" && cd "$@" }

# Insert current time at cursor (e.g. 3:15pm) — bound to Ctrl+]
_insert_time() { LBUFFER+=$(date '+%I:%M%p' | sed 's/^0//' | tr '[:upper:]' '[:lower:]') }
zle -N _insert_time
bindkey '^]' _insert_time
