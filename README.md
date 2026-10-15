# osu! Skin Maker

Generates a basic osu! skin (`.osk`) from a few colors. Pure Python, no root, no git, no pip.

## Install (openSUSE or any Linux, no root)
    curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/install.sh | SKINMAKER_REPO=USER/REPO sh

Replace `USER/REPO` with this repo. Or edit the `REPO=` line in `install.sh` and drop the variable.

## Use
    skinmaker                                  # opens the skin maker in your browser
    skinmaker "My Skin" --author me --preset neon --ring ff2e88 --cursor 2ee6ff

Open the downloaded `.osk` with osu! (or drag it into the window).
Run `skinmaker --help` for all options. Uninstall with `uninstall.sh`.
