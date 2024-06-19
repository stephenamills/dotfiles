# My dotfiles

This collection contains my shell configuration files and installed Homebrew and npm packages.

This is 150 packages, just so you know.

This is really for personal use but here in case someone finds it useful.

# Usage

Homebrew is required to install dependencies the two shell configuration files rely on.

Clone this repository and copy `.zprofile` and `.zshrc` to your home directory.

Lastly, run the commands below to install:

- The Homebrew packages listed in the `Brewfile`
- The npm packages listed in the `Npmfile`
- The Rust packages listed in the `Rustfile`

```shell
brew bundle install --no-lock

pnpm install -g $(tr '\n' ' ' < Npmfile)

cargo install $(tr '\n' ' ' < Rustfile)
```
