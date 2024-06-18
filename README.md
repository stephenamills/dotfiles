# My dotfiles

This collection contains my personal shell configuration files and installed Homebrew and npm packages.

# Usage

Homebrew is required to install packages that the shell configuration files depend on.

Clone this repository and copy `.zprofile` and `.zshrc` to your home directory.

Then install the Homebrew packages from the `Brewfile`:

```
brew bundle install --no-lock
```

Lastly, install the npm packages from the `Npmfile`:

```shell
pnpm add -g $(tr '\n' ' ' < Npmfile)
```
