# Add paths for Homebrew
eval "$(/opt/homebrew/bin/brew shellenv)"

export LESSHISTFILE=- # Disable autocreation of less history file

export ANTIGRAVITY_PATH="/Users/steph/.antigravity/antigravity/bin:$PATH"
export ARGC_COMPLETIONS_ROOT="/Users/steph/.argc"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export JETBRAINS_PATH="/Users/steph/Library/Application Support/JetBrains/Toolbox/scripts"

export BUN_INSTALL="/Users/steph/.bun"
export DOTNET_PATH="/Users/steph/.dotnet/tools"
export GOPATH="/Users/steph/go"
export MINT_PATH="/Users/steph/.mint/bin"
export JAVA_HOME="$(brew --prefix openjdk)/bin"
export NODE_PATH="$(brew --prefix node@24)/bin"
export PYTHON_PATH="$(brew --prefix python)/libexec/bin" # Dynamically expands to the path of whatever the latest version of Python is
export RUBY_PATH="$(brew --prefix ruby)/bin"
export RUBYGEMS_PATH="$($(brew --prefix ruby)/bin/gem env gemdir)/bin" # Causes use of the Homebrew-installed gem command, overriding the old default shipped with macOS
export RUST_PATH="/Users/steph/.cargo/bin"
export UV_PATH="/Users/steph/.local/bin"

export PATH="ANTIGRAVITY_PATH:\
$ARGC_COMPLETIONS_PATH:\
$ARGC_COMPLETIONS_ROOT:\
$BUN_INSTALL/bin:\
$DOTNET_PATH:\
$GOPATH/bin:\
$JAVA_HOME:\
$JETBRAINS_PATH:\
$MINT_PATH:\
$NODE_PATH:\
$UV_PATH:\
$PYTHON_PATH:\
$RUBY_PATH:\
$RUBYGEMS_PATH:\
$RUST_PATH:\
$PATH"
