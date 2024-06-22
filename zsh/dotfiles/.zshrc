# This file depends on four modules installed from the Brewfile:
# asdf pure zsh-autocomplete zsh-autosuggestions zsh-syntax-highlighting

# If the `brew` command exists
if type brew &>/dev/null; then
  # Load dependencies installed by Homebrew

  # asdf version manager
  source $(brew --prefix)/opt/asdf/libexec/asdf.sh

  # direnv (automatically loads/unloads environment variables)
  eval "$(direnv hook zsh)"

  # zsh Pure extension (aesthetically pleasing terminal prompt)
  autoload promptinit
  promptinit
  prompt pure

  # zsh-autocomplete extension (automatically displays completions for commands in real-time)
  source $(brew --prefix)/share/zsh-autocomplete/zsh-autocomplete.plugin.zsh

  # zsh-autosuggestions extension (suggests commands from history)
  source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  # zsh-syntax-highlighting extension (syntax highlighting in real-time while typing)
  source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# The .argc-completions git submodule must be copied to $HOME/.argc-completions
if [ -d "$HOME/.argc-completions" ]; then
  # Store the name of each completion shell script in an array
  argc_scripts=( $(ls -p -1 "$ARGC_COMPLETIONS_ROOT/completions" | sed -n 's/\.sh$//p') )
  source <(argc --argc-completions zsh $argc_scripts)
fi

# Customizing zsh autocompletion menu colors with zstyle pattern globbing:
# =(#b): Pattern matches follow.
# *: Matches command names/options before --.
# (-- *): Matches --, a space, and the description after the space.
# =color1=color2: color2 for matched pattern, color1 for others. 35=magenta, 90=light gray.
# Adapted from online examples. https://github.com/ohmyzsh/ohmyzsh/issues/9728#issuecomment-1025890246 and https://superuser.com/a/1200812
zstyle ':completion:*' list-colors '=(#b)*(-- *)=35=90'

# Command to install an app
bi() {
  brew install --no-quarantine "$@"
}

# Command to commit changes to a git repository
gitc() {
  printf 'Enter commit message: ' && read msg && git add . && git commit -m \"$msg\" && git push
}

# Same command to commit changes to a git repository
gc() {
  printf 'Enter commit message: ' && read msg && git add . && git commit -m \"$msg\" && git push
}

# Command to install a .pkg file
ins() {
  for pkg in "$@"; do
    sudo installer -pkg "$pkg" -target /
  done
}

# Command to sign a bundle
prep() {
  sudo xattr -r -d com.apple.quarantine "$1"
  sudo codesign --force --deep --sign - "$1"
}

# Lazy loading for bloated Google Cloud SDK
gcloud() {
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