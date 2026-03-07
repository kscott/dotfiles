if [[ "$OSTYPE" == darwin* ]]; then
  export BROWSER='open'
fi

export EDITOR=vim
export VISUAL=vim
export PAGER='less'

[[ -z "$LANG" ]] && export LANG='en_US.UTF-8'

# Ensure path arrays do not contain duplicates.
typeset -gU cdpath fpath mailpath path

path=(
  $HOME/.local/bin
  $HOME/bin
  /opt/homebrew/{bin,sbin}
  /usr/local/{bin,sbin}
  $path
)

export LESS='-g -i -M -R -S -w -X -z-4'

if (( $#commands[(i)lesspipe(|.sh)] )); then
  export LESSOPEN="| /usr/bin/env $commands[(i)lesspipe(|.sh)] %s 2>&-"
fi
