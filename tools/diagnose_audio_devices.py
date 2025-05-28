"""
Audio devices diagnostic tool
Helps identify available audio devices for system sound capture
"""

import sounddevice as sd
import platform
import os

def check_audio_devices():
    """Check and display all available audio devices"""
    print("=" * 80)
    print("AUDIO DEVICES DIAGNOSTIC")
    print("=" * 80)
    print(f"Platform: {platform.system()} {platform.version()}")
    print(f"Python: {platform.python_version()}")
    print()
    
    # Get all devices
    devices = sd.query_devices()
    
    # Separate input and output devices
    input_devices = []
    output_devices = []
    stereo_mix_devices = []
    virtual_devices = []
    
    print("ANALYZING DEVICES...")
    print("-" * 80)
    
    for i, device in enumerate(devices):
        device_name = device['name'].lower()
        
        # Check for system sound capture devices
        is_stereo_mix = any(keyword in device_name for keyword in [
            'stereo mix', 'стереомикшер', 'stereomix', 
            'what u hear', 'what you hear', 'wave out mix'
        ])
        
        is_virtual = any(keyword in device_name for keyword in [
            'virtual', 'cable', 'vb-audio', 'voicemeeter'
        ])
        
        if device['max_input_channels'] > 0:
            input_devices.append((i, device))
            if is_stereo_mix:
                stereo_mix_devices.append((i, device))
            if is_virtual:
                virtual_devices.append((i, device))
                
        if device['max_output_channels'] > 0:
            output_devices.append((i, device))
    
    # Display results
    print(f"\nFOUND {len(devices)} TOTAL DEVICES:")
    print(f"  - {len(input_devices)} input devices")
    print(f"  - {len(output_devices)} output devices")
    print(f"  - {len(stereo_mix_devices)} Stereo Mix devices")
    print(f"  - {len(virtual_devices)} Virtual Cable devices")
    
    print("\n" + "=" * 80)
    print("SYSTEM SOUND CAPTURE DEVICES (for recording computer audio):")
    print("=" * 80)
    
    if stereo_mix_devices or virtual_devices:
        print("\n✓ AVAILABLE DEVICES FOR SYSTEM SOUND:")
        
        if stereo_mix_devices:
            print("\n  Stereo Mix devices:")
            for idx, device in stereo_mix_devices:
                print(f"    [{idx}] {device['name']}")
                print(f"        Channels: {device['max_input_channels']}")
                print(f"        Sample rate: {device['default_samplerate']} Hz")
                
        if virtual_devices:
            print("\n  Virtual Cable devices:")
            for idx, device in virtual_devices:
                print(f"    [{idx}] {device['name']}")
                print(f"        Channels: {device['max_input_channels']}")
                print(f"        Sample rate: {device['default_samplerate']} Hz")
    else:
        print("\n✗ NO SYSTEM SOUND CAPTURE DEVICES FOUND!")
        print("\nTo record system audio, you need one of these:")
        print("  1. Enable 'Stereo Mix' in Windows Sound settings")
        print("  2. Install VB-Audio Virtual Cable")
        print("  3. Install VoiceMeeter")
        print("\nSee: docs\\SYSTEM_AUDIO_SETUP.md for detailed instructions")
    
    print("\n" + "=" * 80)
    print("ALL INPUT DEVICES (including microphones):")
    print("=" * 80)
    
    for idx, device in input_devices:
        device_type = "MICROPHONE"
        if any(kw in device['name'].lower() for kw in ['stereo mix', 'стереомикшер', 'what u hear']):
            device_type = "SYSTEM SOUND"
        elif 'virtual' in device['name'].lower() or 'cable' in device['name'].lower():
            device_type = "VIRTUAL"
            
        print(f"\n[{idx}] {device['name']} ({device_type})")
        print(f"    Max channels: {device['max_input_channels']}")
        print(f"    Default sample rate: {device['default_samplerate']} Hz")
        
    print("\n" + "=" * 80)
    print("ALL OUTPUT DEVICES (speakers/headphones):")
    print("=" * 80)
    
    for idx, device in output_devices:
        print(f"\n[{idx}] {device['name']}")
        print(f"    Max channels: {device['max_output_channels']}")
        print(f"    Default sample rate: {device['default_samplerate']} Hz")
    
    # Windows-specific checks
    if platform.system() == 'Windows':
        print("\n" + "=" * 80)
        print("WINDOWS-SPECIFIC CHECKS:")
        print("=" * 80)
        
        # Check if comtypes is available for WASAPI
        try:
            import comtypes
            print("\n✓ comtypes is installed (Windows WASAPI support available)")
        except ImportError:
            print("\n✗ comtypes not installed (Windows WASAPI not available)")
            print("  Install with: pip install comtypes")
            
        # Check if Stereo Mix might be disabled
        if not stereo_mix_devices:
            print("\n⚠ Stereo Mix not found. It might be:")
            print("  1. Disabled in Sound settings")
            print("  2. Not supported by your sound card")
            print("  3. Hidden by audio drivers")
            print("\nTo enable Stereo Mix:")
            print("  1. Right-click speaker icon → Sounds")
            print("  2. Recording tab → Right-click → Show Disabled Devices")
            print("  3. Enable 'Stereo Mix' if found")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS FOR AI MEETINGS:")
    print("=" * 80)
    
    if stereo_mix_devices:
        idx, device = stereo_mix_devices[0]
        print(f"\n1. Use Stereo Mix:")
        print(f"   - Select device [{idx}] {device['name']} as 'Input Device'")
        print(f"   - Use 'Standard' or 'Enhanced' recording mode")
    elif virtual_devices:
        idx, device = virtual_devices[0]
        print(f"\n1. Use Virtual Cable:")
        print(f"   - Select device [{idx}] {device['name']} as 'Input Device'")
        print(f"   - Configure your audio to output through the virtual cable")
    else:
        print("\n1. No system audio device found!")
        print("   - Install VB-Audio Virtual Cable (recommended)")
        print("   - Or enable Stereo Mix in Windows settings")
        print("   - See docs\\SYSTEM_AUDIO_SETUP.md for help")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    check_audio_devices()
    input("\nPress Enter to exit...")
