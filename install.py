#!/usr/bin/env python3
"""
AgentVault Automated Installer - FIXED VERSION
"""
import os
import sys
import subprocess
import time

def run_pip_install(package, desc):
    """Install a package, don't crash on failure"""
    print(f"\n⏳ {desc}...")
    try:
        # Use sys.executable to ensure correct python
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout per package
            check=False   # Don't crash on error
        )
        if result.returncode == 0:
            print(f"✅ {desc}")
            return True
        else:
            print(f"⚠️  {desc} - Warning: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"⚠️  {desc} - Error: {e}")
        return False

def main():
    print("="*60)
    print("AgentVault Automated Installer")
    print("="*60)
    
    # Directories
    print("\n📁 Creating directories...")
    dirs = ["workspace", "data", "memory", "tools", "agent"]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  ✓ {d}/")
    
    # Packages - install one by one so one failure doesn't kill everything
    print("\n📦 Installing packages (this takes 5-10 minutes)...")
    
    packages = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn server"),
        ("websockets", "Websockets"),
        ("aiohttp", "HTTP client"),
        ("python-multipart", "Multipart forms"),
        ("chromadb", "Vector database"),
        ("rich", "Terminal UI"),
        ("psutil", "System monitor"),
        ("playwright", "Browser automation"),
    ]
    
    failed = []
    for pkg, name in packages:
        if not run_pip_install(pkg, name):
            failed.append(name)
    
    if failed:
        print(f"\n⚠️  These failed (you can install manually later): {', '.join(failed)}")
    
    # Playwright browsers
    print("\n🌐 Installing Chromium browser...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )
        if result.returncode == 0:
            print("✅ Chromium installed")
        else:
            print("⚠️  Chromium install failed, run manually: playwright install chromium")
    except Exception as e:
        print(f"⚠️  Chromium error: {e}")
    
    # Check Ollama
    print("\n🤖 Checking Ollama...")
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print(f"✅ Ollama found: {result.stdout.strip()}")
            print("⏳ Pulling AI model (5-10 minutes, Ctrl+C to skip)...")
            subprocess.run(["ollama", "pull", "qwen2.5:7b"], check=False)
        else:
            print("⚠️  Ollama not found. Install from: https://ollama.com/download")
    except FileNotFoundError:
        print("⚠️  Ollama not installed. Download: https://ollama.com/download")
        print("   Then run: ollama pull qwen2.5:7b")
    
    # Create .env
    print("\n📝 Creating .env file...")
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write("""# AgentVault Configuration
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
IMAP_SERVER=imap.gmail.com
GITHUB_TOKEN=
OLLAMA_MODEL=qwen2.5:7b
""")
        print("✅ Created .env (edit with your credentials)")
    else:
        print("✅ .env already exists")
    
    # Create __init__.py files
    print("\n🐍 Creating package files...")
    for pkg in ["tools", "memory", "agent"]:
        init_file = os.path.join(pkg, "__init__.py")
        if not os.path.exists(init_file):
            open(init_file, "w").close()
            print(f"  ✓ {pkg}/__init__.py")
    
    # Done
    print("\n" + "="*60)
    print("INSTALLATION COMPLETE!")
    print("="*60)
    print("""
🚀 To start AgentVault:
   python main.py

📱 Web UI: Open agentvault_test_console.html in browser
🔌 WebSocket: ws://localhost:18789/ws/

⚠️  IMPORTANT: Edit .env file with your email credentials!

💡 Example commands:
   "Take screenshot of https://google.com"
   "Send email to test@example.com about Hello World"
   "Add event Meeting on 2024-12-25 at 14:00"
   "Query database SELECT * FROM calendar_events"
""")
    
    # Only pause if double-clicked (not if run from CMD)
    if sys.stdin.isatty() and os.name == 'nt':
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Installation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to close...")