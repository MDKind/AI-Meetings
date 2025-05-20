# Инструкция по установке проекта AI MEETINGS

## Подготовка среды

1. **Обновите pip и инструменты для сборки**:
   ```powershell
   python -m pip install --upgrade pip
   pip install --upgrade setuptools wheel
   ```

2. **Установите зависимости из requirements.txt**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Отдельно установите аудио-библиотеку** (выберите один из вариантов):

   **Вариант A: PyAudio (рекомендуется)**
   ```powershell
   pip install pipwin
   pipwin install pyaudio
   ```
   
   **Вариант B: Sounddevice (альтернатива если PyAudio не устанавливается)**
   ```powershell
   pip install sounddevice
   ```
   
   Если вы выбрали Sounddevice, необходимо заменить файл `src/audio_capture.py` на альтернативную версию.

4. **Создайте файл .env** в корневой директории проекта:
   ```
   OPENAI_API_KEY=ваш_api_ключ_openai
   ```

## Проверка установки

Проверьте, что все необходимые зависимости установлены:

```powershell
pip list
```

В списке должны присутствовать:
- numpy
- openai
- pydub
- torch
- openai-whisper
- python-dotenv
- И либо pyaudio, либо sounddevice

## Запуск приложения

```powershell
python main.py
```

## Устранение возможных проблем

### Проблема: Ошибка "BackendUnavailable: Cannot import 'setuptools.build_meta'"

**Решение**:
```powershell
pip uninstall setuptools
pip install setuptools==59.8.0
```

### Проблема: Ошибка с PyAudio

**Решение 1**: Используйте pipwin
```powershell
pip install pipwin
pipwin install pyaudio
```

**Решение 2**: Установите предкомпилированный wheel-файл
1. Скачайте соответствующий wheel-файл для вашей версии Python с https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
2. Установите скачанный файл: `pip install путь_к_файлу.whl`

**Решение 3**: Используйте sounddevice вместо PyAudio
```powershell
pip install sounddevice
```

### Проблема: Ошибки при установке torch или whisper

**Решение**: Установите их по отдельности
```powershell
pip install torch
pip install openai-whisper
```

### Проблема: Недостаточно памяти для модели Whisper

**Решение**: Используйте модель меньшего размера ('tiny' или 'base') в настройках приложения.

## Уточнения для различных ОС

### Windows
- Требуется Microsoft Visual C++ Build Tools для некоторых пакетов.
- Возможно, потребуется запуск PowerShell/CMD от имени администратора.

### Linux
- Возможно, потребуются дополнительные библиотеки для аудио:
  ```bash
  sudo apt-get install portaudio19-dev python3-pyaudio
  ```

### macOS
- Возможно, потребуются дополнительные библиотеки для аудио:
  ```bash
  brew install portaudio
  ```