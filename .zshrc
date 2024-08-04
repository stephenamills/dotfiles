# This file depends on seven modules installed from the Brewfile:
# argc asdf direnv pure zsh-autocomplete zsh-autopair zsh-autosuggestions zsh-syntax-highlighting

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

# You must manually create a link from the .argc folder in this repo to $HOME/.argc or this will fail
if [ -d "$HOME/.argc" ]; then
  # Store the name of each completion shell script in an array
  argc_scripts=($(ls -p -1 "$ARGC_COMPLETIONS_ROOT/completions" | sed -n 's/\.sh$//p'))
  source <(argc --argc-completions zsh $argc_scripts)
fi

# The following obscure line customizes colors of the text in the zsh autocompletion menu using zstyle's pattern matching syntax:
# =(#b): Pattern matches follow.
# *: Matches command names or options before --.
# (-- *): Matches --, a space, and the description text after the space.
# =color1=color2: color2 is applied to the matched pattern, color1 to everything else. 35=magenta, 90=light gray.
# Adapted from online examples. See https://github.com/ohmyzsh/ohmyzsh/issues/9728#issuecomment-1025890246 and https://superuser.com/a/1200812.
zstyle ':completion:*' list-colors '=(#b)*(-- *)=35=90'

# Add paths for Perl
eval "$(perl -I$HOME/perl5/lib/perl5 -Mlocal::lib=$HOME/perl5)"

# The following are useful functions or aliases for command-line use

# Removes error messages when searching for manual pages
alias man='/usr/bin/man 2>/dev/null'

# Opens a Rust package in a browser
cb() {
  open "https://crates.io/crates/${1}"
}

# Deletes a line from the zsh history file
del() {
  # Delete the line by its line number
  sed -i '' $1d ~/.zsh_history
}

# Opens a GitHub repository in the browser
gb() {
  xargs -n 1 -P 8 hub browse <<< $@
}

# Opens a Homebrew package in a browser
hb() {
  brew home $@
}

# Loads the Google Cloud SDK – it's too bloated to load everytime the shell starts
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

# Searches for GitHub repositories
ghs() {
  gh search repos $@
}

# Searches for GitHub repositories and opens them in the browser
ghsb() {
  gh search repos $@ | awk '{print $1}' | xargs -n 1 -P 8 hub browse
}

# Commits changes to a Git repository
gitp() {
  # Prompt for the commit message
  printf 'Enter commit message: '
  read msg

  # Execute git commands without an additional note
  git add .
  git commit -m "$msg"

  git push
}
alias gitc=gitp

# Commits changes to a Git repository with an optional extended message, accepts 'l' or 'long' as an argument for an extended commit message
gitpl() {
  # Prompt for the commit message
  printf 'Enter commit message: '
  read msg

  # Prompt for the additional note
  printf 'Enter commit note: '
  read msg2

  # Execute git commands with an additional note
  git add .
  git commit -m "$msg" -m "$msg2"

  git push
}

# Updates my local Git repos
gitu() {
  gitup -c -t 2 .
}

# Installs multiple .pkg files
ins() {
  for pkg in "$@"; do
    sudo installer -pkg "$pkg" -target /
  done
}

# Lists dependencies of an npm package
npmd() {
  npm view $1 dependencies
}

# Signs a macOS app bundle
prep() {
  sudo xattr -r -d com.apple.quarantine "$1"
  sudo codesign --force --deep --sign - "$1"
}
