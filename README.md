# osu! Skin Maker

A small desktop app for designing osu! skins with a live preview, then exporting an `.osk`.
Pure Python, no root, no git, no pip.

Repo: https://github.com/brendenthebanana-hash/OsuSkinners

## Install (openSUSE or any Linux, no root)

    curl -fsSL https://raw.githubusercontent.com/brendenthebanana-hash/OsuSkinners/main/install.sh | sh

If your default branch is `master`:

    curl -fsSL https://raw.githubusercontent.com/brendenthebanana-hash/OsuSkinners/master/install.sh | SKINMAKER_BRANCH=master sh

This installs into your home folder: the program, a `skinmaker` command, an app menu entry
with an icon, and nothing else. If `skinmaker` is not found, add
`export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`.

## Use

Open **osu! Skin Maker** from your app menu (or run `skinmaker`).

- Live preview of hit circles, approach circle, slider, cursor + trail and hit results,
  plus a cursor close-up. The preview is drawn by the same code that writes the skin files.
- Customize: combo colors (1-8), hit circle fill/outline/numbers, approach circle, cursor
  (ring, dot, cross, diamond, arrow), trail, slider, hit result colors. Start from a preset.
- **Save to library** keeps skins (with thumbnails) so you can reopen and tweak them later.
- **Download .osk** then open it with osu! (or drag it into the game window).
- **Save preview image** exports the preview as a PNG.

The app opens in its own window if a Chromium based browser (Chrome, Chromium, Brave, Edge,
Vivaldi, also the Flatpak versions) is installed. Otherwise it opens in your default browser
tab; close it with Ctrl+C in the terminal. Force a browser tab with `skinmaker --browser`.

## Command line

    skinmaker "My Skin" --preset neon --author me --set cursor_style=arrow --set circle_outline_w=6
    skinmaker --list-options

## Uninstall

    sh uninstall.sh
