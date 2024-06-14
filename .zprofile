export GO_PATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PNPM_HOME="$HOME/Library/pnpm" # pnpm requires this variable to be named PNPM_HOME
export PATH="$GO_PATH:$JETBRAINS_PATH:$PNPM_HOME:$PATH"

# Add Homebrew to PATH variable
eval "$(/opt/homebrew/bin/brew shellenv)"

# Load asdf version manager
source /opt/homebrew/opt/asdf/libexec/asdf.sh

# Load Google Cloud SDK
source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
source "$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"
