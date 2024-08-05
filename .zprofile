# Add paths for Homebrew based on architecture.
[[ $(uname -m) == "arm64" ]] && eval "$(/opt/homebrew/bin/brew shellenv)" || eval "$(/usr/local/bin/brew shellenv)"

export ARGC_COMPLETIONS_ROOT="$HOME/.argc"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export LESSHISTFILE=- # Disables unsolicited creation of a history file by less in the home directory.

export DOTNET_PATH="$HOME/.dotnet/tools"
export GOPATH="$HOME/go"
export MINT_PATH="$HOME/.mint/bin"
export JAVA_HOME="$(brew --prefix openjdk)/bin"
export NODE_PATH="$(brew --prefix node@20)/bin"
export PIPX_PATH="$HOME/.local/bin"
export PNPM_HOME="$HOME/Library/pnpm"
export PYTHON_PATH="$(brew --prefix python)/libexec/bin" # Dynamically expands to the path of whatever the latest version of Python is.
export RUBY_PATH="$(brew --prefix ruby)/bin"
export RUBYGEMS_PATH="$($(brew --prefix ruby)/bin/gem env gemdir)/bin" # Use the gem command installed by Homebrew, overriding the old that comes with macOS.
export RUST_PATH="$HOME/.cargo/bin"

export PATH="$ARGC_COMPLETIONS_PATH:""\
$DOTNET_PATH:""\
$GOPATH/bin:""\
$JAVA_HOME:""\
$JETBRAINS_PATH:""\
$MINT_PATH:""\
$NODE_PATH:""\
$PIPX_PATH:""\
$PNPM_HOME:""\
$PYTHON_PATH:""\
$RUBY_PATH:""\
$RUBYGEMS_PATH:""\
$RUST_PATH:""\
$PATH"
