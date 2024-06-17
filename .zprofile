export GO_PATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PNPM_HOME="$HOME/Library/pnpm"

# argc-completions
export ARGC_COMPLETIONS_ROOT="$HOME/.argc-completions"
export ARGC_COMPLETIONS_PATH="$ARGC_COMPLETIONS_ROOT/completions"

# Add Homebrew to PATH variable
eval "$(/usr/local/bin/brew shellenv)"

export PATH="$ARGC_COMPLETIONS_ROOT/bin:$GO_PATH:$JETBRAINS_PATH:$PNPM_HOME:$PATH"
