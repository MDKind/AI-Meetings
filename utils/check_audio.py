import sounddevice as sd
import platform
print(f"Версия sounddevice: {sd.__version__}")
print(f"Информация о платформе: {platform.system()} {platform.release()}")

# Проверим доступные аудио устройства
devices = sd.query_devices()
print("\nДоступные аудио устройства:")
for i, device in enumerate(devices):
    if device['max_input_channels'] > 0:
        print(f"ВХОД {i}: {device['name']} (каналов: {device['max_input_channels']})")
    if device['max_output_channels'] > 0:
        print(f"ВЫХОД {i}: {device['name']} (каналов: {device['max_output_channels']})")

# Проверка WASAPI и Loopback
print("\nПроверка параметров для Windows WASAPI и Loopback:")
system = platform.system()
if system == "Windows":
    for device_idx, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            print(f"\nПроверка устройства вывода {device_idx}: {device['name']}")
            print("Доступные настройки:")
            
            # Проверка стандартных параметров
            try:
                info = sd.query_hostapis()
                for api_idx, api_info in enumerate(info):
                    print(f"API {api_idx}: {api_info['name']}")
                    if api_info['name'] == 'Windows WASAPI':
                        print(f"WASAPI API доступен (индекс: {api_idx})")
            except Exception as e:
                print(f"Ошибка при проверке API: {e}")
            
            # Проверка различных вариантов настройки loopback
            try:
                print("\nПроверка варианта 1 (extra_settings с loopback):")
                # Только для проверки, не запускаем поток
                stream_params = {
                    'samplerate': 16000,
                    'channels': 1,
                    'device': device_idx,
                    'dtype': 'float32',
                    'extra_settings': {
                        'loopback': True
                    }
                }
                print(f"Параметры поддерживаются: {stream_params}")
            except Exception as e:
                print(f"Ошибка при проверке параметров: {e}")
            
            # Попытаемся создать поток, но не запускать его
            try:
                print("\nСоздание тестового потока с использованием extra_settings.loopback:")
                stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    device=device_idx,
                    dtype='float32',
                    extra_settings={'loopback': True}
                )
                print("Тестовый поток успешно создан")
                # Не запускаем поток, только проверяем создание
                stream.close()
            except Exception as e:
                print(f"Ошибка при создании тестового потока: {e}")
            
            break  # Достаточно проверить одно устройство вывода
else:
    print(f"Платформа {system} не поддерживает WASAPI loopback")

print("\nПроверка завершена.")