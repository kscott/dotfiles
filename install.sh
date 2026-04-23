#!/usr/bin/env zsh
set -e

DOTFILES="$HOME/dotfiles"
BACKUP="$HOME/.dotfiles_backup_$(date +%Y%m%d_%H%M%S)"

# ── Machine type ───────────────────────────────────────────────────────────────

if [[ $1 == "personal" ]]; then
  MACHINE="personal"
elif [[ $1 == "work" ]]; then
  MACHINE="work"
else
  echo "What kind of machine is this?"
  echo "  1) Personal"
  echo "  2) Work"
  printf "Choice: "
  read choice
  case $choice in
    1) MACHINE="personal" ;;
    2) MACHINE="work" ;;
    *) echo "Unknown choice — defaulting to work"; MACHINE="work" ;;
  esac
fi

echo ""
echo "Installing for: $MACHINE Mac"
echo ""

# ── Helpers ────────────────────────────────────────────────────────────────────

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

# ── Core setup (all machines) ──────────────────────────────────────────────────

echo "==> Creating standard directories"
mkdir -p $HOME/dev $HOME/bin $HOME/Notes
mkdir -p "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Productivity"
[[ -L $HOME/iCloud ]] || ln -s "$HOME/Library/Mobile Documents/com~apple~CloudDocs" $HOME/iCloud

echo "==> Installing Homebrew packages (core)"
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

echo "==> Linking Claude config"
mkdir -p ~/.claude
link claude-skills         .claude/skills
link claude/settings.json  .claude/settings.json
link claude/CLAUDE.md      .claude/CLAUDE.md

echo "==> Linking tool configs"
link gemrc      .gemrc
link ripgreprc  .ripgreprc
link rspec      .rspec
mkdir -p ~/.config/doing
link config/doing/config.yml .config/doing/config.yml
link config/starship.toml    .config/starship.toml

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

echo "==> Installing crontab"
crontab $DOTFILES/crontab
echo "  installed"

# ── Personal setup ─────────────────────────────────────────────────────────────

if [[ $MACHINE == "personal" ]]; then
  echo "==> Installing LaunchAgents"
  mkdir -p "$HOME/Library/LaunchAgents"
  for plist in $DOTFILES/launchagents/personal/*.plist; do
    name=$(basename $plist)
    dst="$HOME/Library/LaunchAgents/$name"
    cp $plist $dst
    launchctl unload $dst 2>/dev/null || true
    launchctl load $dst
    echo "  loaded $name"
  done

  echo "==> Installing Homebrew packages (personal)"
  brew bundle --file="$DOTFILES/Brewfile.personal"

  echo "==> Installing Get Clear zsh completions"
  mkdir -p "$HOME/.local/share/zsh/site-functions"
  for tool in reminders calendar contacts mail sms; do
    curl -fsSL -o "$HOME/.local/share/zsh/site-functions/_${tool}" \
      "https://raw.githubusercontent.com/kscott/get-clear/main/completions/_${tool}" 2>/dev/null \
      && echo "  _${tool}" || echo "  failed: _${tool}"
  done

  echo "==> Linking Get Clear dev builds (if repos present)"
  mkdir -p "$HOME/bin"
  for tool in reminders calendar contacts mail sms; do
    src="$HOME/dev/${tool}-cli/.build/release/${tool}-bin"
    if [[ -f "$src" ]]; then
      ln -sf "$src" "$HOME/bin/$tool"
      echo "  linked $tool"
    fi
  done

  echo "==> Linking bin scripts"
  mkdir -p $HOME/bin
  link bin/brew-update.sh             bin/brew-update.sh
  link bin/claude-status.sh           bin/claude-status.sh
  link bin/fix-claude-iterm-colors.py bin/fix-claude-iterm-colors.py
  link bin/transcribe                 bin/transcribe
  link bin/sort-downloads.sh          bin/sort-downloads.sh
  link bin/trinity-reminders          bin/trinity-reminders
  link bin/plex-export                bin/plex-export
  link bin/audiobook-join.py          bin/audiobook-join.py
  link bin/audiobook-tags.py          bin/audiobook-tags.py
  link bin/audiobook-rename.py        bin/audiobook-rename.py
  link bin/audiobook-calibre.py       bin/audiobook-calibre.py
  link bin/music-blurbs.py            bin/music-blurbs.py
  link bin/music-gap.py               bin/music-gap.py
  link bin/music-rank.py              bin/music-rank.py
  link bin/archive-session-log.py    bin/archive-session-log.py
fi

# ── Work setup ─────────────────────────────────────────────────────────────────

if [[ $MACHINE == "work" ]]; then
  echo "==> Linking bin scripts (work)"
  mkdir -p $HOME/bin
  link bin/backup-ai-folder.py    bin/backup-ai-folder.py
  link bin/backup-notes-folder.py bin/backup-notes-folder.py

  echo "==> Installing LaunchAgents"
  mkdir -p "$HOME/Library/LaunchAgents"
  for plist in $DOTFILES/launchagents/work/*.plist; do
    name=$(basename $plist)
    dst="$HOME/Library/LaunchAgents/$name"
    cp $plist $dst
    launchctl unload $dst 2>/dev/null || true
    launchctl load $dst
    echo "  loaded $name"
  done
fi

# ── Next steps ─────────────────────────────────────────────────────────────────

echo ""
echo "Done. Open a new shell to pick up the changes."
echo ""
echo "Next steps (all machines):"
echo "  1. Run: gh auth login"
echo "  2. Add any personal tokens to ~/.zsh/secrets.zsh"
echo "  3. Set up SSH key:"
echo "       ssh-keygen -t ed25519 -C 'ken@optikos.net'"
echo "       gh ssh-key add ~/.ssh/id_ed25519.pub --title \"\$(scutil --get ComputerName)\""
echo "  4. iTerm2: quit iTerm2, run: python3 ~/bin/fix-claude-iterm-colors.py, then relaunch"
echo "  5. Reminders CLI: gh repo clone kscott/reminders-cli ~/dev/reminders-cli && ~/dev/reminders-cli/reminders setup"

if [[ $MACHINE == "personal" ]]; then
  echo ""
  echo "Next steps (personal Mac):"
  echo "  6. Plex config: create ~/.config/plex/config with:"
  echo "       PLEX_SERVER=http://<plex-ip>:32400"
  echo "       PLEX_TOKEN=<token>"
  echo "       PLEX_SECTION_MOVIES=<section-id>"
  echo "       PLEX_SECTION_TV=<section-id>"
  echo "       PLEX_SECTION_MUSIC=<section-id>"
  echo "     (token: on Plex Mac run: defaults read com.plexapp.plexmediaserver PlexOnlineToken)"
  echo "  7. SSH to Plex: add 'Host plex' to ~/.ssh/config, then:"
  echo "       ssh-copy-id -i ~/.ssh/id_ed25519.pub ken@<plex-ip>"
  echo "  8. Transmission: Preferences → Transfers → Management →"
  echo "       'Call script when torrent is complete' → ~/bin/sort-downloads.sh"
  echo "  9. whisper model: place ggml-medium.en.bin at ~/.whisper/"
fi

echo ""
if [[ -d $BACKUP ]]; then
  echo "Backed up old files to: $BACKUP"
fi

echo ""
echo "Apps to install manually:"
echo ""
glow "$DOTFILES/apps.$MACHINE.md" 2>/dev/null || cat "$DOTFILES/apps.$MACHINE.md"
