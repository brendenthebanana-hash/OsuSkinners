# osu! Skin Maker

Generates a basic osu! skin (`.osk`) from a few colors you pick.
Pure Python. No root, no git, no pip.

Repo: https://github.com/brendenthebanana-hash/OsuSkinners

## Install (openSUSE or any Linux, no root)

    curl -fsSL https://raw.githubusercontent.com/brendenthebanana-hash/OsuSkinners/main/install.sh | sh

If your default branch is `master`:

    curl -fsSL https://raw.githubusercontent.com/brendenthebanana-hash/OsuSkinners/master/install.sh | SKINMAKER_BRANCH=master sh

This installs into your home folder only:

- program: `~/.local/share/osu-skinmaker`
- command: `~/.local/bin/skinmaker`
- app menu entry: "osu! Skin Maker"

If `skinmaker` is not found, add this to `~/.bashrc` and reopen the terminal:

    export PATH="$HOME/.local/bin:$PATH"

## Use

    skinmaker

Opens the skin maker in your browser. Pick colors, click **Download .osk**,
then open the file with osu! (or drag it into the game window).

Command line:

    skinmaker "My Skin" --author me --preset neon --ring ff2e88 --cursor 2ee6ff

Options: `--preset classic|neon|pastel|dark`, `--colors ff0000,00ff00`, `--ring`, `--cursor`,
`--folder` (unzipped folder instead of .osk), `--out DIR`. See `skinmaker --help`.

## Uninstall

    sh uninstall.sh
