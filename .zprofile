export GO_PATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PNPM_HOME="$HOME/Library/pnpm"

# argc-completions
export ARGC_COMPLETIONS_ROOT="$HOME/.argc-completions"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"

# Add Homebrew to PATH variable (for Apple Silicon and Intel Macs)
if [[ $(uname -m) == "arm64" ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  eval "$(/usr/local/bin/brew shellenv)"
fi

export PATH="$ARGC_COMPLETIONS_ROOT/bin:$GO_PATH:$JETBRAINS_PATH:$PNPM_HOME:$PATH"
