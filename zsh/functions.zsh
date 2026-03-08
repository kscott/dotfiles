# Personal shell functions

# Create directory (including parents) and cd into it
mkcd() { mkdir -p "$@" && cd "$@" }
