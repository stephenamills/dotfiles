# This file depends on four modules installed from the Brewfile:
# asdf pure zsh-autocomplete zsh-autosuggestions zsh-syntax-highlighting

# If the `brew` command exists
if type brew &>/dev/null; then
  # Load dependencies installed by Homebrew

  # asdf version manager
  source $(brew --prefix)/opt/asdf/libexec/asdf.sh

  # Pure terminal prompt
  autoload -U promptinit; promptinit
  prompt pure

  # zsh-autocomplete (automatically displays completions for commands in real-time)
  source $(brew --prefix)/share/zsh-autocomplete/zsh-autocomplete.plugin.zsh

  # zsh-autosuggestions (suggests commands from history)
  source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  # zsh-syntax-highlighting (highlighting for zsh syntax while typing)
  source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# This depends on the sigoden/argc-completions repo being cloned to $HOME/.argc-completions
if [ -d "$HOME/.argc-completions" ]; then
  # To add completions for only the specified command, modify next line e.g. argc_scripts=( cargo git )
  argc_scripts=( $(ls -p -1 "$ARGC_COMPLETIONS_ROOT/completions" | sed -n 's/\.sh$//p') )
  source <(argc --argc-completions zsh $argc_scripts)
fi

# Invoked as a command to install an app
function bi() {
  brew install --no-quarantine "$@"
}

# Invoked as a command to install a .pkg file
function ins() {
  for pkg in "$@"; do
    sudo installer -pkg "$pkg" -target /
  done
}

# Invoked as a command to sign a bundle
function prep() {
  sudo xattr -r -d com.apple.quarantine "$1"
  sudo codesign --force --deep --sign - "$1"
}

# Lazy loading for bloated Google Cloud SDK
function gcloud() {
    # Check if Google Cloud SDK is installed
    if [ -d "$(brew --prefix)/share/google-cloud-sdk" ]; then
        # Source the SDK components
        source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
        source "$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"
        
        # Remove the function definition after it's called once
        unset -f gcloud
        
        # Proceed with the original gcloud command
        command gcloud "$@"
    else
        echo "Google Cloud SDK is not installed."
    fi
}
