export GO_PATH="$HOME/go/bin"
export JETBRAINS_PATH="$HOME/Library/Application Support/JetBrains/Toolbox/scripts"
export PATH="$GO_PATH:$JETBRAINS_PATH:$PATH"

# Add Homebrew to PATH variable
eval "$(/opt/homebrew/bin/brew shellenv)"

# Load asdf version manager
source /opt/homebrew/opt/asdf/libexec/asdf.sh
