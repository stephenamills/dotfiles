# This file depends on seven modules installed from the Brewfile:
# argc asdf pure zsh-autocomplete zsh-autopair zsh-autosuggestions zsh-syntax-highlighting

# The .argc-completions git submodule must be copied to $HOME/.argc-completions
if [ -d "$HOME/.argc-completions" ]; then
  # Store the name of each completion shell script in an array
  argc_scripts=( $(ls -p -1 "$ARGC_COMPLETIONS_ROOT/completions" | sed -n 's/\.sh$//p') )
  source <(argc --argc-completions zsh $argc_scripts)
fi


# If the `brew` command exists
if type brew &>/dev/null; then
  # Read in the files installed by Homebrew

  # asdf version manager
  source $(brew --prefix)/opt/asdf/libexec/asdf.sh

  # direnv (automatically loads/unloads environment variables)
  eval "$(direnv hook zsh)"

  # zsh-autocomplete extension (automatically displays completions for commands in real-time)
  source $(brew --prefix)/share/zsh-autocomplete/zsh-autocomplete.plugin.zsh

  # zsh-autopair extension (automatically inserts matching brackets, quotes, etc.)
  source $(brew --prefix)/share/zsh-autopair/autopair.zsh

  # zsh-autosuggestions extension (suggests previously typed command lines from history)
  source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  # zsh pure extension (aesthetically pleasing terminal prompt)
  autoload promptinit
  promptinit
  prompt pure

  # zsh-syntax-highlighting extension (syntax highlighting in real-time while typing)
  source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi


# The following obscure line customizes colors of the text in the zsh autocompletion menu using zstyle's pattern matching syntax:
# =(#b): Pattern matches follow.
# *: Matches command names or options before --.
# (-- *): Matches --, a space, and the description text after the space.
# =color1=color2: color2 is applied to the matched pattern, color1 to everything else. 35=magenta, 90=light gray.
# Adapted from online examples. See https://github.com/ohmyzsh/ohmyzsh/issues/9728#issuecomment-1025890246 and https://superuser.com/a/1200812.
zstyle ':completion:*' list-colors '=(#b)*(-- *)=35=90'


# The following are utility functions I use at the command line:

# Loads the Google Cloud SDK – it's too bloated to load when the shell starts
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

# Commits changes to a git repository
gitc() {
  printf 'Enter commit message: ' && read msg && git add . && git commit -m $msg && git push
}

# Installs multiple .pkg files
ins() {
  for pkg in "$@"; do
    sudo installer -pkg "$pkg" -target /
  done
}

# Signs a macOS app bundle
prep() {
  sudo xattr -r -d com.apple.quarantine "$1"
  sudo codesign --force --deep --sign - "$1"
}