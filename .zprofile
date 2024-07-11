# Adjusts path for Homebrew based on architecture.
[[ $(uname -m) == "arm64" ]] && eval "$(/opt/homebrew/bin/brew shellenv)" || eval "$(/usr/local/bin/brew shellenv)"

export ARGC_COMPLETIONS_ROOT="$HOME/.argc"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export LESSHISTFILE=- # Disables unsolicited creation of a history file by less in the home directory.

export GOPATH="$HOME/go"
export JAVA_HOME="$(brew --prefix openjdk)/bin"
export NODE_PATH="$(brew --prefix node@20)/bin" # Sets LTS Node.js version in $PATH, overriding unstable versions.
export PIPX_PATH="$HOME/.local/bin"
export PNPM_HOME="$HOME/Library/pnpm"
export PYTHON_PATH="$(brew --prefix python)/libexec/bin" # Dynamically expands to the path of whatever the latest version of Python is
export RUBY_PATH="$(brew --prefix ruby)/bin"
export RUBYGEMS_PATH_MAJOR_MINOR_ZERO_VERSION=$($HOMEBREW_PREFIX/opt/ruby/bin/ruby -e 'puts RUBY_VERSION.split(".")[0..1].join(".") + ".0"') # Fixes macOS Ruby conflict and aligns Homebrew gem path with Ruby version (e.g., 3.3.0 for Ruby 3.3.3)
export RUBYGEMS_PATH="$HOMEBREW_PREFIX/lib/ruby/gems/$RUBYGEMS_PATH_MAJOR_MINOR_ZERO_VERSION/bin"
export RUST_PATH="$HOME/.cargo/bin"

export PATH="$ARGC_COMPLETIONS_PATH:$GOPATH/bin:$JAVA_HOME:$JETBRAINS_PATH:$NODE_PATH:$PIPX_PATH:$PNPM_HOME:$PYTHON_PATH:$RUBY_PATH:$RUBYGEMS_PATH:$RUST_PATH:$PATH"
