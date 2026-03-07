# Brew completions (hardcoded path avoids slow `brew --prefix` call)
FPATH=/opt/homebrew/share/zsh/site-functions:$FPATH
autoload -Uz compinit
compinit

# Source zsh modules
for _f in aliases functions options; do
  [[ -f $HOME/.zsh/$_f.zsh ]] && source $HOME/.zsh/$_f.zsh
done
unset _f

# Secrets (not tracked by git — personal tokens, etc.)
[[ -f $HOME/.zsh/secrets.zsh ]] && source $HOME/.zsh/secrets.zsh

# NVM (lazy load — only initializes when you first use node/npm/etc.)
export NVM_DIR="$HOME/.nvm"
if [[ -s $NVM_DIR/nvm.sh ]] && (( ! ${+functions[__init_nvm]} )); then
  [[ -s $NVM_DIR/bash_completion ]] && source $NVM_DIR/bash_completion
  _nvm_cmds=(nvm node npm yarn npx)
  __init_nvm() {
    for _c in $_nvm_cmds; do unalias $_c 2>/dev/null; done
    source $NVM_DIR/nvm.sh
    unset _nvm_cmds
    unset -f __init_nvm
  }
  for _c in $_nvm_cmds; do alias $_c="__init_nvm && $_c"; done
  unset _c
fi

# chruby
for _d in /opt/homebrew/share/chruby /usr/local/share/chruby; do
  if [[ -f $_d/chruby.sh ]]; then
    source $_d/chruby.sh
    source $_d/auto.sh
    break
  fi
done
unset _d

# Cache slow eval outputs; cache invalidates automatically when the binary changes
_eval_cache() {
  local cmd=$1 cache=$HOME/.zsh/cache/$1.zsh
  if [[ ! -f $cache || $commands[$cmd] -nt $cache ]]; then
    "$@" >| $cache
  fi
  source $cache
}
(( $+commands[direnv]   )) && _eval_cache direnv hook zsh
(( $+commands[starship] )) && _eval_cache starship init zsh
unset -f _eval_cache

# History substring search
for _f in /opt/homebrew/share/zsh-history-substring-search/zsh-history-substring-search.zsh \
          /usr/local/share/zsh-history-substring-search/zsh-history-substring-search.zsh; do
  [[ -f $_f ]] && { source $_f; break }
done
unset _f

bindkey "^[[A" history-substring-search-up
bindkey "^[[B" history-substring-search-down
