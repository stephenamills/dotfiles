# Adds Homebrew to the path variable – Homebrew on Apple Silicon Macs changed to using the first path for whatever reason
[[ $(uname -m) == "arm64" ]] && eval "$(/opt/homebrew/bin/brew shellenv)" || eval "$(/usr/local/bin/brew shellenv)"

export ARGC_COMPLETIONS_ROOT="$HOME/.argc-completions"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export LESSHISTFILE=- # Disables unsolicited creation of a history file by less in the home directory

export GOPATH="$HOME/go"
export PIPX_PATH="$HOME/.local/bin"
export PNPM_HOME="$HOME/Library/pnpm"
export PYTHON_PATH="$(brew --prefix python)/libexec/bin" # Adds whatever the latest version of Python is to the path variable
export RUST_PATH="$HOME/.cargo/bin"

export PATH="$ARGC_COMPLETIONS_PATH:$GOPATH/bin:$JETBRAINS_PATH:$PIPX_PATH:$PNPM_HOME:$PYTHON_PATH:$RUST_PATH:$PATH"