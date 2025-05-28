"""
Test audio recording from different sources
"""

import sounddevice as sd
import numpy as np
import wave
import time
import os
from datetime import datetime

def test_recording(device_index, device_name, duration=5):
    """Test recording from a specific device"""
    print(f"\nТестирование записи с устройства: {device_name}")
    print(f"Запись {duration} секунд...")
    
    try:
        # Parameters
        sample_rate = 44100
        channels = 2
        
        # Record
        print("Запись началась! Включите YouTube или музыку...")
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=channels,
            device=device_index
        )
        
        # Show progress
        for i in range(duration):
            print(f"Запись... {i+1}/{duration} сек", end='\r')
            time.sleep(1)
            
        sd.wait()
        print("\nЗапись завершена!")
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_recording_{device_name.replace(' ', '_')}_{timestamp}.wav"
        
        # Remove invalid characters from filename
        for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
            filename = filename.replace(char, '_')
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes((recording * 32767).astype(np.int16).tobytes())
        
        print(f"Файл сохранен: {filename}")
        
        # Check if recording has sound
        max_volume = np.max(np.abs(recording))
        if max_volume < 0.01:
            print("⚠ ВНИМАНИЕ: Записанный файл очень тихий или пустой!")
            print("  Возможно, устройство не захватывает звук.")
        else:
            print("✓ Звук записан успешно!")
            print(f"  Максимальная громкость: {max_volume:.2%}")
            
        return filename
        
    except Exception as e:
        print(f"✗ Ошибка при записи: {e}")
        return None

def main():
    print("=" * 60)
    print("ТЕСТ ЗАПИСИ ЗВУКА ИЗ ПРИЛОЖЕНИЙ")
    print("=" * 60)
    
    # Get devices
    devices = sd.query_devices()
    
    # Find Stereo Mix and similar devices
    stereo_mix_devices = []
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            name_lower = device['name'].lower()
            if any(kw in name_lower for kw in ['stereo mix', 'стереомикшер', 'what u hear', 'cable output']):
                stereo_mix_devices.append((i, device['name']))
    
    if not stereo_mix_devices:
        print("\n✗ НЕ НАЙДЕНО УСТРОЙСТВ ДЛЯ ЗАПИСИ ЗВУКА ИЗ ПРИЛОЖЕНИЙ!")
        print("\nЧто делать:")
        print("1. Включите Stereo Mix в настройках Windows")
        print("2. Или установите VB-Audio Virtual Cable")
        print("\nЗапустите setup_youtube_recording.bat для инструкций")
        return
    
    print("\nНайдены устройства для записи звука из приложений:")
    for idx, (device_id, device_name) in enumerate(stereo_mix_devices):
        print(f"{idx + 1}. [{device_id}] {device_name}")
    
    # Test each device
    print("\n" + "-" * 60)
    print("НАЧИНАЕМ ТЕСТИРОВАНИЕ")
    print("-" * 60)
    print("\n⚠ ВАЖНО: Включите YouTube видео или музыку СЕЙЧАС!")
    input("\nНажмите Enter когда будете готовы...")
    
    for device_id, device_name in stereo_mix_devices:
        test_recording(device_id, device_name, duration=5)
    
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ:")
    print("=" * 60)
    print("\n1. Проверьте созданные файлы test_recording_*.wav")
    print("2. Если файлы пустые - устройство не настроено правильно")
    print("3. Если звук есть - используйте это устройство в AI Meetings")
    
    # List created files
    print("\nСозданные файлы:")
    for file in os.listdir('.'):
        if file.startswith('test_recording_') and file.endswith('.wav'):
            size = os.path.getsize(file) / 1024 / 1024  # MB
            print(f"  - {file} ({size:.1f} MB)")

if __name__ == "__main__":
    main()
    input("\nНажмите Enter для выхода...")
