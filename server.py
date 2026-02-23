from __future__ import annotations

import os
import sys
import json
import platform
import subprocess
import time 
from pathlib import Path

import requests

from Azul_installer import setup_java


# ========== Windows Self-Elevation ==========
def _is_windows():
    return platform.system().lower() == "windows"

def _is_admin_windows():
    """Check if running with Administrator privileges on Windows."""
    if not _is_windows():
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError, ImportError):
        return False

def _elevate_windows():
    """Re-launch the current script with Administrator privileges.
    
    Returns True if elevation was attempted (script will exit).
    Returns False if already admin or not on Windows.
    """
    if not _is_windows():
        return False
    
    if _is_admin_windows():
        return False  # Already admin
    
    print("\n🔑 Administrator privileges required for system-wide Java installation.")
    print("   Requesting elevation via UAC...\n")
    
    try:
        import ctypes
        
        # Get the Python executable and script path
        python_exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{script}"'] + [f'"{arg}"' for arg in sys.argv[1:]])
        
        # ShellExecute with 'runas' verb to request elevation
        result = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "runas",        # lpVerb - 'runas' triggers UAC elevation
            python_exe,     # lpFile - the Python executable
            params,         # lpParameters - script and its arguments
            None,           # lpDirectory
            1               # nShowCmd - SW_SHOWNORMAL
        )
        
        # ShellExecuteW returns >32 on success, <=32 on error
        if result > 32:
            print("✅ Elevated process started. This window will close.")
            sys.exit(0)  # Exit the non-elevated process
        else:
            error_codes = {
                0: "Out of memory",
                2: "File not found",
                3: "Path not found", 
                5: "Access denied",
                8: "Not enough memory",
                32: "DLL not found",
            }
            error_msg = error_codes.get(result, f"Unknown error (code {result})")
            print(f"❌ Failed to elevate: {error_msg}")
            print("   Please right-click and 'Run as Administrator' manually.")
            return False
            
    except Exception as e:
        print(f"❌ Could not request elevation: {e}")
        print("   Please right-click and 'Run as Administrator' manually.")
        return False
    
    return True

def ensure_admin_for_java_install():
    """On Windows, ensure we have admin rights before installing Java system-wide.
    
    If not admin, attempts to relaunch with elevation.
    """
    if not _is_windows():
        return  # Not Windows, no elevation needed
    
    if _is_admin_windows():
        print("🔑 Running as Administrator - Java will be installed for all users.\n")
        return
    
    # Not admin - try to elevate
    print("\n" + "="*60)
    print("⚠️  ADMINISTRATOR PRIVILEGES RECOMMENDED")
    print("="*60)
    print("\nTo install Java system-wide (accessible by all users),")
    print("this script needs to run as Administrator.\n")
    
    choice = input("Attempt to elevate to Administrator? (y/n): ").strip().lower()
    
    if choice in ("y", "yes"):
        if _elevate_windows():
            sys.exit(0)  # Elevated process started, exit this one
    else:
        print("\n⚠️ Continuing without Administrator privileges.")
        print("   Java will be installed for the current user only.\n")



def server_base_dir() -> Path:
    os_name = platform.system().lower()
    if "windows" in os_name:
        base = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData")) / "MinecraftServers"
    elif "darwin" in os_name:
        base = Path.home() / "Library" / "Application Support" / "MinecraftServers"
    else:
        base = Path.home() / ".local" / "share" / "MinecraftServers"
    base.mkdir(parents=True, exist_ok=True)
    return base

def server_dir_for(flavor: str, mc_version: str | None = None) -> Path:
    name = f"{flavor.lower()}_{mc_version}" if mc_version else flavor.lower()
    d = server_base_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d

def handle_eula(folder: Path, java_bin: str):

    eula_file = folder / "eula.txt"
    eula_url = "https://www.minecraft.net/eula"

    if not eula_file.exists():
        print("\n 📀 Running the server once to generate eula.txt...")
        subprocess.run([java_bin, "-jar", "server.jar", "--nogui"], cwd=folder)
        print("📝 eula.txt should now be generated.")
        time.sleep(3)  # Brief wait for file system

    if not eula_file.exists():
        print("❌ eula.txt not found. Something went wrong.")
        return False
    
    # Check if already accepted
    content = eula_file.read_text(encoding="utf-8")
    if "eula=true" in content.lower():
        print("✅ EULA already accepted.")
        return True
    
    print(f"\n 📜 Minecraft End User License Agreement (EULA): {eula_url}")
    choice = input("Do you accept the EULA? (yes/no): ").strip().lower()

    if choice in ("yes", "y"):
        eula_file.write_text("eula=true\n", encoding="utf-8")
        print("✅ You accepted the EULA.")
        return True
    else:
        eula_file.write_text("eula=false\n", encoding="utf-8")
        print("❌ You did not accept the EULA. Exiting setup.")
        return False
    

def download_file(path: Path, url: str, label: str = "file", expected_size: int = 0):
    print(f"Downloading {label}...")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        # Use Content-Length from headers, or fall back to expected_size parameter
        total_size = int(r.headers.get('content-length', 0)) or expected_size
        downloaded = 0
        bar_width = 40
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        spin_idx = 0
        
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    downloaded_mb = downloaded / (1024 * 1024)
                    
                    if total_size > 0:
                        # Known size: show progress bar
                        percent = (downloaded / total_size) * 100
                        filled = int(bar_width * downloaded / total_size)
                        bar = '█' * filled + '░' * (bar_width - filled)
                        total_mb = total_size / (1024 * 1024)
                        print(f"\r  [{bar}] {percent:5.1f}% | {downloaded_mb:.1f}/{total_mb:.1f} MB", end='', flush=True)
                    else:
                        # Unknown size: show spinner with downloaded amount
                        spin_idx = (spin_idx + 1) % len(spinner)
                        print(f"\r  {spinner[spin_idx]} Downloaded: {downloaded_mb:.1f} MB...", end='', flush=True)
        
        # Move to new line after download completes
        print()
    
    print(f"✅ Saved: {path}")


# _______ Vanilla Server Setup _______

def get_latest_vanilla():
    manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
    r = requests.get(manifest_url, timeout=30)
    r.raise_for_status()
    data = r.json()
    latest = data["latest"]["release"]
    v = next(v for v in data["versions"] if v["id"] == latest)
    r2 = requests.get(v["url"], timeout=30)
    r2.raise_for_status()
    version_data = r2.json()
    server_url = version_data["downloads"]["server"]["url"]
    return latest, server_url

def install_vanilla(folder: Path) -> tuple[str, Path]:
    mc_version, jar_url = get_latest_vanilla()
    jar_path = folder / "server.jar"
    print(f"\n🌐 Installing Vanilla Minecraft Server version {mc_version}: {jar_url}")
    download_file(jar_path, jar_url, label="vanilla server.jar")
    return mc_version, jar_path

# _______ Paper Server Setup _______
def get_latest_paper_download():
    base = "https://api.papermc.io/v2/projects/paper"
    r = requests.get(base, timeout=30)
    r.raise_for_status()
    version = r.json()["versions"]
    if not version:
        raise RuntimeError("No Paper versions found.")
    mc_version = version[-1]

    r2 = requests.get(f"{base}/versions/{mc_version}", timeout=30)
    r2.raise_for_status()
    builds = r2.json()["builds"]
    if not builds:
        raise RuntimeError(f"No Paper builds for {mc_version}.")
    latest_build = builds[-1]  # builds is a list of integers

    r3 = requests.get(f"{base}/versions/{mc_version}/builds/{latest_build}", timeout=30)
    r3.raise_for_status()
    info = r3.json()
    download_info = info["downloads"]["application"]
    fname = download_info["name"]
    file_size = download_info.get("size", 0)  # Get file size from API
    url = f"{base}/versions/{mc_version}/builds/{latest_build}/downloads/{fname}"
    return mc_version, url, fname, file_size

def install_paper(folder: Path) -> tuple[str, Path]:
    mc_version, url, fname, file_size = get_latest_paper_download()
    jar_path = folder / "server.jar"
    print(f"\n🌐 Installing Paper Minecraft Server version {mc_version}: {url}")
    download_file(jar_path, url, label="Paper server.jar", expected_size=file_size)
    return mc_version, jar_path

# _______ Spigot (BuildTools) _______
BUILDTOOLS_URL = "https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar"

def check_git_installed() -> bool:
    """Check if git is installed and available."""
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def get_latest_mc_version() -> str:
    """Get the latest Minecraft release version from Mojang."""
    manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
    r = requests.get(manifest_url, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["latest"]["release"]

def install_spigot(folder: Path) -> tuple[str, Path]:
    """
    Install Spigot server using BuildTools.
    BuildTools compiles Spigot from source, which requires:
    - Java (already handled)
    - Git (must be installed on the system)
    """
    # Check for Git
    if not check_git_installed():
        print("\n❌ Git is required to build Spigot!")
        print("   Please install Git:")
        print("   • macOS: brew install git  (or install Xcode Command Line Tools)")
        print("   • Windows: https://git-scm.com/download/win")
        print("   • Linux: sudo apt install git (or your package manager)")
        raise RuntimeError("Git is not installed. Please install Git and try again.")
    
    print("\n🔧 Building Spigot Server with BuildTools...")
    print("   This may take 5-10 minutes on first run.\n")
    
    # Create a build directory inside the server folder
    build_dir = folder / "buildtools"
    build_dir.mkdir(parents=True, exist_ok=True)
    
    buildtools_jar = build_dir / "BuildTools.jar"
    
    # Download BuildTools if not present or if it's old
    print("📥 Downloading BuildTools.jar...")
    download_file(buildtools_jar, BUILDTOOLS_URL, label="BuildTools.jar")
    
    # Get the latest MC version
    mc_version = get_latest_mc_version()
    print(f"\n🎯 Building for Minecraft {mc_version}...")
    
    # Get Java binary from Azul installer
    from Azul_installer import setup_java
    info = setup_java(java_major=21)
    java_bin = info["java_bin"]
    
    # Run BuildTools
    print("\n🔨 Running BuildTools (this takes a while)...")
    print("   Please wait, compiling Spigot from source...\n")
    
    cmd = [java_bin, "-jar", "BuildTools.jar", "--rev", mc_version]
    
    try:
        result = subprocess.run(
            cmd, 
            cwd=str(build_dir),
            capture_output=False,  # Show output in real-time
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"BuildTools failed with exit code {result.returncode}")
            
    except subprocess.SubprocessError as e:
        raise RuntimeError(f"BuildTools execution failed: {e}")
    
    # Find the built spigot jar
    spigot_jars = list(build_dir.glob(f"spigot-{mc_version}*.jar"))
    
    if not spigot_jars:
        # Also check for spigot.jar (some versions)
        spigot_jars = list(build_dir.glob("spigot-*.jar"))
    
    if not spigot_jars:
        raise RuntimeError(
            f"BuildTools completed but no spigot-*.jar found in {build_dir}. "
            "Check the BuildTools output for errors."
        )
    
    # Use the first (or latest) spigot jar found
    built_jar = spigot_jars[0]
    print(f"\n✅ Built: {built_jar.name}")
    
    # Copy to server.jar in the main folder
    jar_path = folder / "server.jar"
    import shutil
    shutil.copy2(built_jar, jar_path)
    print(f"📁 Copied to: {jar_path}")
    
    return mc_version, jar_path

# ---------- UI ----------
def prompt_choice() -> str:
    print("\nChoose Minecraft server type:")
    print("  1) Paper (recommended)")
    print("  2) Vanilla (official)")
    print("  3) Spigot (requires Git)")
    choice = input("Enter 1/2/3: ").strip()
    mapping = {"1": "paper", "2": "vanilla", "3": "spigot"}
    return mapping.get(choice, "")


def launch_control_ui():
    """Launch the server control UI in a new process."""
    ui_script = Path(__file__).parent / "server_ui.py"
    
    if not ui_script.exists():
        print(f"❌ Control UI not found: {ui_script}")
        return
    
    print(f"\n🎮 Launching Server Control Panel...")
    print(f"   You can also run it directly: python {ui_script.name}")
    time.sleep(1)
    
    # Run the UI script
    subprocess.run([sys.executable, str(ui_script)])


def main():
    # 0) On Windows, offer to elevate to Administrator for system-wide Java install
    ensure_admin_for_java_install()
    
    # 1) Ensure Java (Azul) and get the Java executable path
    info = setup_java(java_major=21)
    java_bin = info["java_bin"]  # "java" on PATH (MSI) or full path (portable)

    # 2) Ask user which server
    flavor = prompt_choice()
    if not flavor:
        print("Invalid choice. Exiting.")
        sys.exit(1)

    # 3) Install chosen server
    try:
        if flavor == "paper":
            folder = server_dir_for("paper")
            mc_version, jar_path = install_paper(folder)
        elif flavor == "vanilla":
            folder = server_dir_for("vanilla")
            mc_version, jar_path = install_vanilla(folder)
        elif flavor == "spigot":
            folder = server_dir_for("spigot")
            mc_version, jar_path = install_spigot(folder)
        else:
            print("Unknown flavor.")
            return
        
        # Save server metadata for UI to read
        server_info = {
            "flavor": flavor,
            "version": mc_version,
            "jar_file": jar_path.name
        }
        info_path = folder / "server_info.json"
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(server_info, f, indent=2)
        print(f"📝 Saved server info to {info_path}")
        
    except Exception as e:
        print("❌ Install failed:", e)
        sys.exit(1)

    if not jar_path.exists():
        print("❌ Download failed: server.jar not found.")
        sys.exit(1)

    # 4) Ask the user to accept EULA before proceeding
    if not handle_eula(folder, java_bin):
        print("⚠️ You must accept the EULA to start the server.")
        sys.exit(0)

    # 5) Launch the server control UI
    print("\n✅ Setup complete!")
    launch_control_ui()


if __name__ == "__main__":
    main()
