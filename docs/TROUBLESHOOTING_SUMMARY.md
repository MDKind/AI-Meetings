# Решение проблем с запуском AI Meetings

## Проблемы и решения

### 1. Ошибка "No module named 'comtypes'"
```bash
# Установите comtypes
pip install comtypes
```

### 2. Ошибка "Digital filter critical frequencies"
Эта ошибка связана с scipy. Мы заменили audio_synchronizer.py на упрощенную версию без фильтров.

### 3. Ошибка "stdout and stderr arguments may not be used with capture_output"
Эта ошибка была в файле speech_recognition.py. Мы исправили ее, удалив параметр capture_output=True.

**Проверьте исправление:**
```bash
python test_subprocess_fix.py
```

**Проверьте проблему:**
```bash
python diagnose_scipy.py
```

**Если нужно восстановить оригинальную версию с фильтрами:**
```bash
# Сделайте резервную копию текущей версии
copy src\audio_synchronizer.py src\audio_synchronizer_simple_backup.py

# Восстановите полную версию
copy src\audio_synchronizer_full.py src\audio_synchronizer.py
```

### 3. Общие проблемы с запуском

**Шаг 1: Установите минимальные зависимости**
```bash
minimal_install.bat
```

**Шаг 2: Проверьте установку**
```bash
python check_dependencies.py
python test_startup.py
```

**Шаг 3: Запустите приложение**
```bash
python main.py
```

## Что было сделано для решения проблем

1. **Упрощен windows_audio_capture.py** - работает без comtypes
2. **Упрощен audio_synchronizer.py** - работает без scipy фильтров
3. **Созданы скрипты установки** - minimal_install.bat для быстрого старта
4. **Добавлены диагностические скрипты** - для проверки проблем

## Структура файлов

```
src/
├── audio_synchronizer.py          # Упрощенная версия (текущая)
├── audio_synchronizer_full.py     # Полная версия с фильтрами
├── windows_audio_capture.py       # Упрощенная версия (текущая)
└── windows_audio_capture_full.py  # Полная версия с WASAPI
```

## Если ничего не помогает

1. Создайте новое виртуальное окружение:
```bash
python -m venv venv_new
venv_new\Scripts\activate
pip install numpy sounddevice openai python-dotenv
python main.py
```

2. Используйте минимальную конфигурацию без распознавания речи и продвинутых функций.

3. Проверьте версию Python (должна быть 3.8+):
```bash
python --version
```
