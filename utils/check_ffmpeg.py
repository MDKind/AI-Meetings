"""
Утилита для проверки наличия и поиска ffmpeg в системе
"""
import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

def check_ffmpeg():
    """
    Проверяет наличие ffmpeg в системе и в директории проекта
    
    Returns:
        tuple: (bool, str) - найден ffmpeg, путь к ffmpeg или None
    """
    print("Проверка наличия ffmpeg...")
    
    # Проверяем в системе через shutil.which
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"ffmpeg найден в системе: {ffmpeg_path}")
        return True, ffmpeg_path
    
    # Проверяем в директории проекта
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_ffmpeg = os.path.join(project_dir, "ffmpeg.exe")
    
    if os.path.exists(project_ffmpeg):
        print(f"ffmpeg найден в директории проекта: {project_ffmpeg}")
        return True, project_ffmpeg
    
    print("ffmpeg не найден ни в PATH, ни в директории проекта")
    return False, None

def list_ffmpeg_devices():
    """
    Выводит список устройств, доступных для ffmpeg
    
    Returns:
        bool: Удалось ли получить список устройств
    """
    ffmpeg_found, ffmpeg_path = check_ffmpeg()
    
    if not ffmpeg_found:
        print("ffmpeg не найден, невозможно получить список устройств")
        return False
    
    system = platform.system()
    
    if system == "Windows":
        try:
            print("Получение списка устройств DirectShow...")
            
            # Команда для вывода списка устройств
            cmd = [ffmpeg_path, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
            
            # Запускаем команду и перехватываем stderr, где выводится список устройств
            process = subprocess.Popen(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
            )
            
            _, stderr = process.communicate()
            
            print("\n=== Доступные DirectShow устройства ===")
            print(stderr)
            
            # Анализируем вывод для более структурированного отображения
            audio_devices = []
            video_devices = []
            audio_mode = False
            video_mode = False
            
            for line in stderr.split("\n"):
                if "DirectShow audio devices" in line:
                    audio_mode = True
                    video_mode = False
                    continue
                
                if "DirectShow video devices" in line:
                    audio_mode = False
                    video_mode = True
                    continue
                
                if "Alternative name" in line:
                    if "'" in line:
                        device_name = line.split("'")[1]
                        if audio_mode:
                            audio_devices.append(device_name)
                        elif video_mode:
                            video_devices.append(device_name)
            
            print("\n=== Аудио устройства ===")
            for i, device in enumerate(audio_devices):
                print(f"{i}: {device}")
            
            print("\n=== Видео устройства ===")
            for i, device in enumerate(video_devices):
                print(f"{i}: {device}")
            
            return True
        
        except Exception as e:
            print(f"Ошибка при получении списка устройств: {e}")
            return False
    
    elif system == "Darwin":  # macOS
        print("Получение списка устройств AVFoundation...")
        cmd = [ffmpeg_path, "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        
        # Аналогично для macOS
        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        
        _, stderr = process.communicate()
        
        print("\n=== Доступные AVFoundation устройства ===")
        print(stderr)
        return True
    
    elif system == "Linux":
        print("Получение списка устройств для Linux...")
        cmd = [ffmpeg_path, "-sources", "pulse"]
        
        # Для Linux
        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        
        stdout, stderr = process.communicate()
        
        print("\n=== Доступные PulseAudio устройства ===")
        print(stdout)
        print(stderr)
        return True
    
    else:
        print(f"Неизвестная операционная система: {system}")
        return False

def download_ffmpeg():
    """
    Загружает и устанавливает ffmpeg в директорию проекта
    
    Returns:
        bool: Удалось ли загрузить ffmpeg
    """
    # Проверяем, может быть ffmpeg уже установлен
    ffmpeg_found, _ = check_ffmpeg()
    if ffmpeg_found:
        choice = input("ffmpeg уже найден. Загрузить заново? (y/n): ").lower()
        if choice != 'y':
            return True
    
    system = platform.system()
    arch = "64" if platform.architecture()[0] == "64bit" else "32"
    
    print(f"Обнаружена операционная система: {system} {arch}-bit")
    
    try:
        import tempfile
        import urllib.request
        import zipfile
        
        # Создаем временную директорию
        with tempfile.TemporaryDirectory() as temp_dir:
            # URL для загрузки
            if system == "Windows":
                if arch == "64":
                    url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
                else:
                    url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip"
                
                print(f"Загрузка ffmpeg с {url}...")
                
                # Загружаем архив
                zip_path = os.path.join(temp_dir, "ffmpeg.zip")
                urllib.request.urlretrieve(url, zip_path)
                
                print("Распаковка архива...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Находим распакованную директорию
                ffmpeg_dir = None
                for item in os.listdir(temp_dir):
                    if os.path.isdir(os.path.join(temp_dir, item)) and "ffmpeg" in item.lower():
                        ffmpeg_dir = os.path.join(temp_dir, item)
                        break
                
                if not ffmpeg_dir:
                    print("Не удалось найти распакованную директорию ffmpeg")
                    return False
                
                print(f"Найдена директория ffmpeg: {ffmpeg_dir}")
                
                # Копируем ffmpeg.exe и ffprobe.exe в директорию проекта
                project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                
                for exe_file in ["ffmpeg.exe", "ffprobe.exe"]:
                    src_path = os.path.join(ffmpeg_dir, "bin", exe_file)
                    dst_path = os.path.join(project_dir, exe_file)
                    
                    if os.path.exists(src_path):
                        shutil.copy2(src_path, dst_path)
                        print(f"Скопирован {exe_file} в {dst_path}")
                
                print("ffmpeg успешно установлен!")
                return True
            
            else:
                print("Автоматическая загрузка ffmpeg поддерживается только для Windows.")
                print("Для других операционных систем установите ffmpeg с официального сайта:")
                print("https://ffmpeg.org/download.html")
                return False
    
    except Exception as e:
        print(f"Ошибка при загрузке ffmpeg: {e}")
        return False

def main():
    """
    Основная функция утилиты
    """
    print("=== Утилита для проверки и установки ffmpeg ===")
    
    while True:
        print("\nВыберите действие:")
        print("1. Проверить наличие ffmpeg")
        print("2. Вывести список устройств ffmpeg")
        print("3. Загрузить и установить ffmpeg")
        print("0. Выход")
        
        choice = input("\nВаш выбор: ")
        
        if choice == "1":
            check_ffmpeg()
        elif choice == "2":
            list_ffmpeg_devices()
        elif choice == "3":
            download_ffmpeg()
        elif choice == "0":
            print("Выход из программы...")
            break
        else:
            print("Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()