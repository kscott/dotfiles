# Interesting Dotfiles & Zsh Resources

## Dotfiles
- https://github.com/elementalvoid/dotfiles — well-organized dotfiles to draw inspiration from

## iTerm2 Key Bindings

### Insert current time at cursor
**Settings → Keys → Key Bindings → + → Action: Run Coprocess**
```
/bin/zsh -c "date '+%I:%M%p' | sed 's/^0//' | tr '[:upper:]' '[:lower:]' | tr -d '\n'"
```
Outputs e.g. `3:29pm`. The `tr -d '\n'` strips the trailing newline so it inserts cleanly.

A zsh widget alternative is in `functions.zsh` (`_insert_time`, bound to `Ctrl+]`) — not yet confirmed working.

---

## Zsh Plugins
- https://github.com/onyxraven/zsh-osx-keychain — store/retrieve secrets from macOS Keychain in zsh
- https://github.com/zdharma-continuum/history-search-multi-word — better zsh history search (multi-word)
- https://github.com/zdharma-continuum/zinit — fast zsh plugin manager
