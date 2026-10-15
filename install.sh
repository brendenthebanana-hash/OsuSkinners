#!/bin/sh
# Installs osu! Skin Maker into your home folder. No root, no git needed.
set -eu

REPO="${SKINMAKER_REPO:-YOUR_USERNAME/YOUR_REPO}"   # <- your GitHub user/repo
BRANCH="${SKINMAKER_BRANCH:-main}"

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA/osu-skinmaker"
BIN="$HOME/.local/bin"
APPS="$DATA/applications"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required (it ships with openSUSE)."; exit 1; }
mkdir -p "$PREFIX" "$BIN" "$APPS"

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
if [ -n "$here" ] && [ -f "$here/skinmaker.py" ]; then
  cp "$here/skinmaker.py" "$PREFIX/skinmaker.py"
else
  case "$REPO" in YOUR_USERNAME*) echo "Set the repo first:  SKINMAKER_REPO=user/repo sh install.sh"; exit 1;; esac
  url="https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"
  echo "Downloading $url"
  tmp="$(mktemp -d)"
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$url" -o "$tmp/src.tgz"
  else wget -qO "$tmp/src.tgz" "$url"; fi
  tar -xzf "$tmp/src.tgz" -C "$tmp"
  cp "$tmp"/*/skinmaker.py "$PREFIX/skinmaker.py"
  rm -rf "$tmp"
fi

cat > "$BIN/skinmaker" <<WRAP
#!/bin/sh
exec python3 "$PREFIX/skinmaker.py" "\$@"
WRAP
chmod +x "$BIN/skinmaker"

cat > "$APPS/osu-skinmaker.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=osu! Skin Maker
Comment=Generate osu! skins
Exec=$BIN/skinmaker --gui
Terminal=false
Categories=Game;Graphics;
DESK

echo
echo "Installed. Run:  skinmaker            (opens in your browser)"
echo "          or:  skinmaker \"My Skin\" --preset neon"
case ":$PATH:" in *":$BIN:"*) ;; *)
  echo "NOTE: add this to ~/.bashrc, then reopen the terminal:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"";; esac
