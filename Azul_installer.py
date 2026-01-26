import os
import socket
import subprocess
import tempfile
import shutil
import requests
import tarfile
import zipfile
import platform

from pathlib import Path

# ---------Network Request---------
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retries = Retry(
    total = 5,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))
DEFAULT_TIMEOUT = 15 #seconds

AZUL_METADATA_BASE = "https://api.azul.com/metadata/v1" # Azul's metadata API base URL


# Normalize OS and architecture
def normalize_os_arch():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if "windows" in system:
        os_name = "windows"
    elif "linux" in system:
        os_name = "linux"
    elif "darwin" in system or "mac" in system:
        os_name = "macos"
    else:
        raise ValueError(f"Unsupported OS: {system}")
    
    # Mapping the architecture

    if machine in ["x86_64", "amd64"]:
        arch = "x86_64"
    elif machine in ["aarch64", "arm64"]:
        arch = "aarch64"
    else:
        raise ValueError(f"Unsupported architecture: {machine}")
    
    return os_name, arch


# API calling
def get_latest_zulu(java_major=21, os_name=None, arch=None):

    if not os_name or not arch:
        os_name, arch = normalize_os_arch()

    params = {
        "java_version": java_major,
        "os": os_name,
        "arch": arch,
        "java_package_type": "jdk",
        "release_status": "ga",
        "availability_types": "CA",
        "latest": "true",
        "page_size": 20
    }
    
    # For Linux, specify glibc to avoid getting musl builds (Alpine Linux)
    # Ubuntu and most Linux distros use glibc, not musl
    if os_name == "linux":
        params["libc_type"] = "glibc"

    url = f"{AZUL_METADATA_BASE}/zulu/packages/"
    print("Fetching Azul Zulu JDK metadata...")

    try:
        resp = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Network error while fetching Azul metadata: {e}")
    
    data = resp.json()

    if not data:
        raise ValueError("No matching Zulu JDK found.")
    
    def pick(suffix):
        for pkg in data:
            name = pkg["name"].lower()
            # Skip CRaC builds
            if "-crac-" in name:
                continue
            # CRITICAL: Skip musl builds on non-Alpine Linux systems
            # musl binaries are incompatible with glibc systems like Ubuntu/Debian
            if os_name == "linux" and "_musl_" in name:
                continue
            if any(name.endswith(suf) for suf in suffix):
                return pkg["download_url"], pkg["name"]
        return None
    
    if os_name == "windows":

        found = pick([".msi"]) or pick([".zip"])
    
    elif os_name == "macos":
        found = pick([".tar.gz", ".tgz"]) or pick([".zip"])
    else: # For Linux distros
        found = pick([".tar.gz", ".tgz"]) or pick([".zip"])
    
    if not found:
        raise ValueError("No suitable package found for the specified OS and architecture.")
    return found


def download_file(url, dest):
    print(f"Downloading {url}...\n")

    try:
        with session.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            bar_width = 40
            
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        # Calculate progress
                        percent = (downloaded / total_size) * 100
                        filled = int(bar_width * downloaded / total_size)
                        bar = '█' * filled + '░' * (bar_width - filled)
                        
                        # Show size in MB
                        downloaded_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        
                        # Print progress bar (overwrite same line)
                        print(f"\r  [{bar}] {percent:5.1f}% | {downloaded_mb:.1f}/{total_mb:.1f} MB", end='', flush=True)
            
            # Move to new line after download completes
            if total_size > 0:
                print()  # New line after progress bar
                
    except requests.RequestException as e:
        raise RuntimeError(f"Download failed: {e}")
    
    print(f"\n✅ Saved: {dest}\n")

def _is_admin_windows():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except (AttributeError, OSError, ImportError):
        return False
    
def _is_root_unix():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False
    
def detect_shell():
    """Detect the current shell and return the appropriate config file."""
    shell = os.environ.get("SHELL", "")
    shell_name = Path(shell).name if shell else ""
    
    # Determine which config files to use
    if "zsh" in shell_name:
        candidates = [Path.home() / ".zshrc", Path.home() / ".zprofile"]
        shell_type = "zsh"
    elif "bash" in shell_name:
        candidates = [Path.home() / ".bashrc", Path.home() / ".bash_profile", Path.home() / ".profile"]
        shell_type = "bash"
    else:
        # Default to bash-style files
        candidates = [Path.home() / ".bashrc", Path.home() / ".profile"]
        shell_type = "unknown"
    
    # Find the first existing file, or use the first candidate
    target = next((p for p in candidates if p.exists()), candidates[0])
    return target, shell_type, shell_name

def verify_java_installation(java_bin=None):
    """Verify that Java is properly installed and accessible."""
    try:
        cmd = [java_bin] if java_bin else ["java"]
        result = subprocess.run(
            cmd + ["-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Java version info goes to stderr
            version_output = result.stderr if result.stderr else result.stdout
            return True, version_output.split('\n')[0] if version_output else "Unknown version"
        return False, None
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        return False, str(e)

def choose_permanent_base(os_name: str) -> Path:
    if os_name == "linux":
        return Path("/usr/local/lib/jvm") if _is_root_unix() else Path.home() / ".local" / "share" / "java"
    if os_name == "macos":
        return Path("/Library/Java/JavaVirtualMachines") if _is_root_unix() else Path.home() / "Library" / "Java" / "JavaVirtualMachines"
    if os_name == "windows":
        if _is_admin_windows():
            return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Zulu"
        else:
            return Path(os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%LOCALAPPDATA%"))) / "Programs" / "Zulu"
    raise ValueError(f"Unsupported OS: {os_name}")
    
def persist_env_windows_user(jdk_root: Path):

    subprocess.run(["setx", "JAVA_HOME", str(jdk_root)], check=False, shell=True)
    # Append to PATH using setx - only add %JAVA_HOME%\bin to avoid PATH length issues
    current_path = os.environ.get('PATH', '')
    if "%JAVA_HOME%\\bin" not in current_path and str(jdk_root / "bin") not in current_path:
        subprocess.run(["setx", "PATH", f"%JAVA_HOME%\\bin;%PATH%"], check=False, shell=True)
    print("🔧 Set JAVA_HOME and updated PATH for the current user (restart Terminal to apply).\n")


def move_extracted_to_base(tmp_extract_dir: Path, base: Path) -> Path:
    entries = [p for p in tmp_extract_dir.iterdir() if p.is_dir()]
    if not entries:
        raise RuntimeError("Extraction failed, no contents found.")
    src_root = entries[0]
    base.mkdir(parents=True, exist_ok=True)
    dest = base / src_root.name
    
    if dest.exists():
        # Validate existing installation has java binary
        java_bin = dest / "bin" / "java"
        if not java_bin.exists() and not (dest / "bin" / "java.exe").exists():
            print(f"⚠️ {dest} exists but appears corrupted. Removing and reinstalling...\n")
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(src_root), str(dest))
            print(f"✅ Moved JDK to: {dest}\n")
        else:
            print(f"⚠️ Target directory {dest} already exists and appears valid. Using existing installation.\n")
        return dest
    else:
        shutil.move(str(src_root), str(dest))
        print(f"✅ Moved JDK to: {dest}\n")
        return dest


def persist_env_posix(jdk_root: Path):
    """Append JAVA_HOME/PATH to system-wide or user shell config (idempotent)."""
    
    # When running as root, use /etc/profile.d for system-wide access
    if _is_root_unix():
        profile_d = Path("/etc/profile.d")
        target = profile_d / "zulu-jdk.sh"
        
        script_content = (
            "#!/bin/sh\n"
            "# Zulu JDK environment configuration (managed by Azul installer)\n"
            f'export JAVA_HOME="{jdk_root}"\n'
            'export PATH="$JAVA_HOME/bin:$PATH"\n'
        )
        
        # Check if already configured
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if str(jdk_root) in existing:
                print(f"✅ JAVA_HOME already configured in {target}\n")
                return target
        
        # Write system-wide profile script
        profile_d.mkdir(parents=True, exist_ok=True)
        target.write_text(script_content, encoding="utf-8")
        target.chmod(0o644)  # Make readable by all users
        
        # Also create symlinks for java/javac in /usr/local/bin for immediate access
        local_bin = Path("/usr/local/bin")
        local_bin.mkdir(parents=True, exist_ok=True)
        
        for binary in ["java", "javac", "jar"]:
            src = jdk_root / "bin" / binary
            link = local_bin / binary
            if src.exists():
                if link.exists() or link.is_symlink():
                    link.unlink()  # Remove old symlink
                link.symlink_to(src)
        
        print(f"🔧 Created system-wide Java configuration: {target}")
        print(f"🔗 Created symlinks in /usr/local/bin for immediate access\n")
        print("=" * 60)
        print("✅ Java is now available SYSTEM-WIDE!")
        print("=" * 60)
        print("\nJava will be available:")
        print("  • Immediately in this terminal (via /usr/local/bin symlinks)")
        print("  • In all new terminal sessions")
        print("  • For all users on this system")
        print("  • After system restart")
        print("=" * 60 + "\n")
        return target
    
    # For non-root users, use user's shell config
    block = (
        "\n# >>> zulu-jdk (managed) >>>\n"
        f'export JAVA_HOME="{jdk_root}"\n'
        'export PATH="$JAVA_HOME/bin:$PATH"\n'
        "# <<< zulu-jdk (managed) <<<\n"
    )
    
    target, shell_type, shell_name = detect_shell()
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    
    if "# >>> zulu-jdk (managed) >>>" not in text:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(block)
        print(f"🔧 Added JAVA_HOME and PATH to {target}\n")
        print("\n" + "="*60)
        print("⚠️  ACTION REQUIRED - Environment Not Yet Active")
        print("="*60)
        print(f"\nThe installation is complete, but your current terminal")
        print(f"session doesn't have the updated environment variables yet.\n")
        print(f"To activate Java in THIS terminal, run:\n")
        print(f"    source {target}\n")
        print(f"OR simply close this terminal and open a new one.\n")
        print(f"New terminal sessions will automatically have Java available.")
        print("="*60 + "\n")
        return target
    else:
        print(f"✅ JAVA_HOME already configured in {target}\n")
        return target

    
def extract_archive(archive_path, extract_to):
    if archive_path.endswith(".zip"):
        with zipfile.ZipFile(archive_path, 'r') as z:
            z.extractall(extract_to)
    elif archive_path.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, 'r:gz') as t:
            t.extractall(extract_to)
    else:
        raise ValueError("Unsupported archive format.")
    print(f"Extracted to: {extract_to}\n")

def ensure_java_installed():
    try:
        out = subprocess.run(["java", "-version"], capture_output=True, text=True)
        return out.returncode == 0
    except FileNotFoundError:
        return False

def install_zulu_msi(msi_path):
    print ("Running MSI installer (requires Administrator access)...\n")
    subprocess.run([
        "msiexec", "/i", msi_path,
        "/qn",
        "ADDLOCAL=FeatureJavaHome,FeatureEnvironment"
    ], check=True)
    print("✅ Azul JDK installed via MSI.\n")

def setup_java(java_major=21):
    if ensure_java_installed():
        print("✅ Java is already installed.\n")
        return {"java_bin": "java", "jdk_root": None, "mode": "existing"}
        
    os_name, arch = normalize_os_arch()
    url, fname = get_latest_zulu(java_major, os_name, arch)

    if os_name in ("linux", "macos"):
        base = Path.home() / ".local" / "share" / "java"
        if base.exists():
            for child in base.iterdir():
                if child.is_dir() and "zulu" in child.name.lower():
                    ans = input(f"⚠️ Found existing Azul JDK at {child}. Do you want to uninstall it? (y/n): ").strip().lower()
                    if ans == "y":
                        uninstall_zulu_linux()
                    else:
                        print("Aborting installation.\n")
                        return {"java_bin": None, "jdk_root": str(child), "mode": "skipped", "os": os_name, "arch": arch}
                    break

    print(f"Found Azul JDK package: {fname}\n")

    tmpdir = tempfile.mkdtemp()
    try:
        file_path = os.path.join(tmpdir, fname)
        download_file(url, file_path)

        if os_name == "windows" and fname.lower().endswith(".msi"):
            install_zulu_msi(file_path)
            java_bin = "java"
            jdk_root = None
            mode = "msi"
        else:
            base = choose_permanent_base(os_name)
            tmp_extract = Path(tempfile.mkdtemp())

            try:
                extract_archive(file_path, tmp_extract)
                jdk_root = move_extracted_to_base(tmp_extract, base)
            finally:
                shutil.rmtree(tmp_extract, ignore_errors=True)
            
            if os_name == "windows":
                persist_env_windows_user(jdk_root)
                java_bin = str(jdk_root / "bin" / "java.exe")
            else:
                persist_env_posix(jdk_root)
                java_bin = str(jdk_root / "bin" / "java")
            mode = "portable"

            os.environ["JAVA_HOME"] = str(jdk_root)
            os.environ["PATH"] = f"{jdk_root}/bin:" + os.environ["PATH"]

            # Verify installation in current session
            print("\n" + "="*60)
            print("📋 Verifying Installation")
            print("="*60)
            success, version_info = verify_java_installation(java_bin)
            if success:
                print(f"\n✅ Java is working in the current Python session!")
                print(f"   {version_info}\n")
            else:
                print(f"\n⚠️  Warning: Could not verify Java installation: {version_info}\n")
            
            # Important note about shell reload
            if os_name in ("linux", "macos"):
                print("\n💡 Remember: If you open a NEW terminal later, Java will")
                print("   be available automatically. If you want to use it in")
                print("   THIS terminal, follow the instructions above.\n")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return {"java_bin": java_bin, "jdk_root": str(jdk_root) if jdk_root else None, "mode": mode, "os": os_name, "arch": arch}


# Uninstall existing Azul JDK installations (if any)
def uninstall_zulu_linux():
    base = Path.home() / ".local" / "share" / "java"
    removed = False

    if base.exists():
        for child in base.iterdir():
            if child.is_dir() and "zulu" in child.name.lower():
                print(f"⚠️ Found an existing JDK at {child}, removing...\n")
                shutil.rmtree(child, ignore_errors=True)
                removed = True
    
    # Clean up shell configuration files (both bash and zsh)
    candidates = [
        Path.home() / ".bashrc",
        Path.home() / ".profile",
        Path.home() / ".zshrc",
        Path.home() / ".zprofile"
    ]
    for target in candidates:
        if target.exists():
            text = target.read_text(encoding="utf-8")
            if "# >>> zulu-jdk (managed) >>>" in text:
                cleaned = []
                skip = False
                for line in text.splitlines():
                    if line.strip() == "# >>> zulu-jdk (managed) >>>":
                        skip = True
                        continue
                    if line.strip() == "# <<< zulu-jdk (managed) <<<":
                        skip = False
                        continue
                    if not skip:
                        cleaned.append(line)
                target.write_text("\n".join(cleaned), encoding="utf-8")
                print(f"🧹 Cleaned zulu-jdk block from {target}\n")
    if removed:
        print("✅ Existing Azul JDK installations removed.\n")
    else:
        print("ℹ️ No existing Azul JDK installations found.")

def uninstall_zulu_macos():
    # TODO: Implement macOS uninstallation similar to Linux
    # Should remove from ~/Library/Java/JavaVirtualMachines or /Library/Java/JavaVirtualMachines
    # and clean up .zshrc/.zprofile/.bashrc/.profile
    print("⚠️ macOS uninstallation not yet implemented. Please manually remove from Java installation directory.")
    pass

if __name__ == "__main__":
    setup_java(java_major=21)

    





