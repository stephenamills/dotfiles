# My dotfiles

This collection contains my macOS shell configuration files and installed Homebrew and npm packages.

# Usage

Homebrew is required to install packages that the shell configuration files depend on.

Clone this repository and copy the `.zprofile` and `.zshrc` config files to your home directory.

Install the Homebrew packages from the `Brewfile`:

```
brew bundle install --no-lock
```

Install the npm packages from the `Npmfile`:

```shell
pnpm add -g $(tr '\n' ' ' < Npmfile)
```
