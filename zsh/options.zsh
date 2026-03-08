export RIPGREP_CONFIG_PATH="$HOME/.ripgreprc"

export CLICOLOR=1
export LSCOLORS="ExFxcxdxbxegedabagacad"
export LS_COLORS="di=94:ln=95:so=32:pi=33:ex=91:bd=30;46:cd=30;43:su=30;41:sg=30;46:tw=30;42:ow=30;43:"

# History
HISTFILE=$HOME/.zsh_history
HISTSIZE=50000
SAVEHIST=100000
setopt append_history
setopt extended_history
setopt inc_append_history
setopt share_history
setopt hist_expire_dups_first
setopt hist_ignore_dups
setopt hist_ignore_all_dups
setopt hist_ignore_space
setopt hist_reduce_blanks
setopt hist_find_no_dups
setopt hist_save_no_dups

# Navigation
setopt auto_cd
setopt auto_name_dirs
setopt auto_pushd
setopt pushd_ignore_dups
setopt pushdminus

# Completion
setopt auto_list
setopt auto_remove_slash
setopt always_to_end
setopt complete_in_word

# Correction
setopt correct
setopt nocorrectall

# Prompt
setopt prompt_subst
setopt transient_rprompt

# Help
unalias run-help 2>/dev/null
autoload run-help
[[ -d /opt/homebrew/share/zsh/helpfiles ]] && HELPDIR=/opt/homebrew/share/zsh/helpfiles
