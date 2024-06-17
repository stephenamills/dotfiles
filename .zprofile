export ARGC_COMPLETIONS_ROOT="$HOME/.argc-completions"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"
export GO_PATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PNPM_HOME="$HOME/Library/pnpm"

export LESSHISTFILE=- # Disable history file for less

# Add Homebrew to PATH variable
if [[ $(uname -m) == "arm64" ]]; then
  # If the machine is Apple Silicon, use Homebrew's different default path
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  # If the machine is Intel, use Homebrew's different default path
  eval "$(/usr/local/bin/brew shellenv)"
fi

export PATH="$ARGC_COMPLETIONS_ROOT/bin:$GO_PATH:$JETBRAINS_PATH:$PNPM_HOME:$PATH"
