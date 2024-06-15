# This file depends on three modules installed from the Brewfile:
# zsh-autosuggestions zsh-completions zsh-syntax-highlighting

# Check if the `brew` command exists
if type brew &>/dev/null; then
  # Initialize shell modules installed in the Brewfile

  # Pure terminal prompt module
  fpath+=$(brew --prefix)/share/zsh/site-functions # Fixes the module not finding anything (https://github.com/sindresorhus/pure/issues/584#issuecomment-989054653)
  autoload -U promptinit; promptinit
  prompt pure

  # Zsh-completions tab autocompletion module (requires pressing the tab key)
  zstyle ':completion:*' list-prompt '' # Disables annoying confirmation message that appears when doing a tab completion (https://unix.stackexchange.com/a/30092)
  fpath+=$(brew --prefix)/share/zsh-completions
  autoload -Uz compinit; compinit
  compaudit | xargs chmod g-w # Fixes incorrect permissions on folders (https://github.com/zsh-users/zsh-completions/issues/680#issuecomment-612960481)

  # Zsh-autosuggestions tabless autocompletion module (does not require pressing the tab key)
  source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  # Zsh-syntax-highlighting module
  source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi


# Invoked as a command to install an app
function bi() {
  brew install --no-quarantine "$1"
}

# Invoked as a command to install a .pkg file
function ins() {
  sudo installer -pkg "$1" -target /
}

# Invoked as a command to sign a bundle
function prep() {
  sudo xattr -r -d com.apple.quarantine "$1"
  sudo codesign --force --deep --sign - "$1"
}
