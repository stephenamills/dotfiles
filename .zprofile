export GO_PATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PNPM_PATH="$HOME/Library/pnpm"
export PATH="$GO_PATH:$JETBRAINS_PATH:$PNPM_PATH:$PATH"

# Configure 'brew search --desc' to work without needing --eval-all
export HOMEBREW_EVAL_ALL=1
export HOMEBREW_NO_ENV_HINTS=1

# Add Homebrew to PATH variable
eval "$(/opt/homebrew/bin/brew shellenv)"

# Load asdf version manager
source /opt/homebrew/opt/asdf/libexec/asdf.sh
