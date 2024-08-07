# My dotfiles

This collection contains my shell configuration files and command and app lists.

This repo is really for personal use but here in case someone finds these useful.

# Usage

Homebrew is required to install dependencies the two shell configuration files rely on.

Clone this repository and copy `.zprofile` and `.zshrc` to your home directory.

Lastly, run the commands below to install:

- The Homebrew packages listed in the `Brewfile`
- The Go packages in the `Gofile`
- The JavaScript packages in the `Javascriptfile`
- The Python packages in the `Pythonfile`
- The Rust packages in the `Rustfile`
- The Swift packages in the `Swiftfile`
- The Dotnet packages in the `Dotnetfile`

```shell
brew bundle install --no-lock
xargs -n 1 go install < Gofile
pnpm install -g $(tr '\n' ' ' < Javascriptfile)
xargs -n 1 pipx install < Pythonfile
cargo-binstall -y $(tr '\n' ' ' < Rustfile)
mint install $(tr '\n' ' ' < Swiftfile)
xargs -n 1 dotnet tool install -g < Dotnetfile
```
