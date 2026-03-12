#!/usr/bin/env python3
"""
Minecraft Server & Java Uninstaller
Removes installed components with user confirmation.
"""

import os
import sys
import shutil
import platform
from pathlib import Path





def clear_screen():
    os.system('clear')


def server_base_dir() -> Path:
    """Get the base directory where Minecraft servers are stored."""
    base = Path.home() / ".local" / "share" / "MinecraftServers"
    return base


def find_java_installation() -> dict | None:
    """Find installed Azul Zulu JDK."""
    # Check system-wide installation
    jvm_path = Path("/usr/local/lib/jvm")
    if jvm_path.exists():
        for jdk in jvm_path.iterdir():
            if jdk.is_dir() and "zulu" in jdk.name.lower():
                return {
                    "path": jdk,
                    "name": jdk.name,
                    "type": "system",
                    "profile_script": Path("/etc/profile.d/zulu-jdk.sh"),
                    "symlinks": [Path("/usr/local/bin/java"), 
                                Path("/usr/local/bin/javac"),
                                Path("/usr/local/bin/jar")]
                }
    
    # Check user installation
    user_path = Path.home() / ".local" / "share" / "java"
    if user_path.exists():
        for jdk in user_path.iterdir():
            if jdk.is_dir() and "zulu" in jdk.name.lower():
                return {
                    "path": jdk,
                    "name": jdk.name,
                    "type": "user",
                    "profile_script": None,
                    "symlinks": []
                }
    
    return None


def find_minecraft_servers() -> list[dict]:
    """Find all installed Minecraft servers."""
    base = server_base_dir()
    servers = []
    
    if not base.exists():
        return servers
    
    for folder in base.iterdir():
        if folder.is_dir():
            jar_path = folder / "server.jar"
            if jar_path.exists():
                # Try to read version info
                info_path = folder / "server_info.json"
                if info_path.exists():
                    try:
                        import json
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                        flavor = info.get("flavor", folder.name)
                        version = info.get("version", "unknown")
                    except:
                        flavor = folder.name
                        version = "unknown"
                else:
                    parts = folder.name.split("_")
                    flavor = parts[0] if parts else folder.name
                    version = parts[1] if len(parts) > 1 else "unknown"
                
                # Calculate folder size
                size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                
                servers.append({
                    "folder": folder,
                    "flavor": flavor,
                    "version": version,
                    "size_mb": size_mb
                })
    
    return servers


def uninstall_java(java_info: dict) -> bool:
    """Uninstall Azul Zulu JDK."""
    print(f"\n🗑️  Removing Java: {java_info['name']}")
    
    try:
        # Remove JDK directory
        if java_info['path'].exists():
            shutil.rmtree(java_info['path'])
            print(f"   ✅ Removed: {java_info['path']}")
        
        # Remove profile script (Linux)
        if java_info.get('profile_script') and java_info['profile_script'].exists():
            java_info['profile_script'].unlink()
            print(f"   ✅ Removed: {java_info['profile_script']}")
        
        # Remove symlinks
        for symlink in java_info.get('symlinks', []):
            if symlink.exists() or symlink.is_symlink():
                symlink.unlink()
                print(f"   ✅ Removed symlink: {symlink}")
        
        # Clean shell config files
        config_files = [
            Path.home() / ".bashrc",
            Path.home() / ".profile",
            Path.home() / ".zshrc",
            Path.home() / ".zprofile",
            Path("/root/.bashrc")
        ]
        
        for config in config_files:
            if config.exists():
                try:
                    text = config.read_text(encoding="utf-8")
                    if "# >>> zulu-jdk (managed) >>>" in text:
                        lines = text.splitlines()
                        cleaned = []
                        skip = False
                        for line in lines:
                            if "# >>> zulu-jdk (managed) >>>" in line:
                                skip = True
                                continue
                            if "# <<< zulu-jdk (managed) <<<" in line:
                                skip = False
                                continue
                            if not skip:
                                cleaned.append(line)
                        config.write_text("\n".join(cleaned), encoding="utf-8")
                        print(f"   ✅ Cleaned: {config}")
                except PermissionError:
                    print(f"   ⚠️  Could not clean {config} (permission denied)")
        
        print("\n✅ Java uninstalled successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error uninstalling Java: {e}")
        return False


def uninstall_server(server: dict) -> bool:
    """Uninstall a Minecraft server."""
    print(f"\n🗑️  Removing: {server['flavor'].capitalize()} {server['version']}")
    
    try:
        if server['folder'].exists():
            shutil.rmtree(server['folder'])
            print(f"   ✅ Removed: {server['folder']}")
        print(f"\n✅ Server uninstalled successfully!")
        return True
    except Exception as e:
        print(f"\n❌ Error uninstalling server: {e}")
        return False


def main_menu():
    """Display main uninstaller menu."""
    while True:
        clear_screen()
        print("=" * 55)
        print("🗑️   MINECRAFT SERVER & JAVA UNINSTALLER   🗑️")
        print("=" * 55)
        print()
        
        # Find installations
        java_info = find_java_installation()
        servers = find_minecraft_servers()
        
        print("  Found installations:\n")
        
        options = []
        
        # Java option
        if java_info:
            print(f"    [1] Java (Azul Zulu) - {java_info['name']}")
            print(f"        Location: {java_info['path']}")
            options.append(("java", java_info))
        else:
            print("    [1] Java - Not installed")
        
        print()
        
        # Server options
        if servers:
            for i, server in enumerate(servers, 2):
                print(f"    [{i}] {server['flavor'].capitalize()} {server['version']} ({server['size_mb']:.1f} MB)")
                print(f"        Location: {server['folder']}")
                options.append(("server", server))
        else:
            print("    No Minecraft servers found")
        
        print()
        print("    [A] Uninstall ALL (Java + all servers)")
        print("    [Q] Quit")
        print()
        
        choice = input("  Select what to uninstall: ").strip().lower()
        
        if choice == 'q':
            print("\n👋 Goodbye!")
            break
        
        elif choice == 'a':
            # Uninstall everything
            print("\n⚠️  WARNING: This will remove:")
            if java_info:
                print(f"    • Java: {java_info['name']}")
            for server in servers:
                print(f"    • {server['flavor'].capitalize()} {server['version']}")
            
            confirm = input("\n  Are you SURE? Type 'yes' to confirm: ").strip().lower()
            if confirm == 'yes':
                if java_info:
                    uninstall_java(java_info)
                for server in servers:
                    uninstall_server(server)
                print("\n✅ All components uninstalled!")
                input("\n  Press Enter to continue...")
            else:
                print("\n❌ Cancelled.")
                input("\n  Press Enter to continue...")
        
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    item_type, item = options[idx]
                    
                    if item_type == "java":
                        print(f"\n⚠️  This will remove Java: {item['name']}")
                        print("    Minecraft servers will NOT work without Java!")
                    else:
                        print(f"\n⚠️  This will remove: {item['flavor'].capitalize()} {item['version']}")
                        print(f"    All world data in {item['folder']} will be DELETED!")
                    
                    confirm = input("\n  Type 'yes' to confirm: ").strip().lower()
                    if confirm == 'yes':
                        if item_type == "java":
                            uninstall_java(item)
                        else:
                            uninstall_server(item)
                        input("\n  Press Enter to continue...")
                    else:
                        print("\n❌ Cancelled.")
                        input("\n  Press Enter to continue...")
                else:
                    print("\n❌ Invalid selection")
                    input("\n  Press Enter to continue...")
            except ValueError:
                print("\n❌ Invalid input")
                input("\n  Press Enter to continue...")


if __name__ == "__main__":
    def _is_root_unix() -> bool:
        try:
            return os.geteuid() == 0
        except AttributeError:
            return False

    # Check permissions for system-wide uninstall
    java_info = find_java_installation()
    
    if java_info and java_info.get('type') == 'system':
        if not _is_root_unix():
            print("⚠️  System-wide Java installation found.")
            print("   Run with sudo for full uninstall: sudo python3 uninstall.py")
            print()
    
    main_menu()
