export ARGC_COMPLETIONS_ROOT="$HOME/.argc-completions"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export GOPATH="$HOME/go"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PIPX_PATH="$HOME/.local/bin"
export PNPM_HOME="$HOME/Library/pnpm"
export RUST_PATH="$HOME/.cargo/bin"

export LESSHISTFILE=- # Disable history file for less

# Add Homebrew to PATH variable
# If the machine is Apple Silicon, use Homebrew's different default path
if [[ $(uname -m) == "arm64" ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  # If the machine is Intel, use Homebrew's different default path
  eval "$(/usr/local/bin/brew shellenv)"
fi

export PYTHON_PATH="$(brew --prefix python)/libexec/bin" # This must be executed after the Homebrew shellenv command
export PATH="$PYTHON_PATH:$ARGC_COMPLETIONS_ROOT/bin:$GOPATH/bin:$JETBRAINS_PATH:$PIPX_PATH:$PNPM_HOME:$RUST_PATH:$PATH"
