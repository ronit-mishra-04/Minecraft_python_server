#!/usr/bin/env python3
"""
Minecraft Server Control Panel
Run this file to start/stop your Minecraft server.
"""

import os
import sys
import json
import platform
import subprocess
import time
import threading
import queue
from pathlib import Path


def server_base_dir() -> Path:
    """Get the base directory where Minecraft servers are stored."""
    os_name = platform.system().lower()
    if "windows" in os_name:
        base = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData")) / "MinecraftServers"
    elif "darwin" in os_name:
        base = Path.home() / "Library" / "Application Support" / "MinecraftServers"
    else:
        base = Path.home() / ".local" / "share" / "MinecraftServers"
    return base


def find_installed_servers() -> list[dict]:
    """Find all installed Minecraft servers."""
    base = server_base_dir()
    servers = []
    
    if not base.exists():
        return servers
    
    for folder in base.iterdir():
        if folder.is_dir():
            jar_path = folder / "server.jar"
            eula_path = folder / "eula.txt"
            info_path = folder / "server_info.json"
            
            if jar_path.exists():
                # Check if EULA is accepted
                eula_accepted = False
                if eula_path.exists():
                    content = eula_path.read_text(encoding="utf-8")
                    eula_accepted = "eula=true" in content.lower()
                
                # Try to read version from server_info.json first
                if info_path.exists():
                    try:
                        import json
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                        flavor = info.get("flavor", folder.name)
                        version = info.get("version", "unknown")
                    except (json.JSONDecodeError, KeyError):
                        # Fallback to folder name parsing
                        name = folder.name
                        parts = name.split("_")
                        flavor = parts[0] if parts else name
                        version = parts[1] if len(parts) > 1 else "unknown"
                else:
                    # Fallback to folder name parsing
                    name = folder.name
                    parts = name.split("_")
                    flavor = parts[0] if parts else name
                    version = parts[1] if len(parts) > 1 else "unknown"
                
                servers.append({
                    "name": folder.name,
                    "flavor": flavor,
                    "version": version,
                    "folder": folder,
                    "eula_accepted": eula_accepted
                })
    
    return servers


def get_java_bin() -> str:
    """Get the Java binary path."""
    # Check for Azul Zulu installation
    os_name = platform.system().lower()
    
    if "darwin" in os_name:
        # Check common macOS locations for Azul Zulu
        zulu_paths = [
            Path.home() / ".azul" / "zulu",
            Path("/Library/Java/JavaVirtualMachines")
        ]
        for base in zulu_paths:
            if base.exists():
                for jdk in base.iterdir():
                    java_bin = jdk / "bin" / "java"
                    if java_bin.exists():
                        return str(java_bin)
                    # macOS bundle structure
                    java_bin = jdk / "Contents" / "Home" / "bin" / "java"
                    if java_bin.exists():
                        return str(java_bin)
    
    elif "windows" in os_name:
        # Check Program Files for Zulu
        pf = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
        zulu_dir = pf / "Zulu"
        if zulu_dir.exists():
            for jdk in zulu_dir.iterdir():
                java_bin = jdk / "bin" / "java.exe"
                if java_bin.exists():
                    return str(java_bin)
    
    # Fallback to system java
    return "java"


def run_server_in_new_terminal(java_bin: str, folder: Path, min_ram="1G", max_ram="2G"):
    """Launch the Minecraft server in a new terminal window."""
    jar_cmd = f'cd "{folder}" && "{java_bin}" -Xms{min_ram} -Xmx{max_ram} -jar server.jar nogui'
    os_name = platform.system().lower()
    
    print(f"🚀 Starting server in: {folder}")
    
    if "darwin" in os_name:  # macOS
        apple_script = f'''
        tell application "Terminal"
            activate
            do script "{jar_cmd}"
        end tell
        '''
        subprocess.Popen(["osascript", "-e", apple_script])
        print("✅ Server launched in a new Terminal window!")
        
    elif "windows" in os_name:
        CREATE_NEW_CONSOLE = 0x00000010
        cmd = [java_bin, f"-Xms{min_ram}", f"-Xmx{max_ram}", "-jar", "server.jar", "nogui"]
        subprocess.Popen(cmd, cwd=str(folder), creationflags=CREATE_NEW_CONSOLE)
        print("✅ Server launched in a new console window!")
        
    else:  # Linux - try multiple terminal emulators
        # List of terminal emulators to try (in order of preference)
        terminals = [
            # GNOME Terminal
            (["gnome-terminal", "--", "bash", "-c", jar_cmd + "; exec bash"], "GNOME Terminal"),
            # Konsole (KDE)
            (["konsole", "-e", "bash", "-c", jar_cmd + "; exec bash"], "Konsole"),
            # XFCE Terminal
            (["xfce4-terminal", "-e", f"bash -c '{jar_cmd}; exec bash'"], "XFCE Terminal"),
            # MATE Terminal
            (["mate-terminal", "-e", f"bash -c '{jar_cmd}; exec bash'"], "MATE Terminal"),
            # LXTerminal
            (["lxterminal", "-e", f"bash -c '{jar_cmd}; exec bash'"], "LXTerminal"),
            # Tilix
            (["tilix", "-e", f"bash -c '{jar_cmd}'"], "Tilix"),
            # XTerm (usually available as fallback)
            (["xterm", "-hold", "-e", jar_cmd], "XTerm"),
        ]
        
        launched = False
        error_msg = None
        
        for cmd, term_name in terminals:
            try:
                # Use subprocess.run with a short timeout to see if it fails immediately
                # Most terminal errors (like DBUS issues) happen right away
                proc = subprocess.Popen(
                    cmd, 
                    cwd=str(folder),
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE
                )
                # Wait briefly to catch immediate failures
                time.sleep(0.5)
                
                # Check if process died immediately (indicates an error)
                ret = proc.poll()
                if ret is not None and ret != 0:
                    # Process exited with error - read stderr
                    stderr = proc.stderr.read().decode() if proc.stderr else ""
                    error_msg = f"{term_name} failed: {stderr.strip()}"
                    continue
                
                # Also check for error output without exit (some terminals do this)
                if proc.stderr:
                    import select
                    if select.select([proc.stderr], [], [], 0)[0]:
                        stderr = proc.stderr.read().decode()
                        if "error" in stderr.lower() or "failed" in stderr.lower():
                            error_msg = f"{term_name}: {stderr.strip()}"
                            proc.terminate()
                            continue
                
                print(f"✅ Server launched in {term_name}!")
                launched = True
                break
                
            except FileNotFoundError:
                continue
            except Exception as e:
                error_msg = str(e)
                continue
        
        if not launched:
            # No terminal emulator found or all failed - ask user what to do
            print("\n⚠️  Could not launch server in a new terminal window!")
            if error_msg:
                print(f"    Last error: {error_msg}\n")
            else:
                print("    No graphical terminal emulator found.\n")
            print("    This often happens when running with 'sudo' (DBUS issues).")
            print("    Try running WITHOUT sudo: python3 server_ui.py\n")
            print("    Options:")
            print("    1) Run in current terminal (you won't be able to use the control panel)")
            print("    2) Exit and try running without sudo\n")
            
            choice = input("    Continue in current terminal? (yes/no): ").strip().lower()
            
            if choice in ("yes", "y", "1"):
                print("\n🚀 Starting server in current terminal (Ctrl+C to stop)...\n")
                print("=" * 50)
                cmd = [java_bin, f"-Xms{min_ram}", f"-Xmx{max_ram}", "-jar", "server.jar", "nogui"]
                subprocess.run(cmd, cwd=str(folder))
            else:
                print("\n💡 To install a terminal emulator, try one of these:")
                print("    sudo apt install gnome-terminal   # Ubuntu/Debian")
                print("    sudo apt install xterm            # Lightweight option")
                print("    sudo apt install konsole          # KDE")
            return
    
    print("   First start may take a minute to create worlds.")


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if platform.system().lower() == 'windows' else 'clear')


def input_with_status_check(prompt: str, folder: Path, check_interval: float = 2.0) -> tuple[str | None, bool]:
    """
    Wait for user input while monitoring server status.
    Uses select() for non-blocking input on Unix systems.
    
    Returns:
        (user_input, status_changed) - user_input is None if status changed before input
    """
    import select
    import sys
    
    print(prompt, end='', flush=True)
    
    # Get initial status
    initial_status, _ = get_server_status(folder)
    
    input_buffer = ""
    last_check = time.time()
    
    # Set stdin to non-blocking mode on Unix
    os_name = platform.system().lower()
    
    if os_name != "windows":
        import termios
        import tty
        
        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)
        
        try:
            # Set terminal to raw mode (character-by-character input)
            tty.setcbreak(sys.stdin.fileno())
            
            while True:
                # Check if input is available (non-blocking)
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    char = sys.stdin.read(1)
                    if char == '\n' or char == '\r':
                        print()  # Echo newline
                        return input_buffer.strip().lower(), False
                    elif char == '\x7f' or char == '\b':  # Backspace
                        if input_buffer:
                            input_buffer = input_buffer[:-1]
                            print('\b \b', end='', flush=True)  # Erase character
                    elif char == '\x03':  # Ctrl+C
                        raise KeyboardInterrupt
                    else:
                        input_buffer += char
                        print(char, end='', flush=True)  # Echo character
                
                # Periodically check server status
                if time.time() - last_check >= check_interval:
                    last_check = time.time()
                    current_status, _ = get_server_status(folder)
                    if current_status != initial_status:
                        print("\n\n  🔄 Server status changed! Refreshing...")
                        time.sleep(0.5)
                        return None, True
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    else:
        # Windows fallback - use threading (Enter still required after status change)
        input_queue = queue.Queue()
        status_changed_event = threading.Event()
        
        def input_thread():
            try:
                result = input()
                input_queue.put(result)
            except EOFError:
                input_queue.put("")
        
        def monitor_thread():
            nonlocal initial_status
            while not status_changed_event.is_set():
                time.sleep(check_interval)
                current_status, _ = get_server_status(folder)
                if current_status != initial_status:
                    status_changed_event.set()
                    break
        
        inp_thread = threading.Thread(target=input_thread, daemon=True)
        mon_thread = threading.Thread(target=monitor_thread, daemon=True)
        inp_thread.start()
        mon_thread.start()
        
        while True:
            if status_changed_event.is_set():
                print("\n\n  🔄 Server status changed! Refreshing...")
                time.sleep(0.5)
                return None, True
            try:
                result = input_queue.get(timeout=0.2)
                return result.strip().lower(), False
            except queue.Empty:
                continue


def select_server(servers: list[dict]) -> dict | None:
    """Let user select which server to control."""
    clear_screen()
    print("=" * 50)
    print("🎮  MINECRAFT SERVER SELECTOR  🎮")
    print("=" * 50)
    print()
    
    if not servers:
        print("  ❌ No servers found!")
        print("  Run server.py first to install a server.")
        print()
        input("  Press Enter to exit...")
        return None
    
    print("  Available servers:\n")
    for i, server in enumerate(servers, 1):
        status = "✅" if server["eula_accepted"] else "⚠️ EULA not accepted"
        print(f"    {i}) {server['flavor'].capitalize()} {server['version']} {status}")
    
    print(f"\n    0) Exit")
    print()
    
    choice = input("  Select server (number): ").strip()
    
    try:
        idx = int(choice)
        if idx == 0:
            return None
        if 1 <= idx <= len(servers):
            return servers[idx - 1]
    except ValueError:
        pass
    
    print("\n  ❌ Invalid selection")
    time.sleep(1)
    return select_server(servers)


def is_port_listening(port: int = 25565, host: str = "127.0.0.1") -> bool:
    """Check if a port is listening (server is ready to accept connections)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def get_server_status(folder: Path) -> tuple[str, int | None]:
    """Check the Minecraft server status.
    
    Returns (status, pid) tuple where status is one of:
    - "stopped" - No server process running
    - "starting" - Process running but not ready (port not listening)
    - "running" - Server is ready and accepting connections
    """
    pid = None
    process_running = False
    
    try:
        # Check for java processes with server.jar
        if platform.system().lower() == "windows":
            result = subprocess.run(
                ["wmic", "process", "where", "name='java.exe'", "get", "commandline,processid"],
                capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if "server.jar" in line and str(folder) in line:
                    parts = line.strip().split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            process_running = True
                            break
                        except ValueError:
                            process_running = True
        else:
            # Unix: use pgrep
            result = subprocess.run(
                ["pgrep", "-f", f"java.*server.jar"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid_str in pids:
                    try:
                        pid = int(pid_str)
                        cwd_link = Path(f"/proc/{pid}/cwd")
                        if cwd_link.exists():
                            try:
                                cwd = cwd_link.resolve()
                                if cwd == folder.resolve():
                                    process_running = True
                                    break
                            except (PermissionError, OSError):
                                process_running = True
                                break
                    except (ValueError, FileNotFoundError):
                        continue
                # Fallback: if we found any java server process
                if not process_running and pids and pids[0]:
                    process_running = True
                    pid = int(pids[0]) if pids[0].isdigit() else None
    except Exception:
        pass
    
    if not process_running:
        return "stopped", None
    
    # Process is running - check if server is ready (port listening)
    if is_port_listening(25565):
        return "running", pid
    else:
        return "starting", pid


def stop_server(pid: int | None = None) -> bool:
    """Stop the Minecraft server by killing the java process."""
    try:
        if pid:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(2)
            # Check if still running
            try:
                os.kill(pid, 0)  # Just check if process exists
                os.kill(pid, 9)  # SIGKILL if still alive
            except OSError:
                pass  # Process already dead
            return True
        else:
            # Try to kill any java server.jar process
            if platform.system().lower() == "windows":
                subprocess.run(["taskkill", "/F", "/IM", "java.exe"], capture_output=True)
            else:
                subprocess.run(["pkill", "-f", "java.*server.jar"], capture_output=True)
            return True
    except Exception as e:
        print(f"Error stopping server: {e}")
        return False


# Global to track launched process
_server_process: subprocess.Popen | None = None


def run_server_direct(java_bin: str, folder: Path, min_ram="1G", max_ram="2G") -> subprocess.Popen:
    """Start the Minecraft server as a background process (in current terminal)."""
    cmd = [java_bin, f"-Xms{min_ram}", f"-Xmx{max_ram}", "-jar", "server.jar", "nogui"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(folder),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return proc


def server_control_ui(java_bin: str, server: dict):
    """Display a persistent UI for controlling the Minecraft server."""
    global _server_process
    
    folder = server["folder"]
    flavor = server["flavor"]
    version = server["version"]
    
    while True:
        # Check actual server status
        status, pid = get_server_status(folder)
        
        clear_screen()
        print("=" * 50)
        print("🎮  MINECRAFT SERVER CONTROL PANEL  🎮")
        print("=" * 50)
        print(f"\n  Server Type: {flavor.capitalize()}")
        print(f"  Version:     {version}")
        print(f"  Location:    {folder}")
        print()
        
        if status == "running":
            # Server is fully ready
            print("  📡 Status: \033[92m● RUNNING\033[0m", end="")
            if pid:
                print(f" (PID: {pid})")
            else:
                print()
            print("     Server is ready and accepting connections!")
            print()
            print("-" * 50)
            print("\n  Commands:")
            print("    • stop  (or 1) - Stop the server")
            print("    • back  (or 2) - Go back to server selection")
            print("    • exit  (or 3) - Close this control panel")
            print()
            
            # Use threaded input that monitors status in background
            user_input, status_changed = input_with_status_check("  Enter command: ", folder)
            
            if status_changed:
                # Status changed (server stopped), refresh UI
                continue
            
            if user_input in ("stop", "1"):
                print("\n🛑 Stopping server...")
                if stop_server(pid):
                    print("✅ Server stopped.")
                    _server_process = None
                else:
                    print("⚠️  Could not stop server automatically.")
                    print("    Try manually: go to server terminal and type 'stop'")
                time.sleep(2)
                
            elif user_input in ("back", "2"):
                print("\n⚠️  Warning: Returning while server is running!")
                confirm = input("   Continue? (yes/no): ").strip().lower()
                if confirm in ("yes", "y"):
                    return True
                    
            elif user_input in ("exit", "3"):
                print("\n⚠️  Warning: Server will keep running!")
                confirm = input("   Exit anyway? (yes/no): ").strip().lower()
                if confirm in ("yes", "y"):
                    print("\n👋 Goodbye! Server continues running.")
                    return False
                    
        elif status == "starting":
            # Process running but not ready yet
            print("  📡 Status: \033[93m● STARTING...\033[0m", end="")
            if pid:
                print(f" (PID: {pid})")
            else:
                print()
            print("     Server is loading... please wait.")
            print()
            print("-" * 50)
            print("\n  Auto-refreshing every 3 seconds...")
            print("  Commands:")
            print("    • stop  (or 1) - Stop the server")
            print("    • back  (or 2) - Go back (server continues)")
            print()
            
            # Don't block - just wait briefly then refresh
            time.sleep(3)
            
        else:  # stopped
            print("  📡 Status: \033[91m● STOPPED\033[0m")
            print()
            print("-" * 50)
            print("\n  Commands:")
            print("    • start (or 1) - Start the server")
            print("    • back  (or 2) - Go back to server selection")
            print("    • exit  (or 3) - Close this control panel")
            print()
            
            # Use threaded input that monitors status in background
            user_input, status_changed = input_with_status_check("  Enter command: ", folder)
            
            if status_changed:
                # Status changed (server started), refresh UI
                continue
            
            if user_input in ("start", "1"):
                if not server["eula_accepted"]:
                    print("\n⚠️  EULA not accepted! Run server.py first to accept the EULA.")
                    time.sleep(2)
                else:
                    print("\n🚀 Starting server...")
                    run_server_in_new_terminal(java_bin, folder)
                    print("\n  Server is starting...")
                    time.sleep(2)  # Brief pause before showing STARTING status
                    
            elif user_input in ("back", "2"):
                return True
                
            elif user_input in ("exit", "3"):
                print("\n👋 Goodbye!")
                return False
                
            else:
                if user_input:
                    print(f"\n❌ Unknown command: '{user_input}'")
                    time.sleep(1)


def main():
    """Main entry point for the server control UI."""
    java_bin = get_java_bin()
    
    while True:
        servers = find_installed_servers()
        server = select_server(servers)
        
        if server is None:
            print("\n👋 Goodbye!")
            break
        
        # Show control UI for selected server
        continue_selecting = server_control_ui(java_bin, server)
        
        if not continue_selecting:
            break


if __name__ == "__main__":
    main()
