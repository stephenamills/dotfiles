# My dotfiles

This collection contains my shell configuration files and installed Homebrew and npm packages.

# Usage

Homebrew is required to install packages that the two shell configuration files depend on.

This is 150 commands, so don't install if you don't want that.

This is all really for personal use but here in case someone finds it useful.

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
