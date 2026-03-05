#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  build.sh — Build Minecraft Python Server for Ubuntu
#
#  Produces:
#    dist/minecraft-server               (standalone binary)
#    dist/minecraft-server-ui            (standalone binary)
#    dist/minecraft-server-uninstall     (standalone binary)
#    dist/minecraft-python-server_1.0.0_amd64.deb
#
#  Usage:  chmod +x build.sh && ./build.sh
#  Must be run on Ubuntu / Debian (x86_64).
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

PKG_NAME="minecraft-python-server"
PKG_VERSION="1.0.0"
ARCH="amd64"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 0. Pre-flight checks ───────────────────────────────────────────
info "Checking system..."

if [[ "$(uname -s)" != "Linux" ]]; then
    fail "This script must be run on Linux (Ubuntu/Debian)."
fi

if [[ "$(uname -m)" != "x86_64" ]]; then
    warn "Detected arch $(uname -m). Package will still be built as amd64."
fi

# ── 1. Install system dependencies ─────────────────────────────────
info "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv dpkg-dev > /dev/null 2>&1
ok "System dependencies installed."

# ── 2. Create virtual-env & install Python deps ────────────────────
info "Setting up Python virtual environment..."
python3 -m venv build_venv
source build_venv/bin/activate

pip install --upgrade pip > /dev/null 2>&1
pip install pyinstaller -q
pip install -r requirements.txt -q
ok "Python environment ready."

# ── 3. Run PyInstaller ──────────────────────────────────────────────
info "Building executables with PyInstaller..."

rm -rf build/ dist/

pyinstaller minecraft_server.spec --noconfirm --clean 2>&1 | tail -5

# Verify all three binaries exist
for bin_name in minecraft-server minecraft-server-ui minecraft-server-uninstall; do
    if [[ ! -f "dist/$bin_name" ]]; then
        fail "Expected binary dist/$bin_name was not created!"
    fi
done
ok "All 3 binaries built successfully."

# ── 4. Assemble .deb package ───────────────────────────────────────
info "Assembling .deb package..."

DEB_DIR="build/deb/${PKG_NAME}_${PKG_VERSION}_${ARCH}"
rm -rf "$DEB_DIR"

# Directory structure
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/local/bin"
mkdir -p "$DEB_DIR/usr/share/applications"

# Copy Debian control files
cp debian/control   "$DEB_DIR/DEBIAN/control"
cp debian/postinst  "$DEB_DIR/DEBIAN/postinst"
cp debian/prerm     "$DEB_DIR/DEBIAN/prerm"
chmod 755 "$DEB_DIR/DEBIAN/postinst"
chmod 755 "$DEB_DIR/DEBIAN/prerm"

# Copy binaries
cp dist/minecraft-server          "$DEB_DIR/usr/local/bin/"
cp dist/minecraft-server-ui       "$DEB_DIR/usr/local/bin/"
cp dist/minecraft-server-uninstall "$DEB_DIR/usr/local/bin/"
chmod 755 "$DEB_DIR/usr/local/bin/"*

# Copy desktop entry
cp debian/minecraft-server-ui.desktop "$DEB_DIR/usr/share/applications/"

# Calculate installed size (in KB) and inject into control file
INSTALLED_SIZE=$(du -sk "$DEB_DIR" | cut -f1)
sed -i "/^Architecture:/a Installed-Size: ${INSTALLED_SIZE}" "$DEB_DIR/DEBIAN/control"

# Build the .deb
DEB_FILE="dist/${PKG_NAME}_${PKG_VERSION}_${ARCH}.deb"
dpkg-deb --build "$DEB_DIR" "$DEB_FILE"

ok ".deb package created."

# ── 5. Cleanup ──────────────────────────────────────────────────────
deactivate
rm -rf build_venv build/

# ── 6. Summary ──────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  BUILD COMPLETE${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Standalone binaries:"
echo "    📦 dist/minecraft-server"
echo "    📦 dist/minecraft-server-ui"
echo "    📦 dist/minecraft-server-uninstall"
echo ""
echo "  Debian package:"
echo "    📦 $DEB_FILE"
echo ""
echo "  Install with:"
echo "    sudo dpkg -i $DEB_FILE"
echo ""
echo "  Or run standalone:"
echo "    ./dist/minecraft-server"
echo ""
