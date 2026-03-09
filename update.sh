#!/usr/bin/env zsh
# update.sh — run after git pull to apply dotfile changes
# Safe to run automatically: linking and vim plugins only.
# Does NOT run brew bundle, ruby-install, or LaunchAgents.

set -e

DOTFILES="$HOME/dotfiles"
BACKUP="$HOME/.dotfiles_backup_$(date +%Y%m%d_%H%M%S)"

link() {
  local src="$DOTFILES/$1" dst="$HOME/$2"
  if [[ -e $dst || -L $dst ]]; then
    if [[ -L $dst && $(readlink $dst) == $src ]]; then
      echo "  ok  ~/$2"
      return
    fi
    mkdir -p $BACKUP/$(dirname $2)
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

echo "==> Linking ssh config"
mkdir -p ~/.ssh
chmod 700 ~/.ssh
link ssh/config .ssh/config

echo "==> Linking tool configs"
link gemrc      .gemrc
link ripgreprc  .ripgreprc
link rspec      .rspec
mkdir -p ~/.config/doing
link config/doing/config.yml .config/doing/config.yml

echo "==> Linking ~/.config"
mkdir -p ~/.config
link config/gh .config/gh

echo "==> Linking git config"
link git/gitconfig  .gitconfig
link git/gitignore  .gitignore
link git/githelpers .githelpers
link git/gitmessage .gitmessage

echo "==> Linking vim config"
link vim/vimrc .vimrc

echo "==> Linking bin scripts"
mkdir -p $HOME/bin
link bin/claude-status.sh          bin/claude-status.sh
link bin/fix-claude-iterm-colors.py bin/fix-claude-iterm-colors.py

echo "==> Updating vim plugins"
vim +PlugUpdate +qall

echo "Done."
if [[ -d $BACKUP ]]; then
  echo "Backed up changed files to: $BACKUP"
fi
