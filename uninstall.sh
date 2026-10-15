#!/bin/sh
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$DATA/osu-skinmaker" "$HOME/.local/bin/skinmaker" "$DATA/applications/osu-skinmaker.desktop"
echo "Removed osu! Skin Maker."
