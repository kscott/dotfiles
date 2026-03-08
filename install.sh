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

echo "==> Installing Homebrew packages"
brew bundle --file="$DOTFILES/Brewfile"

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

echo "==> Linking vim config"
link vim/vimrc .vimrc

echo "==> Installing vim-plug (if missing)"
if [[ ! -f $HOME/.vim/autoload/plug.vim ]]; then
  curl -fLo ~/.vim/autoload/plug.vim --create-dirs \
    https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
  echo "  installed vim-plug"
else
  echo "  ok  vim-plug already present"
fi

echo "==> Creating vim runtime directories"
mkdir -p ~/.vim/{undo,backup,swap}

echo "==> Linking bin scripts"
mkdir -p $HOME/bin
link bin/claude-status.sh   bin/claude-status.sh
link bin/fix-claude-iterm-colors.py bin/fix-claude-iterm-colors.py

echo ""
echo "Done. Open a new shell to pick up the changes."
echo ""
echo "Next steps:"
echo "  1. Run: gh auth login   (set up personal GitHub credentials)"
echo "  2. Run: git config --global user.name  'Your Name'"
echo "  3. Run: git config --global user.email 'you@example.com'"
echo "  4. Add any personal tokens to ~/.zsh/secrets.zsh"
echo "  5. Open vim and run: :PlugInstall"
echo "  6. iTerm2: quit iTerm2, run: python3 ~/bin/fix-claude-iterm-colors.py, then relaunch"
echo "  7. Reminders CLI: gh repo clone kscott/reminders-cli ~/dev/reminders-cli && ~/dev/reminders-cli/reminders setup"
echo ""
if [[ -d $BACKUP ]]; then
  echo "Backed up old files to: $BACKUP"
fi
