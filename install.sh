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

echo "==> Creating standard directories"
mkdir -p $HOME/dev $HOME/bin $HOME/Notes
mkdir -p "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Productivity"

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

echo "==> Setting up Ruby"
CHRUBY_SH=""
for _d in /opt/homebrew/share/chruby /usr/local/share/chruby; do
  [[ -f $_d/chruby.sh ]] && CHRUBY_SH="$_d/chruby.sh" && break
done

if [[ -n $CHRUBY_SH ]]; then
  source $CHRUBY_SH
  if [[ -z "$(ls ~/.rubies/ 2>/dev/null)" ]]; then
    echo "  Installing latest Ruby (this may take a few minutes)..."
    ruby-install ruby
  else
    echo "  ok  rubies already present"
  fi
  latest_ruby=$(ls ~/.rubies/ | grep "^ruby-" | sort -V | tail -1)
  if [[ -n $latest_ruby ]]; then
    chruby $latest_ruby
    echo $latest_ruby | sed 's/ruby-//' > ~/.ruby-version
    echo "  Using $latest_ruby"
    gem install git-smart doing --no-document
  fi
else
  echo "  skipped (chruby not found — run brew bundle first)"
fi

echo "==> Installing vim plugins"
vim +PlugUpdate +qall

echo "==> Linking bin scripts"
mkdir -p $HOME/bin
link bin/claude-status.sh   bin/claude-status.sh
link bin/fix-claude-iterm-colors.py bin/fix-claude-iterm-colors.py

echo ""
echo "Done. Open a new shell to pick up the changes."
echo ""
echo "Next steps:"
echo "  1. Run: gh auth login   (set up personal GitHub credentials)"
echo "  2. Add any personal tokens to ~/.zsh/secrets.zsh"
echo "  3. Set up SSH key for this machine:"
echo "       ssh-keygen -t ed25519 -C 'ken@optikos.net'"
echo "       gh ssh-key add ~/.ssh/id_ed25519.pub --title \"\$(scutil --get ComputerName)\""
echo "  4. iTerm2: quit iTerm2, run: python3 ~/bin/fix-claude-iterm-colors.py, then relaunch"
echo "     (patches Claude profile colors/font and registers gruvbox color presets)"
echo "  5. Reminders CLI: gh repo clone kscott/reminders-cli ~/dev/reminders-cli && ~/dev/reminders-cli/reminders setup"
echo ""
if [[ -d $BACKUP ]]; then
  echo "Backed up old files to: $BACKUP"
fi
