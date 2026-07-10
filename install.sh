#!/usr/bin/env zsh
set -e

DOTFILES="$HOME/dotfiles"
BACKUP="$HOME/.dotfiles_backup_$(date +%Y%m%d_%H%M%S)"

# ── Machine type ───────────────────────────────────────────────────────────────

if [[ $1 == "home" ]]; then
  MACHINE="personal"
elif [[ $1 == "work" ]]; then
  MACHINE="work"
else
  echo "What kind of machine is this?"
  echo "  1) Home"
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
mkdir -p $HOME/dev $HOME/bin $HOME/Notes $HOME/logs
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

echo "==> Installing claude-statusline"
if [[ ! -f $HOME/.local/bin/claude-statusline ]]; then
  curl --create-dirs -sSLo ~/.local/bin/claude-statusline \
    "https://github.com/TheoBrigitte/claude-statusline/releases/latest/download/claude-statusline.darwin-arm64"
  chmod +x ~/.local/bin/claude-statusline
  echo "  installed claude-statusline"
else
  echo "  ok  claude-statusline already present"
fi

echo "==> Linking claude-statusline config"
link config/claude-statusline.toml .config/claude-statusline.toml

echo "==> Installing npm global packages"
if ! command -v mmdc &>/dev/null; then
  npm install -g @mermaid-js/mermaid-cli --silent && echo "  installed mmdc" || echo "  failed: mmdc"
else
  echo "  ok  mmdc already present"
fi

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

# ── Personal setup ─────────────────────────────────────────────────────────────

if [[ $MACHINE == "personal" ]]; then
  echo "==> Linking claude-projects (Claude Code memory + session sync)"
  # Separate private repo, not inside $DOTFILES — personal-only, deliberately
  # never touched on a work machine. See kscott/claude-projects.
  if [[ ! -d "$HOME/claude-projects" ]]; then
    git clone git@github.com:kscott/claude-projects.git "$HOME/claude-projects"
  fi
  mkdir -p "$HOME/.claude"
  if [[ -L "$HOME/.claude/projects" && "$(readlink "$HOME/.claude/projects")" == "$HOME/claude-projects" ]]; then
    echo "  ok  ~/.claude/projects"
  elif [[ -d "$HOME/.claude/projects" && ! -L "$HOME/.claude/projects" ]]; then
    # Fresh machine already ran Claude Code once (real local content exists)
    # — merge it in before linking, rather than clobbering either side.
    cp -R "$HOME/.claude/projects/." "$HOME/claude-projects/"
    rm -rf "$HOME/.claude/projects"
    ln -s "$HOME/claude-projects" "$HOME/.claude/projects"
    echo " link ~/.claude/projects -> ~/claude-projects (merged existing content)"
  else
    ln -sf "$HOME/claude-projects" "$HOME/.claude/projects"
    echo " link ~/.claude/projects -> ~/claude-projects"
  fi

  echo "==> Cloning workbench (~/ai — personal Claude Code workspace)"
  # Separate private repo, not inside $DOTFILES — personal-only, deliberately
  # never touched on a work machine (work ~/ai stays local-only). See kscott/workbench.
  if [[ -d "$HOME/ai/.git" ]]; then
    echo "  ok  ~/ai"
  elif [[ -d "$HOME/ai" ]]; then
    # Fresh machine already has a ~/ai (e.g. Claude Code ran once and created
    # .claude/settings.local.json) — merge it in rather than clobbering either side.
    git clone git@github.com:kscott/workbench.git "$HOME/ai.tmp"
    cp -R "$HOME/ai/." "$HOME/ai.tmp/"
    rm -rf "$HOME/ai"
    mv "$HOME/ai.tmp" "$HOME/ai"
    echo "  cloned ~/ai (merged existing content)"
  else
    git clone git@github.com:kscott/workbench.git "$HOME/ai"
    echo "  cloned ~/ai"
  fi

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

  printf "Install optional casks/tools (music-tagging tools, Discord, Calibre, etc.)? [y/N] "
  read optional_choice
  if [[ $optional_choice == [yY]* ]]; then
    echo "==> Installing Homebrew packages (personal, optional)"
    brew bundle --file="$DOTFILES/Brewfile.personal.optional"
  else
    echo "  skipped optional packages (see Brewfile.personal.optional)"
  fi

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

  echo "==> Linking ~/Sites files"
  # ~/Sites is a protected macOS special folder that always exists —
  # link files into it individually, don't try to create or replace
  # the folder itself.
  link sites/homelab.html        Sites/homelab.html
  link sites/index.html          Sites/index.html
  link sites/newtype.css         Sites/newtype.css
  link sites/brain-in-a-jar.jpg  Sites/brain-in-a-jar.jpg
  link sites/favicon.ico         Sites/favicon.ico

  echo "==> Linking bin scripts"
  mkdir -p $HOME/bin
  link bin/brew-update.sh             bin/brew-update.sh
  link bin/claude-status.sh           bin/claude-status.sh
  link bin/claude-session-pull        bin/claude-session-pull
  link bin/claude-dotfiles-check      bin/claude-dotfiles-check
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
  link bin/sed                       bin/sed
fi

# ── Work setup ─────────────────────────────────────────────────────────────────

if [[ $MACHINE == "work" ]]; then
  echo "==> Linking bin scripts (work)"
  mkdir -p $HOME/bin
  link bin/backup-folder.py       bin/backup-folder.py
  link bin/claude-statusline-git  bin/claude-statusline-git
  link bin/brew-update.sh         bin/brew-update.sh

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
echo "  3. SSH key: gh auth login creates one — or manually: ssh-keygen -t ed25519 -C 'ken@optikos.net'"
echo "  4. iTerm2: quit iTerm2, run: python3 ~/bin/fix-claude-iterm-colors.py, then relaunch"
echo "  5. Get Clear CLI: gh release download --repo kscott/get-clear --pattern 'get-clear.pkg' --dir /tmp && open /tmp/get-clear.pkg"

if [[ $MACHINE == "work" ]]; then
  echo ""
  echo "Next steps (work Mac):"
  echo "  6. Set up manager-bot:"
  echo "       git clone git@github.com:Ibotta/manager-bot.git ~/dev/manager-bot"
  echo "       git -C ~/dev/manager-bot checkout kscott/manager-bot-content-customized"
  echo "       # Unlock team.yaml: open Passwords, find 'git-crypt manager-bot',"
  echo "       # copy the password, then run:"
  echo "       echo '<paste key>' | base64 -d > /tmp/mgr-bot.key"
  echo "       git -C ~/dev/manager-bot git-crypt unlock /tmp/mgr-bot.key && rm /tmp/mgr-bot.key"
  echo "       cd ~/dev/manager-bot && uv sync"
  echo "       uv run scripts/setup_google_auth.py"
fi

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
fi

echo ""
if [[ -d $BACKUP ]]; then
  echo "Backed up old files to: $BACKUP"
fi

echo ""
echo "Apps to install manually:"
echo ""
glow "$DOTFILES/apps.$MACHINE.md" 2>/dev/null || cat "$DOTFILES/apps.$MACHINE.md"
