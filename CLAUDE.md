# dotfiles

Personal dotfiles for Ken Scott. Managed with a simple symlink installer.

## Structure

```
dotfiles/
  install.sh       # run this on a new machine to set everything up
  zshenv           # → ~/.zshenv
  zprofile         # → ~/.zprofile
  zshrc            # → ~/.zshrc
  zlogin           # → ~/.zlogin
  zlogout          # → ~/.zlogout
  zsh/             # → ~/.zsh/  (aliases, functions, options, secrets)
  vim/
    vimrc          # → ~/.vimrc
```

## Conventions

- `install.sh` uses a `link src dst` function that backs up any existing file before symlinking
- Backups go to `~/.dotfiles_backup_<timestamp>/`
- The `link` function is idempotent — safe to re-run
- `~/.zsh/secrets.zsh` is gitignored and never committed

## Adding a new dotfile

1. Move the file into the appropriate place in this repo
2. Add a `link` call in `install.sh`
3. Re-run `./install.sh` to create the symlink on the current machine

## Vim

- Plugin manager: **vim-plug** (`~/.vim/autoload/plug.vim`)
- Plugins install to: `~/.vim/plugged/`
- Colorscheme: **gruvbox** dark (jellybeans and PaperColor also available)
- install.sh installs vim-plug automatically; run `:PlugInstall` in vim after setup
- Requires: `brew install fzf ripgrep`
- Key mappings:
  - `Ctrl-P` — fuzzy file finder (fzf)
  - `<leader>/` — ripgrep project search
  - `Ctrl-N` — toggle NERDTree
  - `<leader>/` — ripgrep search

## Zsh

- Options/aliases/functions split into `~/.zsh/*.zsh` modules
- Secrets (tokens, credentials) go in `~/.zsh/secrets.zsh` (gitignored)
- Completion cache lives in `~/.zsh/cache/` (gitignored)
