# This file depends on eight packages installed from the Brewfile:
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

# Remove error messages when searching for manual pages
alias man='/usr/bin/man 2>/dev/null'

# Open a Homebrew package in your browser
bh() {
  brew home $@
}

# Open a Rust package in a browser
cb() {
  open "https://crates.io/crates/${1}"
}

# Delete a line from the zsh history file
del() {
  # Delete the line by its line number
  sed -i '' $1d ~/.zsh_history
}

# Example usage:
# open_github_file "cncf/cnf-testbed examples/use_case/external-packet-filtering-on-k8s-nsm-on-packet/README.md"

# Load the Google Cloud SDK – it's too bloated to load everytime the shell starts
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

# Open GitHub files in a browser
# Usage: ghcb <repo1> <file_path1> <repo2> <file_path2> ...
ghcb() {
  while [ "$#" -gt 0 ]; do
    repo=$1
    file_path=$2

    # Determine default branch (main or master)
    default_branch="main"
    if curl --head --silent --fail "https://github.com/$repo/tree/master" >/dev/null; then
      default_branch="master"
    fi

    # Construct URL to the file on GitHub
    url="https://github.com/$repo/blob/$default_branch/$file_path"

    # Shift to the next pair of arguments
    shift 2

    echo "$url"

  done | xargs -n 1 -P 8 open
}

ghgv() {
  gh gist view $@
}

ghge() {
  gh gist edit $@
}

# Open a GitHub repository in the browser
ghrb() {
  xargs -n 1 -P 8 hub browse <<<$@
}

# Search GitHub code
ghsc() {
  gh search code $@
}

# Search GitHub issues
ghsi() {
  gh search issues $@
}

# Search for GitHub issues matching the search terms, and open them all in a browser
# Usage: ghissueb <owner/repo> <search terms>
ghsib() {
  repo=$1

  # Shift the positional parameters down by one, which deletes the first argument in $@
  shift
  gh search issues -R $repo $@ | awk '{ print $2 }' | xargs -P 8 -I {} gh issue view -R $repo {} -w
}

# Search GitHub pull requests
ghspr() {
  gh search prs $@
}

# Search for GitHub repos
ghsr() {
  gh search repos $@
}

# Search for GitHub repos and open each result in a browser
ghsrb() {
  gh search repos $@ | awk '{print $1}' | xargs -n 1 -P 8 hub browse
}

# Open GitHub issues in a browser
# Usage: ghib <owner/repo> <issue1> <issue2> ...
ghib() {
  repo=$1

  shift # This shifts the positional parameters down by one, which deletes the first argument in $@
  for issue in "$@"; do
    # Remove preceding '#' if it exists and construct the URL
    clean_issue=${issue#\#}
    echo "https://github.com/$repo/issues/$clean_issue"
  done | xargs -n 1 -P 8 open
}

# Update local Git repos
gu() {
  gitup -c -t 2
}
alias gitu=gu

# Install .pkg files
ins() {
  for pkg in "$@"; do
    sudo installer -pkg "$pkg" -target /
  done
}

# List an npm package's dependencies
npmdeps() {
  npm view $1 dependencies
}

# Sign a macOS app bundle
prep() {
  sudo xattr -r -d com.apple.quarantine "$1"
  sudo codesign --force --deep --sign - "$1"
}
