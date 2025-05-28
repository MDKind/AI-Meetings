"""
Check dependencies for AI Meetings project
"""

import sys
import importlib
from importlib import metadata

def check_package(package_name, import_name=None):
    """Check if a package is installed and can be imported"""
    if import_name is None:
        import_name = package_name
    
    # Check if installed
    try:
        version = metadata.version(package_name)
        installed = True
    except metadata.PackageNotFoundError:
        version = "Not installed"
        installed = False
    
    # Check if can be imported
    try:
        importlib.import_module(import_name)
        can_import = True
    except ImportError:
        can_import = False
    
    return installed, can_import, version

def main():
    print("=" * 60)
    print("AI Meetings - Dependency Check")
    print("=" * 60)
    print()
    
    # List of dependencies to check
    dependencies = [
        ("numpy", None),
        ("openai", None),
        ("python-dotenv", "dotenv"),
        ("sounddevice", None),
        ("scipy", None),
        ("pyaudio", None),
        ("comtypes", None),
        ("pycaw", None),
        ("torch", None),
        ("openai-whisper", "whisper"),
        ("pydub", None),
        ("ffmpeg-python", "ffmpeg"),
    ]
    
    essential = ["numpy", "openai", "python-dotenv", "sounddevice", "scipy"]
    windows_audio = ["comtypes", "pycaw", "pyaudio"]
    speech_recognition = ["torch", "openai-whisper"]
    
    all_good = True
    essential_good = True
    
    print("Checking dependencies...\n")
    
    for package, import_name in dependencies:
        installed, can_import, version = check_package(package, import_name)
        
        status = "✓" if installed and can_import else "✗"
        import_status = "OK" if can_import else "Import failed"
        
        if package in essential:
            marker = "[ESSENTIAL]"
            if not (installed and can_import):
                essential_good = False
        elif package in windows_audio:
            marker = "[WINDOWS AUDIO]"
        elif package in speech_recognition:
            marker = "[SPEECH RECOGNITION]"
        else:
            marker = "[OPTIONAL]"
        
        print(f"{status} {package:<20} {marker:<20} v{version:<15} {import_status}")
        
        if not (installed and can_import):
            all_good = False
    
    print("\n" + "=" * 60)
    
    if all_good:
        print("✓ All dependencies are installed and working!")
    elif essential_good:
        print("✓ Essential dependencies are installed.")
        print("⚠ Some optional dependencies are missing.")
        print("\nTo install missing dependencies:")
        print("  - For minimal setup: run minimal_install.bat")
        print("  - For full setup: pip install -r requirements.txt")
    else:
        print("✗ Essential dependencies are missing!")
        print("\nPlease run one of the following:")
        print("  1. minimal_install.bat (for basic functionality)")
        print("  2. pip install -r requirements.txt (for full functionality)")
    
    print("\n" + "=" * 60)
    
    # Check for .env file
    import os
    if os.path.exists(".env"):
        print("✓ .env file found")
        
        # Check if API key is set
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key and len(api_key) > 10:
                print("✓ OpenAI API key is set")
            else:
                print("⚠ OpenAI API key not found or invalid in .env")
        except:
            print("⚠ Could not check .env file")
    else:
        print("⚠ .env file not found")
        print("  Create .env file and add: OPENAI_API_KEY=your_key_here")
    
    print("=" * 60)
    
    # Platform info
    print(f"\nPlatform: {sys.platform}")
    print(f"Python version: {sys.version}")
    
    return essential_good

if __name__ == "__main__":
    success = main()
    input("\nPress Enter to continue...")
    sys.exit(0 if success else 1)
