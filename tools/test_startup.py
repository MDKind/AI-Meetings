"""
Test startup script to check if the application starts without errors
"""

import sys
import os

print("Testing AI Meetings startup...")
print("=" * 60)

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test imports
try:
    print("1. Testing basic imports...")
    import numpy
    print("   ✓ numpy imported successfully")
    
    import sounddevice
    print("   ✓ sounddevice imported successfully")
    
    import scipy.signal
    print("   ✓ scipy.signal imported successfully")
    
    from dotenv import load_dotenv
    print("   ✓ python-dotenv imported successfully")
    
    import openai
    print("   ✓ openai imported successfully")
    
except ImportError as e:
    print(f"   ✗ Import error: {e}")
    print("\nPlease run: minimal_install.bat")
    sys.exit(1)

print("\n2. Testing project modules...")

try:
    from src.audio_capture import AudioCapture
    print("   ✓ AudioCapture imported successfully")
    
    from src.speech_recognition import SpeechRecognizer
    print("   ✓ SpeechRecognizer imported successfully")
    
    from src.chatgpt_client import ChatGPTClient
    print("   ✓ ChatGPTClient imported successfully")
    
    from src.realtime_processor import RealTimeAudioProcessor
    print("   ✓ RealTimeAudioProcessor imported successfully")
    
    from src.audio_synchronizer import AudioSynchronizer, EnhancedAudioProcessor
    print("   ✓ AudioSynchronizer imported successfully")
    
except ImportError as e:
    print(f"   ✗ Module import error: {e}")
    sys.exit(1)

print("\n3. Testing audio synchronizer filters...")

try:
    # Test the audio processor with different sample rates
    for sample_rate in [8000, 16000, 44100, 48000]:
        processor = EnhancedAudioProcessor(sample_rate=sample_rate)
        print(f"   ✓ Audio processor created successfully for {sample_rate}Hz")
        
except Exception as e:
    print(f"   ✗ Audio processor error: {e}")
    sys.exit(1)

print("\n4. Testing .env file...")

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    print("   ✓ OpenAI API key found in .env")
else:
    print("   ⚠ OpenAI API key not found in .env")
    print("     Create .env file and add: OPENAI_API_KEY=your_key_here")

print("\n" + "=" * 60)
print("✓ All basic tests passed!")
print("\nYou can now run: python main.py")
print("=" * 60)
