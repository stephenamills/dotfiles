export ARGC_COMPLETIONS_ROOT="$HOME/.argc-completions"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export GOPATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PNPM_HOME="$HOME/Library/pnpm"
export RUST_PATH="$HOME/.cargo/bin"

export LESSHISTFILE=- # Disable history file for less

# Add Homebrew to PATH variable
if [[ $(uname -m) == "arm64" ]]; then
  # If the machine is Apple Silicon, use Homebrew's different default path
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  # If the machine is Intel, use Homebrew's different default path
  eval "$(/usr/local/bin/brew shellenv)"
fi

export PATH="$ARGC_COMPLETIONS_ROOT/bin:$GOPATH:$JETBRAINS_PATH:$PNPM_HOME:$RUST_PATH:$PATH"
