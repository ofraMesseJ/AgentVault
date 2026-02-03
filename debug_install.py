#!/usr/bin/env python3
"""
AgentVault Installer - DEBUG VERSION
"""
import sys
import os
import subprocess
import traceback

def debug_install():
    print("="*60)
    print("AgentVault Installer - Diagnostic Mode")
    print("="*60)
    
    # Step 1: Python Version
    print(f"\n1. Python Version: {sys.version}")
    if sys.version_info < (3, 11):
        print("❌ ERROR: Python 3.11+ required!")
        print(f"You have: {sys.version_info.major}.{sys.version_info.minor}")
        return False
    
    # Step 2: Check pip
    print("\n2. Checking pip...")
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "--version"], 
                              capture_output=True, text=True, check=True)
        print(f"✅ {result.stdout.strip()}")
    except Exception as e:
        print(f"❌ pip not found: {e}")
        print("Fix: python -m ensurepip --upgrade")
        return False
    
    # Step 3: Check current directory
    print(f"\n3. Current Directory: {os.getcwd()}")
    print(f"   Script Location: {os.path.dirname(os.path.abspath(__file__))}")
    
    # Step 4: Create directories (safe mode)
    print("\n4. Creating directories...")
    try:
        dirs = ["workspace", "data", "memory"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            print(f"   ✅ {d}/")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        traceback.print_exc()
        return False
    
    # Step 5: Test package install (one small package first)
    print("\n5. Testing package installation...")
    try:
        print("   Installing 'requests' (test)...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "requests", "--quiet"], 
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("   ✅ Package installation works")
        else:
            print(f"   ⚠️ Warning: {result.stderr}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("Diagnostics complete! If you see ✅ above, proceed with:")
    print("python -c \"import sys; print('Python OK')\"")
    print("="*60)
    return True

if __name__ == "__main__":
    try:
        debug_install()
    except Exception as e:
        print(f"\n💥 CRASH: {e}")
        traceback.print_exc()
        input("\nPress Enter to close...")