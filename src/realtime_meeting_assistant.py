import os
import threading
import time
import queue
import wave
from datetime import datetime

from src.audio_capture import AudioCapture
from src.realtime_processor import RealTimeAudioProcessor
from src.speech_recognition import SpeechRecognizer
from src.chatgpt_client import ChatGPTClient
from src.meeting_summarizer import MeetingSummarizer
from utils.config import AUDIO_SETTINGS, CHATGPT_SETTINGS, SPEECH_RECOGNITION

class RealtimeMeetingAssistant:
    """
    Класс для обработки аудио в реальном времени, распознавания речи,
    отправки в ChatGPT и генерации саммари встречи
    """
    def __init__(self, 
                 audio_capture=None, 
                 speech_recognizer=None, 
                 chatgpt_client=None,
                 meeting_summarizer=None,
                 temp_dir="data/temp"):
        """
        Инициализирует ассистента для встреч
        
        Args:
            audio_capture: Экземпляр класса AudioCapture
            speech_recognizer: Экземпляр класса SpeechRecognizer
            chatgpt_client: Экземпляр класса ChatGPTClient
            meeting_summarizer: Экземпляр класса MeetingSummarizer
            temp_dir: Директория для временных файлов
        """
        # Создаем компоненты, если они не переданы
        self.audio_capture = audio_capture or AudioCapture()
        self.speech_recognizer = speech_recognizer or SpeechRecognizer()
        self.chatgpt_client = chatgpt_client or ChatGPTClient()
        self.meeting_summarizer = meeting_summarizer or MeetingSummarizer(self.chatgpt_client)
        
        # Создаем процессор реального времени
        self.realtime_processor = RealTimeAudioProcessor()
        
        # Очереди для обмена данными между потоками
        self.audio_queue = queue.Queue()
        self.text_queue = queue.Queue()
        self.response_queue = queue.Queue()
        
        # Создаем директорию для временных файлов, если она не существует
        self.temp_dir = temp_dir
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)
        
        # Флаги состояния
        self.is_running = False
        self.threads = []
        
        # Для хранения текущего сеанса
        self.meeting_title = f"Встреча {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        self.meeting_start_time = None
        self.meeting_transcription = []
        
        # Колбэки для UI
        self.on_transcription = None
        self.on_response = None
        self.on_error = None
    
    def start(self, input_device_index=None, output_device_index=None):
        """
        Запускает ассистента для встреч
        
        Args:
            input_device_index: Индекс устройства ввода (микрофон)
            output_device_index: Индекс устройства вывода (наушники)
            
        Returns:
            bool: True, если запуск успешен, иначе False
        """
        if self.is_running:
            print("Ассистент уже запущен")
            return False
        
        try:
            # Запоминаем время начала
            self.meeting_start_time = datetime.now()
            
            # Очищаем историю ChatGPT
            self.chatgpt_client.clear_conversation()
            
            # Добавляем информацию о начале встречи
            self.chatgpt_client.add_message(
                f"Начата новая встреча: {self.meeting_title}. " +
                f"Время начала: {self.meeting_start_time.strftime('%d.%m.%Y %H:%M:%S')}. " +
                "Я буду отправлять тебе транскрипции речи с встречи. Твоя задача - давать полезные ответы на вопросы, " +
                "которые задают во время встречи. В конце мы сформируем саммари встречи.",
                role="system"
            )
            
            # Запускаем захват аудио
            print("Запуск захвата аудио с микрофона и системного звука...")
            
            # Пробуем запустить запись с наушников
            try:
                self.audio_capture.start_universal_recording(
                    input_device_index=input_device_index,
                    output_device_index=output_device_index
                )
            except Exception as e:
                print(f"Ошибка при запуске универсального захвата: {e}")
                print("Пробуем альтернативный метод...")
                try:
                    self.audio_capture.start_dual_recording(
                        input_device_index=input_device_index,
                        output_device_index=output_device_index
                    )
                except Exception as e2:
                    print(f"Ошибка при запуске двойного захвата: {e2}")
                    print("Пробуем стандартный метод...")
                    self.audio_capture.start_recording_with_both(
                        input_device_index=input_device_index,
                        output_device_index=output_device_index
                    )
            
            # Запускаем обработчик реального времени с тем же устройством
            self.realtime_processor.start_processing(
                device_index=input_device_index,
                on_segment_ready=self._on_audio_segment
            )
            
            # Запускаем потоки обработки
            self.is_running = True
            
            # Поток для обработки аудио -> текст
            audio_thread = threading.Thread(
                target=self._audio_to_text_thread,
                name="AudioToTextThread",
                daemon=True
            )
            self.threads.append(audio_thread)
            audio_thread.start()
            
            # Поток для обработки текст -> ответ
            text_thread = threading.Thread(
                target=self._text_to_response_thread,
                name="TextToResponseThread",
                daemon=True
            )
            self.threads.append(text_thread)
            text_thread.start()
            
            print("Ассистент запущен и готов к работе!")
            return True
            
        except Exception as e:
            print(f"Ошибка при запуске ассистента: {e}")
            self.stop()
            if self.on_error:
                self.on_error(f"Ошибка при запуске: {e}")
            return False
    
    def stop(self):
        """
        Останавливает ассистента для встреч
        """
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Останавливаем захват аудио
        try:
            self.audio_capture.stop_recording()
        except Exception as e:
            print(f"Ошибка при остановке захвата аудио: {e}")
        
        # Останавливаем процессор реального времени
        try:
            self.realtime_processor.stop_processing()
        except Exception as e:
            print(f"Ошибка при остановке процессора: {e}")
        
        # Ждем завершения потоков
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=2.0)
        
        self.threads = []
        print("Ассистент остановлен")
    
    def generate_meeting_summary(self, title=None):
        """
        Генерирует саммари встречи
        
        Args:
            title (str): Название встречи (опционально)
            
        Returns:
            dict: Словарь с саммари и метаданными
        """
        if title:
            self.meeting_title = title
            
        # Создаем саммари с помощью summarizer
        summary = self.meeting_summarizer.generate_summary(title=self.meeting_title)
        
        # Сохраняем в файл
        filename = self.meeting_summarizer.save_summary_to_file(summary)
        
        return summary, filename
    
    def save_session(self, filename=None):
        """
        Сохраняет текущую сессию встречи
        
        Args:
            filename (str): Имя файла (опционально)
            
        Returns:
            str: Имя файла, в который сохранена сессия
        """
        # Сохраняем историю разговора
        return self.chatgpt_client.save_conversation(filename)
    
    def _on_audio_segment(self, segment):
        """
        Обрабатывает аудио сегмент от процессора реального времени
        
        Args:
            segment: Аудио сегмент (список байтовых данных)
        """
        if not self.is_running:
            return
            
        # Добавляем сегмент в очередь для обработки
        self.audio_queue.put(segment)
        
        # Сохраняем сегмент во временный файл для отладки
        if AUDIO_SETTINGS.get('save_segments', False):
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.temp_dir, f"segment_{timestamp}.wav")
                
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(AUDIO_SETTINGS['channels'])
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(AUDIO_SETTINGS['rate'])
                    wf.writeframes(b''.join(segment))
                
                print(f"Сегмент сохранен в {filename}")
            except Exception as e:
                print(f"Ошибка при сохранении сегмента: {e}")
    
    def _audio_to_text_thread(self):
        """
        Поток для преобразования аудио в текст
        """
        print("Запущен поток преобразования аудио в текст")
        
        while self.is_running:
            try:
                # Получаем сегмент из очереди с таймаутом
                segment = self.audio_queue.get(timeout=0.5)
                
                # Распознаем текст
                print("Распознавание речи...")
                text = self.speech_recognizer.transcribe_audio_data(
                    segment,
                    sample_rate=AUDIO_SETTINGS['rate'],
                    language=SPEECH_RECOGNITION['default_language']
                )
                
                # Проверяем, что текст не пустой
                if text and text.strip():
                    print(f"Распознано: {text}")
                    
                    # Добавляем в транскрипцию встречи
                    transcript_entry = {
                        "text": text,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                    self.meeting_transcription.append(transcript_entry)
                    
                    # Добавляем в очередь для отправки в ChatGPT
                    self.text_queue.put(text)
                    
                    # Вызываем колбэк, если он установлен
                    if self.on_transcription:
                        self.on_transcription(text)
                else:
                    print("Пустой результат распознавания")
                
                # Помечаем задачу как выполненную
                self.audio_queue.task_done()
                
            except queue.Empty:
                # Очередь пуста, продолжаем ожидание
                pass
            except Exception as e:
                print(f"Ошибка при преобразовании аудио в текст: {e}")
                if self.on_error:
                    self.on_error(f"Ошибка распознавания: {e}")
    
    def _text_to_response_thread(self):
        """
        Поток для получения ответов от ChatGPT
        """
        print("Запущен поток получения ответов от ChatGPT")
        
        while self.is_running:
            try:
                # Получаем текст из очереди с таймаутом
                text = self.text_queue.get(timeout=0.5)
                
                # Отправляем в ChatGPT и получаем ответ
                print("Отправка в ChatGPT...")
                response = self.chatgpt_client.get_response(text)
                
                print(f"Ответ: {response}")
                
                # Добавляем в очередь ответов
                self.response_queue.put(response)
                
                # Вызываем колбэк, если он установлен
                if self.on_response:
                    self.on_response(response)
                
                # Помечаем задачу как выполненную
                self.text_queue.task_done()
                
            except queue.Empty:
                # Очередь пуста, продолжаем ожидание
                pass
            except Exception as e:
                print(f"Ошибка при получении ответа от ChatGPT: {e}")
                if self.on_error:
                    self.on_error(f"Ошибка ChatGPT: {e}")
    
    def set_meeting_title(self, title):
        """
        Устанавливает название встречи
        
        Args:
            title (str): Название встречи
        """
        self.meeting_title = title

# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    import sys
    
    # Добавляем корневую директорию в путь импорта
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Загружаем переменные окружения
    from dotenv import load_dotenv
    load_dotenv()
    
    # Проверяем API ключ
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ВНИМАНИЕ: Не найден API ключ OpenAI в переменных окружения.")
        print("Установите его через переменную OPENAI_API_KEY или создайте файл .env")
        api_key = input("Введите ваш API ключ OpenAI для теста: ")
    
    # Колбэки для тестирования
    def on_transcription(text):
        print(f"\n[ТРАНСКРИПЦИЯ]: {text}")
    
    def on_response(response):
        print(f"\n[ОТВЕТ CHATGPT]: {response}")
    
    def on_error(error):
        print(f"\n[ОШИБКА]: {error}")
    
    # Создаем компоненты
    audio_capture = AudioCapture()
    speech_recognizer = SpeechRecognizer(model_name="tiny")  # Используем маленькую модель для быстроты
    chatgpt_client = ChatGPTClient(api_key=api_key)
    
    # Создаем ассистента
    assistant = RealtimeMeetingAssistant(
        audio_capture=audio_capture,
        speech_recognizer=speech_recognizer,
        chatgpt_client=chatgpt_client
    )
    
    # Устанавливаем колбэки
    assistant.on_transcription = on_transcription
    assistant.on_response = on_response
    assistant.on_error = on_error
    
    # Выводим список устройств
    print("Доступные устройства ввода:")
    input_devices = audio_capture.list_input_devices()
    
    print("\nДоступные устройства вывода:")
    output_devices = audio_capture.list_output_devices()
    
    # Выбираем устройства
    input_choice = int(input("\nВыберите устройство ввода (микрофон): "))
    if 0 <= input_choice < len(input_devices):
        input_device_id, input_device_name, input_device_type = input_devices[input_choice]
        print(f"Выбрано устройство ввода: {input_device_name} [{input_device_type}]")
    else:
        print("Неверный номер устройства ввода.")
        sys.exit(1)
    
    output_choice = int(input("\nВыберите устройство вывода (наушники): "))
    if 0 <= output_choice < len(output_devices):
        output_device_id, output_device_name, output_device_type = output_devices[output_choice]
        print(f"Выбрано устройство вывода: {output_device_name} [{output_device_type}]")
    else:
        print("Неверный номер устройства вывода.")
        sys.exit(1)
    
    # Устанавливаем название встречи
    meeting_title = input("\nВведите название встречи (или нажмите Enter для стандартного названия): ")
    if meeting_title:
        assistant.set_meeting_title(meeting_title)
    
    # Запускаем ассистента
    print("\nЗапуск ассистента...")
    if assistant.start(input_device_index=input_device_id, output_device_index=output_device_id):
        print("\nАссистент запущен! Говорите в микрофон или воспроизводите аудио через наушники.")
        print("Нажмите Ctrl+C для остановки.")
        
        try:
            # Основной цикл
            while True:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
        
        finally:
            # Останавливаем ассистента
            assistant.stop()
            
            # Генерируем саммари
            print("\nГенерация саммари встречи...")
            summary, filename = assistant.generate_meeting_summary()
            
            print(f"\nСаммари встречи сохранено в {filename}")
            print("\nСодержимое саммари:")
            print(summary['summary'])
            
            # Сохраняем сессию
            session_file = assistant.save_session()
            print(f"\nСессия сохранена в {session_file}")
    else:
        print("Не удалось запустить ассистента.")