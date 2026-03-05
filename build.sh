#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  build.sh — Build Minecraft Python Server for Ubuntu
#
#  Produces:
#    dist/minecraft-python-server_1.0.0_all.deb   (multi-arch .deb)
#
#  Optional (pass --pyinstaller flag):
#    dist/minecraft-server               (native standalone binary)
#    dist/minecraft-server-ui            (native standalone binary)
#    dist/minecraft-server-uninstall     (native standalone binary)
#
#  Usage:
#    chmod +x build.sh && ./build.sh            # .deb only
#    chmod +x build.sh && ./build.sh --pyinstaller  # .deb + binaries
#
#  Must be run on Ubuntu / Debian.
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

PKG_NAME="minecraft-python-server"
PKG_VERSION="1.0.0"
BUILD_PYINSTALLER=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --pyinstaller) BUILD_PYINSTALLER=true ;;
    esac
done

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

info "Detected: $(uname -m) — building Architecture: all (multi-arch) .deb"

# ── 1. Install system dependencies ─────────────────────────────────
info "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-requests dpkg-dev > /dev/null 2>&1
ok "System dependencies installed."


# ═══════════════════════════════════════════════════════════════════
# ── 2. Build multi-arch .deb (Architecture: all) ──────────────────
# ═══════════════════════════════════════════════════════════════════
info "Assembling multi-arch .deb package..."

rm -rf build/ dist/
mkdir -p dist/

DEB_DIR="build/deb/${PKG_NAME}_${PKG_VERSION}_all"

# Directory structure
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/local/lib/minecraft-server"
mkdir -p "$DEB_DIR/usr/local/bin"
mkdir -p "$DEB_DIR/usr/share/applications"

# Copy Python source files
cp server.py           "$DEB_DIR/usr/local/lib/minecraft-server/"
cp server_ui.py        "$DEB_DIR/usr/local/lib/minecraft-server/"
cp uninstall.py        "$DEB_DIR/usr/local/lib/minecraft-server/"
cp Azul_installer.py   "$DEB_DIR/usr/local/lib/minecraft-server/"
cp requirements.txt    "$DEB_DIR/usr/local/lib/minecraft-server/"

# Create wrapper scripts that invoke python3 on the source files
cat > "$DEB_DIR/usr/local/bin/minecraft-server" << 'WRAPPER'
#!/usr/bin/env bash
exec python3 /usr/local/lib/minecraft-server/server.py "$@"
WRAPPER

cat > "$DEB_DIR/usr/local/bin/minecraft-server-ui" << 'WRAPPER'
#!/usr/bin/env bash
exec python3 /usr/local/lib/minecraft-server/server_ui.py "$@"
WRAPPER

cat > "$DEB_DIR/usr/local/bin/minecraft-server-uninstall" << 'WRAPPER'
#!/usr/bin/env bash
exec python3 /usr/local/lib/minecraft-server/uninstall.py "$@"
WRAPPER

chmod 755 "$DEB_DIR/usr/local/bin/"*

# Copy Debian control files
cp debian/control   "$DEB_DIR/DEBIAN/control"
cp debian/postinst  "$DEB_DIR/DEBIAN/postinst"
cp debian/prerm     "$DEB_DIR/DEBIAN/prerm"
chmod 755 "$DEB_DIR/DEBIAN/postinst"
chmod 755 "$DEB_DIR/DEBIAN/prerm"

# Copy desktop entry
cp debian/minecraft-server-ui.desktop "$DEB_DIR/usr/share/applications/"

# Calculate installed size (in KB) and inject into control file
INSTALLED_SIZE=$(du -sk "$DEB_DIR" | cut -f1)
sed -i "/^Architecture:/a Installed-Size: ${INSTALLED_SIZE}" "$DEB_DIR/DEBIAN/control"

# Build the .deb
DEB_FILE="dist/${PKG_NAME}_${PKG_VERSION}_all.deb"
dpkg-deb --build "$DEB_DIR" "$DEB_FILE"

ok "Multi-arch .deb package created: $DEB_FILE"


# ═══════════════════════════════════════════════════════════════════
# ── 3. (Optional) Build native PyInstaller binaries ───────────────
# ═══════════════════════════════════════════════════════════════════
if [[ "$BUILD_PYINSTALLER" == "true" ]]; then
    info "Building native PyInstaller binaries..."

    # Detect native arch for labeling
    case "$(uname -m)" in
        x86_64)  NATIVE_ARCH="amd64" ;;
        aarch64) NATIVE_ARCH="arm64" ;;
        armv7l)  NATIVE_ARCH="armhf" ;;
        *)       NATIVE_ARCH="$(dpkg --print-architecture 2>/dev/null || echo unknown)" ;;
    esac

    sudo apt-get install -y -qq python3-venv > /dev/null 2>&1
    python3 -m venv build_venv
    source build_venv/bin/activate

    pip install --upgrade pip > /dev/null 2>&1
    pip install pyinstaller -q
    pip install -r requirements.txt -q

    pyinstaller minecraft_server.spec --noconfirm --clean 2>&1 | tail -5

    for bin_name in minecraft-server minecraft-server-ui minecraft-server-uninstall; do
        if [[ ! -f "dist/$bin_name" ]]; then
            fail "Expected binary dist/$bin_name was not created!"
        fi
    done

    deactivate
    rm -rf build_venv

    ok "Native binaries built for ${NATIVE_ARCH}."
    echo ""
    echo "  Standalone binaries (${NATIVE_ARCH} only):"
    echo "    📦 dist/minecraft-server"
    echo "    📦 dist/minecraft-server-ui"
    echo "    📦 dist/minecraft-server-uninstall"
fi


# ── 4. Cleanup ──────────────────────────────────────────────────────
rm -rf build/

# ── 5. Summary ──────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  BUILD COMPLETE${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Multi-arch .deb (works on amd64, arm64, armhf, etc.):"
echo "    📦 $DEB_FILE"
echo ""
echo "  Install with:"
echo "    sudo dpkg -i $DEB_FILE"
echo ""
if [[ "$BUILD_PYINSTALLER" != "true" ]]; then
    echo "  To also build native standalone binaries, run:"
    echo "    ./build.sh --pyinstaller"
    echo ""
fi
