#!/usr/bin/env zsh
set -e

DOTFILES="$HOME/dotfiles"
BACKUP="$HOME/.dotfiles_backup_$(date +%Y%m%d_%H%M%S)"

link() {
  local src="$DOTFILES/$1" dst="$HOME/$2"

  # If destination exists and is not already our symlink, back it up
  if [[ -e $dst || -L $dst ]]; then
    if [[ -L $dst && $(readlink $dst) == $src ]]; then
      echo "  ok  ~/$2"
      return
    fi
    mkdir -p $BACKUP
    mv $dst $BACKUP/$2
    echo "  bak ~/$2 -> $BACKUP/$2"
  fi

  ln -s $src $dst
  echo " link ~/$2 -> $src"
}

echo "==> Linking dotfiles"
link zshenv   .zshenv
link zprofile .zprofile
link zshrc    .zshrc
link zlogin   .zlogin
link zlogout  .zlogout

echo "==> Linking ~/.zsh"
link zsh .zsh

echo "==> Creating cache directory"
mkdir -p $DOTFILES/zsh/cache

echo "==> Creating secrets file (if missing)"
[[ -f $DOTFILES/zsh/secrets.zsh ]] || cp $DOTFILES/zsh/secrets.zsh.example $DOTFILES/zsh/secrets.zsh 2>/dev/null || true

echo ""
echo "Done. Open a new shell to pick up the changes."
echo ""
echo "Next steps:"
echo "  1. Run: gh auth login   (set up personal GitHub credentials)"
echo "  2. Run: git config --global user.name  'Your Name'"
echo "  3. Run: git config --global user.email 'you@example.com'"
echo "  4. Add any personal tokens to ~/.zsh/secrets.zsh"
echo ""
if [[ -d $BACKUP ]]; then
  echo "Backed up old files to: $BACKUP"
fi
