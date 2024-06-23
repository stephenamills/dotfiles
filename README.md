# My dotfiles

This collection contains my shell configuration files and lists of commands and apps.

This is 150 packages. It's really for personal use but here in case someone finds it useful.

# Usage

Homebrew is required to install dependencies the two shell configuration files rely on.

Clone this repository and copy `.zprofile` and `.zshrc` to your home directory.

Lastly, run the commands below to install:

- The Homebrew packages listed in the `Brewfile`
- The Go packages in the `Gofile`
- The Rust packages in the `Rustfile`
- The JavaScript packages in the `Npmfile`

```shell
brew bundle install --no-lock
cargo install $(tr '\n' ' ' < Rustfile)
go install $(tr '\n' ' ' < Gofile)
pnpm install -g $(tr '\n' ' ' < Npmfile)
```
