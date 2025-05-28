"""
Утилита для диагностики и настройки звуковых устройств для проекта AI Meetings
"""
import sounddevice as sd
import numpy as np
import platform
import sys
import os
import time
from queue import Queue
import threading

def highlight(text):
    """Выделяет текст в консоли"""
    return f"\033[1;33m{text}\033[0m"

def print_header(title):
    """Печатает заголовок раздела"""
    print("\n" + "=" * 80)
    print(f"    {highlight(title)}")
    print("=" * 80)

def check_system_info():
    """Проверяет информацию о системе"""
    print_header("Информация о системе")
    system = platform.system()
    release = platform.release()
    version = platform.version()
    
    print(f"Операционная система: {highlight(system)} {release}")
    print(f"Версия системы: {version}")
    print(f"Python версия: {highlight(sys.version)}")
    print(f"Sounddevice версия: {highlight(sd.__version__)}")
    print(f"NumPy версия: {highlight(np.__version__)}")
    
    if system == "Windows":
        print("\nПроверка Windows-специфичных компонентов:")
        import ctypes
        try:
            # Проверка прав администратора
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            print(f"Права администратора: {highlight('Да' if is_admin else 'Нет')}")
        except:
            print("Не удалось проверить права администратора")
        
        # Проверка наличия звуковых компонентов Windows
        try:
            import winreg
            audio_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                       r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio")
            print("Звуковые компоненты Windows: Обнаружены")
            winreg.CloseKey(audio_key)
        except:
            print("Не удалось проверить компоненты аудио в реестре Windows")
    
    return system

def check_audio_devices():
    """Анализирует звуковые устройства в системе"""
    print_header("Анализ звуковых устройств")
    
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        
        print(f"Доступные аудио API:")
        for i, api in enumerate(hostapis):
            print(f"API {i}: {highlight(api['name'])} - {'Активен' if api['name'] else 'Неактивен'}")
        
        print(f"\nИнформация о звуковых устройствах:")
        print(f"Всего устройств: {highlight(len(devices))}")
        
        # Проверяем наличие Stereo Mix
        stereo_mix_found = False
        
        # Отдельные списки для микрофонов и аудиовыхода
        microphones = []
        outputs = []
        loopback_candidates = []
        
        # Анализируем устройства
        for i, device in enumerate(devices):
            device_info = f"Устройство {i}: {device['name']}"
            if device['max_input_channels'] > 0:
                input_info = f"[ВХОД: {device['max_input_channels']} каналов]"
                if ("stereo mix" in device['name'].lower() or 
                    "стереомикшер" in device['name'].lower() or 
                    "what u hear" in device['name'].lower()):
                    stereo_mix_found = True
                    device_info += f" {highlight('!!! STEREO MIX !!!')} {input_info}"
                    loopback_candidates.append((i, device['name']))
                else:
                    device_info += f" [МИКРОФОН] {input_info}"
                    microphones.append((i, device['name']))
                
            if device['max_output_channels'] > 0:
                output_info = f"[ВЫХОД: {device['max_output_channels']} каналов]"
                device_info += f" {output_info}"
                outputs.append((i, device['name']))
                
                # Потенциальные устройства для loopback
                if "speaker" in device['name'].lower() or "динамик" in device['name'].lower() or \
                   "headphone" in device['name'].lower() or "наушник" in device['name'].lower():
                    loopback_candidates.append((i, device['name']))
            
            print(device_info)
        
        if stereo_mix_found:
            print(f"\n{highlight('Обнаружен Stereo Mix!')} Запись системного звука возможна стандартным способом.")
        else:
            print(f"\n{highlight('Stereo Mix не обнаружен!')} Будет предпринята попытка использования loopback режима.")
        
        return {
            "devices": devices,
            "hostapis": hostapis,
            "stereo_mix_found": stereo_mix_found,
            "microphones": microphones,
            "outputs": outputs,
            "loopback_candidates": loopback_candidates
        }
    except Exception as e:
        print(f"Ошибка при анализе звуковых устройств: {e}")
        return None

def test_audio_device(device_idx, is_input=True, duration=3):
    """Тестирует указанное аудио устройство"""
    device_name = sd.query_devices()[device_idx]['name']
    
    if is_input:
        print(f"Тестирование устройства ввода {device_idx}: {device_name}")
        print(f"Запись начнется через 2 секунды и продлится {duration} секунды...")
        time.sleep(2)
        
        try:
            # Для сбора аудио данных
            q = Queue()
            
            def callback(indata, frames, time, status):
                if status:
                    print(f"Статус: {status}")
                q.put(indata.copy())
            
            # Запускаем запись
            stream = sd.InputStream(
                device=device_idx,
                channels=1,
                samplerate=16000,
                callback=callback
            )
            
            with stream:
                print(f"Запись начата с устройства {device_idx}...")
                time.sleep(duration)
                print("Запись завершена")
            
            # Анализируем записанное аудио
            data = []
            while not q.empty():
                data.append(q.get())
            
            if data:
                audio_data = np.concatenate(data)
                volume = np.abs(audio_data).mean()
                
                print(f"Средняя громкость: {volume:.2f}")
                if volume > 0.001:
                    print(f"{highlight('Устройство активно и передает аудио сигнал')}")
                else:
                    print(f"{highlight('Устройство не передает аудио сигнал или сигнал слишком тихий')}")
                
                return True, volume
            else:
                print("Не удалось получить аудио данные")
                return False, 0
                
        except Exception as e:
            print(f"Ошибка при тестировании устройства: {e}")
            return False, 0
    else:
        print(f"Тестирование устройства вывода {device_idx}: {device_name} не реализовано")
        return False, 0

def test_loopback(output_device_idx):
    """Тестирует режим loopback для устройства вывода"""
    print_header(f"Тестирование режима loopback для устройства {output_device_idx}")
    device_name = sd.query_devices()[output_device_idx]['name']
    
    print(f"Тестирование loopback для устройства {output_device_idx}: {device_name}")
    print("Сейчас будет предпринята попытка записи звука с устройства вывода...")
    
    # Различные параметры для тестирования loopback
    loopback_methods = [
        # Метод 1: newer versions with extra_settings
        {'extra_settings': {'loopback': True}},
        # Метод 2: older versions with wasapi
        {'wasapi': True, 'loopback': True},
        # Метод 3: just loopback
        {'loopback': True}
    ]
    
    successful_method = None
    
    for i, method in enumerate(loopback_methods):
        print(f"\nПопытка метода {i+1}: {method}")
        
        try:
            # Для сбора аудио данных
            q = Queue()
            
            def callback(indata, frames, time, status):
                if status:
                    print(f"Статус: {status}")
                q.put(indata.copy())
            
            # Пробуем установить поток
            try:
                stream = sd.InputStream(
                    device=output_device_idx,
                    channels=1,
                    samplerate=16000,
                    callback=callback,
                    **method
                )
                
                # Если поток создался, проверяем запись
                with stream:
                    print(f"Поток успешно создан с параметрами {method}")
                    print("Запись звука с устройства вывода... (3 секунды)")
                    print("Воспроизведите какой-нибудь звук для проверки.")
                    time.sleep(3)
                
                # Анализируем записанное аудио
                data = []
                while not q.empty():
                    data.append(q.get())
                
                if data:
                    audio_data = np.concatenate(data)
                    volume = np.abs(audio_data).mean()
                    
                    print(f"Средняя громкость: {volume:.6f}")
                    if volume > 0.0001:  # Очень низкий порог для обнаружения какого-либо звука
                        print(f"{highlight('УСПЕХ!')} Обнаружен звук с устройства вывода.")
                        successful_method = method
                        return True, method
                    else:
                        print("Поток создан, но аудио сигнал не обнаружен или слишком тихий.")
                else:
                    print("Не удалось получить аудио данные")
                
            except Exception as e:
                print(f"Ошибка при создании потока: {e}")
        
        except Exception as e:
            print(f"Общая ошибка при методе {i+1}: {e}")
    
    if successful_method:
        print(f"\n{highlight('Успешный метод loopback:')} {successful_method}")
        return True, successful_method
    else:
        print(f"\n{highlight('Ни один метод loopback не сработал.')}")
        print("Рекомендации:")
        print("1. Включите Stereo Mix в настройках звука Windows")
        print("2. Попробуйте запустить приложение с правами администратора")
        print("3. Проверьте настройки звуковой карты и драйверов")
        return False, None

def suggest_configuration():
    """Предлагает конфигурацию на основе анализа"""
    print_header("Рекомендуемая конфигурация")
    
    # Проверяем систему
    system = check_system_info()
    
    # Анализируем устройства
    devices_info = check_audio_devices()
    
    if not devices_info:
        print("Не удалось проанализировать устройства. Настройка невозможна.")
        return
    
    microphones = devices_info["microphones"]
    outputs = devices_info["outputs"]
    stereo_mix_found = devices_info["stereo_mix_found"]
    loopback_candidates = devices_info["loopback_candidates"]
    
    # Выбор микрофона для тестирования
    if microphones:
        print("\nДоступные микрофоны:")
        for i, (idx, name) in enumerate(microphones):
            print(f"{i}: {name} (индекс устройства: {idx})")
        
        if len(microphones) == 1:
            mic_choice = 0
        else:
            mic_choice = int(input("\nВыберите микрофон для тестирования (номер из списка): ") or "0")
        
        if 0 <= mic_choice < len(microphones):
            mic_idx = microphones[mic_choice][0]
            print(f"\nТестирование микрофона {microphones[mic_choice][1]} (индекс: {mic_idx})...")
            mic_success, mic_volume = test_audio_device(mic_idx, is_input=True)
        else:
            print("Неверный выбор микрофона")
            mic_success = False
    else:
        print("Не найдено доступных микрофонов")
        mic_success = False
    
    # Проверка возможности захвата системного звука
    if stereo_mix_found:
        # Если есть Stereo Mix, проверим его
        stereo_mix_idx = None
        for idx, name in loopback_candidates:
            if ("stereo mix" in name.lower() or 
                "стереомикшер" in name.lower() or 
                "what u hear" in name.lower()):
                stereo_mix_idx = idx
                break
        
        if stereo_mix_idx is not None:
            print(f"\nТестирование Stereo Mix (индекс: {stereo_mix_idx})...")
            print("Воспроизведите звук на компьютере для проверки захвата...")
            stereo_mix_success, stereo_mix_volume = test_audio_device(stereo_mix_idx, is_input=True)
        else:
            stereo_mix_success = False
    else:
        stereo_mix_success = False
    
    # Проверяем loopback, если Stereo Mix не работает
    loopback_success = False
    loopback_method = None
    loopback_device = None
    
    if not stereo_mix_success and outputs:
        print("\nПопытка использования режима loopback для захвата системного звука")
        print("Доступные устройства вывода:")
        for i, (idx, name) in enumerate(outputs):
            print(f"{i}: {name} (индекс устройства: {idx})")
        
        if len(outputs) == 1:
            output_choice = 0
        else:
            output_choice = int(input("\nВыберите устройство вывода для тестирования loopback (номер из списка): ") or "0")
        
        if 0 <= output_choice < len(outputs):
            output_idx = outputs[output_choice][0]
            loopback_success, loopback_method = test_loopback(output_idx)
            if loopback_success:
                loopback_device = output_idx
        else:
            print("Неверный выбор устройства вывода")
    
    # Генерируем рекомендации на основе анализа
    print_header("Итоговые рекомендации")
    
    recommended_settings = {
        "mic_device": None,
        "output_device": None,
        "capture_method": None
    }
    
    if mic_success:
        recommended_settings["mic_device"] = mic_idx
        print(f"1. Рекомендуемый микрофон: {highlight(microphones[mic_choice][1])} (индекс: {mic_idx})")
    else:
        print("1. Не удалось обнаружить работающий микрофон.")
    
    if stereo_mix_success:
        recommended_settings["capture_method"] = "stereo_mix"
        recommended_settings["output_device"] = stereo_mix_idx
        print(f"2. Для захвата системного звука рекомендуется использовать {highlight('Stereo Mix')} (индекс: {stereo_mix_idx})")
    elif loopback_success:
        recommended_settings["capture_method"] = "loopback"
        recommended_settings["output_device"] = loopback_device
        print(f"2. Для захвата системного звука рекомендуется использовать {highlight('режим loopback')} для устройства {outputs[output_choice][1]} (индекс: {loopback_device})")
        print(f"   Метод подключения: {loopback_method}")
    else:
        print("2. Не удалось настроить захват системного звука. Рекомендации:")
        print("   - Включите Stereo Mix в настройках звука Windows")
        print("   - Запустите программу с правами администратора")
        print("   - Установите виртуальное аудио устройство (например, VB-Cable)")
    
    return recommended_settings

def generate_config_file(config):
    """Генерирует конфигурационный файл для проекта"""
    print_header("Создание конфигурационного файла")
    
    if not config or not config.get("mic_device"):
        print("Недостаточно данных для создания конфигурации")
        return
    
    try:
        config_dir = "utils"
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        config_path = os.path.join(config_dir, "audio_config.py")
        
        with open(config_path, "w") as f:
            f.write("""# Автоматически сгенерированная конфигурация аудио устройств
# Создано скриптом audio_setup.py

# Настройки аудио устройств
AUDIO_DEVICES = {
""")
            f.write(f"    'microphone': {config['mic_device']},  # Индекс микрофона\n")
            
            if config.get("output_device"):
                f.write(f"    'output': {config['output_device']},  # Индекс устройства вывода или Stereo Mix\n")
            else:
                f.write("    'output': None,  # Не удалось определить устройство вывода\n")
            
            capture_method = config.get("capture_method", "microphone_only")
            f.write(f"    'capture_method': '{capture_method}',  # Метод захвата системного звука (stereo_mix, loopback, microphone_only)\n")
            
            f.write("}\n\n")
            
            # Дополнительные параметры метода
            if capture_method == "loopback" and config.get("loopback_method"):
                f.write("# Параметры для метода loopback\n")
                f.write("LOOPBACK_PARAMS = ")
                f.write(str(config.get("loopback_method", {})) + "\n")
            
            f.write("""
# Функция для получения актуальной конфигурации
def get_audio_config():
    \"\"\"Возвращает конфигурацию аудио устройств\"\"\"
    return AUDIO_DEVICES.copy()
""")
        
        print(f"Конфигурационный файл создан: {highlight(config_path)}")
        print("Вы можете импортировать этот файл в вашем проекте для использования настроек")
        
    except Exception as e:
        print(f"Ошибка при создании конфигурационного файла: {e}")

def show_stereo_mix_help():
    """Показывает информацию о том, как включить Stereo Mix"""
    print_header("Как включить Stereo Mix в Windows")
    
    print("Stereo Mix (Стереомикшер) - это виртуальное устройство записи, которое позволяет")
    print("записывать весь звук, воспроизводимый через звуковую карту компьютера.")
    print("\nИнструкция по включению Stereo Mix в Windows 10/11:")
    print("1. Щелкните правой кнопкой мыши на значке динамика в системном трее")
    print("2. Выберите 'Звуки' или 'Параметры звука'")
    print("3. Перейдите на вкладку 'Запись'")
    print("4. Щелкните правой кнопкой мыши на пустом месте в списке устройств")
    print("5. Выберите 'Показать отключенные устройства'")
    print("6. Если Stereo Mix появился в списке, щелкните правой кнопкой мыши на нем")
    print("7. Выберите 'Включить'")
    print("\nЕсли Stereo Mix не появляется даже после включения отключенных устройств:")
    print("- Возможно, ваша звуковая карта не поддерживает Stereo Mix")
    print("- Попробуйте обновить драйверы звуковой карты")
    print("- Рассмотрите возможность использования виртуальных аудио устройств, таких как VB-Cable")
    
    print("\nАльтернативы Stereo Mix:")
    print("1. VB-Cable (Virtual Audio Cable): https://vb-audio.com/Cable/")
    print("2. Voicemeeter: https://vb-audio.com/Voicemeeter/")
    
    input("\nНажмите Enter для продолжения...")

def main():
    """Основная функция утилиты"""
    print_header("Утилита настройки аудио устройств для AI Meetings")
    print("Эта утилита поможет настроить захват аудио с микрофона и системного звука.")
    
    while True:
        print("\nВыберите действие:")
        print("1. Проверить информацию о системе")
        print("2. Проанализировать доступные аудио устройства")
        print("3. Провести полную настройку и тестирование")
        print("4. Как включить Stereo Mix в Windows")
        print("0. Выход")
        
        choice = input("\nВаш выбор: ")
        
        if choice == "1":
            check_system_info()
        elif choice == "2":
            check_audio_devices()
        elif choice == "3":
            config = suggest_configuration()
            if config:
                generate = input("\nСоздать конфигурационный файл? (y/n): ").lower()
                if generate.startswith("y"):
                    generate_config_file(config)
        elif choice == "4":
            show_stereo_mix_help()
        elif choice == "0":
            print("Выход из программы...")
            break
        else:
            print("Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()