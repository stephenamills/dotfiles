This repo contains my shell configurations and packages.

These are for my personal use cases, but here in case someone finds them useful.

### Usage

[Homebrew](https://brew.sh) is required to install dependencies the two shell configuration files rely on.

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

xargs -n 1 dotnet tool install -g < Dotnetfile
xargs -n 1 go install < Gofile
pnpm install -g $(cat Javascriptfile)
xargs -n 1 pipx install < Pythonfile
cargo-binstall -y $(cat Rustfile)
mint install $(cat Swiftfile)
```
