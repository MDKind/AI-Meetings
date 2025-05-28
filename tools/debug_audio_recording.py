"""
Debug tool to check what is being recorded and save samples
"""

import sounddevice as sd
import numpy as np
import wave
import time
import os
from datetime import datetime

def monitor_and_record(device_index, device_name, duration=10):
    """Monitor audio levels and save recording"""
    print(f"\nМониторинг устройства: {device_name}")
    print("=" * 60)
    
    sample_rate = 44100
    channels = 2
    recording = []
    
    def callback(indata, frames, time_info, status):
        if status:
            print(f"Status: {status}")
        
        # Calculate volume
        volume = np.sqrt(np.mean(indata**2))
        
        # Create volume bar
        bar_length = int(volume * 50)
        bar = '█' * bar_length + '░' * (50 - bar_length)
        
        # Check what frequencies are present (simple spectrum analysis)
        if volume > 0.01:  # If there's sound
            # Simple frequency detection
            fft = np.fft.rfft(indata[:, 0])
            freqs = np.fft.rfftfreq(len(indata[:, 0]), 1/sample_rate)
            
            # Find dominant frequency
            dominant_freq_idx = np.argmax(np.abs(fft))
            dominant_freq = freqs[dominant_freq_idx]
            
            print(f"\rГромкость: [{bar}] {volume:.3f} | Частота: {dominant_freq:.0f}Hz", end='')
        else:
            print(f"\rГромкость: [{bar}] {volume:.3f} | Тишина", end='')
        
        # Store recording
        recording.append(indata.copy())
    
    # Create stream
    print("\nНачинаем мониторинг...")
    print("ВКЛЮЧИТЕ YOUTUBE ИЛИ МУЗЫКУ СЕЙЧАС!\n")
    
    with sd.InputStream(
        device=device_index,
        channels=channels,
        samplerate=sample_rate,
        blocksize=2048,
        callback=callback
    ):
        print(f"Запись {duration} секунд...")
        time.sleep(duration)
    
    print("\n\nЗапись завершена!")
    
    # Save recording
    if recording:
        audio_data = np.concatenate(recording)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_recording_{timestamp}.wav"
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())
        
        print(f"\nФайл сохранен: {filename}")
        print(f"Размер: {os.path.getsize(filename) / 1024 / 1024:.1f} MB")
        
        # Analyze recording
        max_volume = np.max(np.abs(audio_data))
        mean_volume = np.mean(np.abs(audio_data))
        
        print(f"\nАнализ записи:")
        print(f"- Максимальная громкость: {max_volume:.3f}")
        print(f"- Средняя громкость: {mean_volume:.3f}")
        
        if max_volume < 0.01:
            print("⚠ ЗАПИСЬ ОЧЕНЬ ТИХАЯ ИЛИ ПУСТАЯ!")
        elif mean_volume < 0.001:
            print("⚠ В записи есть только короткие звуки (возможно, только уведомления)")
        else:
            print("✓ Запись содержит звук")

def check_stereo_mix_settings():
    """Check and guide through Stereo Mix settings"""
    print("\nПРОВЕРКА НАСТРОЕК STEREO MIX")
    print("=" * 60)
    print("\n1. Откройте настройки Stereo Mix:")
    print("   - Панель управления → Звук → Запись")
    print("   - Правый клик на 'Стерео микшер' → Свойства")
    print("\n2. Проверьте вкладку 'Уровни':")
    print("   - Громкость должна быть 100%")
    print("   - Кнопка звука НЕ должна быть отключена")
    print("\n3. Проверьте вкладку 'Прослушать':")
    print("   - Галочка 'Прослушивать с данного устройства' должна быть СНЯТА")
    print("\n4. Вкладка 'Дополнительно':")
    print("   - Формат: 2 канала, 16 бит, 44100 Гц или выше")
    
    input("\nНажмите Enter после проверки настроек...")

def main():
    print("=" * 60)
    print("ОТЛАДКА ЗАПИСИ ЗВУКА")
    print("=" * 60)
    
    # Get devices
    devices = sd.query_devices()
    stereo_mix = None
    
    # Find Stereo Mix
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            if 'стерео микшер' in device['name'].lower() or 'stereo mix' in device['name'].lower():
                stereo_mix = (i, device['name'])
                break
    
    if not stereo_mix:
        print("✗ Stereo Mix не найден!")
        return
    
    device_id, device_name = stereo_mix
    print(f"\nНайден: [{device_id}] {device_name}")
    
    # Check settings
    check_stereo_mix_settings()
    
    # Test recording
    print("\n" + "=" * 60)
    print("ТЕСТ ЗАПИСИ")
    print("=" * 60)
    print("\n⚠ ВАЖНО: СЕЙЧАС НУЖНО:")
    print("1. Открыть YouTube в браузере")
    print("2. Включить любое видео со звуком")
    print("3. Убедиться, что звук идет в ваши наушники/колонки")
    print("4. НЕ отключать звук в браузере или Windows!")
    
    input("\nНажмите Enter когда включите видео...")
    
    # Monitor and record
    monitor_and_record(device_id, device_name, duration=10)
    
    print("\n" + "=" * 60)
    print("ВОЗМОЖНЫЕ ПРОБЛЕМЫ:")
    print("=" * 60)
    print("\n1. Если записались только уведомления:")
    print("   - Проверьте, что браузер использует то же устройство вывода")
    print("   - Проверьте громкость в браузере и Windows")
    print("\n2. Если запись пустая:")
    print("   - Stereo Mix может быть отключен в настройках")
    print("   - Драйвер звуковой карты может блокировать Stereo Mix")
    print("\n3. Если ничего не помогает:")
    print("   - Установите VB-Audio Virtual Cable")
    print("   - Используйте OBS Studio для захвата звука")

if __name__ == "__main__":
    main()
    input("\n\nНажмите Enter для выхода...")
