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
  
  # The following obscure zstyle pattern globbing is for customizing the colors of the zsh autocompletion menu

  # =(#b) means pattern matches will come next
  # * matches everything (command names or command options) prior to the --
  # (-- *) matches the -- and a space and everything (description of the command or command option) after that space
  # in =color1 and =color2, color2 references and applies to the matched pattern in parentheses and color1 applies to anything else
  # 35 is magenta and 90 is a lightish gray -- sometimes the contrast is too low but I can't find a limited ANSI terminal color that works better
  # I have zero clue what :*:default does or whether the :default is necessary
  # I fixed and adapted this from https://superuser.com/a/1200812 and https://github.com/ohmyzsh/ohmyzsh/issues/9728#issuecomment-1025890246
  zstyle ':completion:*:default' list-colors '=(#b)*(-- *)=35=90'

  # zsh-autosuggestions extension (suggests commands from history)
  source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  # zsh-syntax-highlighting extension (syntax highlighting in real-time while typing)
  source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# This depends on the sigoden/argc-completions repo being placed at $HOME/.argc-completions
if [ -d "$HOME/.argc-completions" ]; then
  # To add completions for only the specified command, modify next line e.g. argc_scripts=( cargo git )
  argc_scripts=( $(ls -p -1 "$ARGC_COMPLETIONS_ROOT/completions" | sed -n 's/\.sh$//p') )
  source <(argc --argc-completions zsh $argc_scripts)
fi

# Invoked at the command line to install an app
bi() {
  brew install --no-quarantine "$@"
}

# Invoked at the command line to search
bs() {
  brew search --eval-all --desc "$@"
}

# Invoked at the command line to install a .pkg file
ins() {
  for pkg in "$@"; do
    sudo installer -pkg "$pkg" -target /
  done
}

# Invoked at the command line to sign a bundle
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