"""
Simplified audio synchronization module without scipy dependency
"""

import numpy as np
import threading
import time
from collections import deque
from queue import Queue, Empty

class AudioSynchronizer:
    """
    Синхронизирует несколько аудио потоков (микрофон и системный звук)
    """
    def __init__(self, sample_rate=16000, channels=1, sync_window_ms=50):
        """
        Инициализирует синхронизатор аудио
        
        Args:
            sample_rate: Частота дискретизации
            channels: Количество каналов
            sync_window_ms: Окно синхронизации в миллисекундах
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.sync_window_samples = int(sample_rate * sync_window_ms / 1000)
        
        # Буферы для каждого потока
        self.mic_buffer = deque(maxlen=sample_rate * 5)  # 5 секунд буфер
        self.system_buffer = deque(maxlen=sample_rate * 5)  # 5 секунд буфер
        
        # Временные метки
        self.mic_timestamp = 0
        self.system_timestamp = 0
        
        # Очередь для синхронизированного аудио
        self.output_queue = Queue()
        
        # Флаги управления
        self.is_running = False
        self.sync_thread = None
        
        # Параметры обнаружения задержки
        self.delay_samples = 0  # Задержка между потоками
        self.correlation_threshold = 0.3
        
        # Блокировки для потокобезопасности
        self.mic_lock = threading.Lock()
        self.system_lock = threading.Lock()
        
    def start(self):
        """Запускает синхронизацию"""
        if self.is_running:
            return
            
        self.is_running = True
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        
    def stop(self):
        """Останавливает синхронизацию"""
        self.is_running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=1.0)
            
    def add_mic_data(self, audio_data):
        """
        Добавляет данные с микрофона
        
        Args:
            audio_data: numpy array с аудио данными
        """
        with self.mic_lock:
            # Если данные многоканальные, конвертируем в моно
            if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
                audio_data = np.mean(audio_data, axis=1)
                
            # Добавляем в буфер
            self.mic_buffer.extend(audio_data.flatten())
            self.mic_timestamp = time.time()
            
    def get_synchronized_audio(self, timeout=0.1):
        """
        Получает синхронизированное аудио
        
        Args:
            timeout: Таймаут ожидания в секундах
            
        Returns:
            numpy array с синхронизированным аудио или None
        """
        try:
            return self.output_queue.get(timeout=timeout)
        except Empty:
            return None
            
    def _sync_loop(self):
        """Основной цикл синхронизации"""
        while self.is_running:
            # Проверяем наличие достаточного количества данных
            with self.mic_lock:
                mic_len = len(self.mic_buffer)
            with self.system_lock:
                system_len = len(self.system_buffer)
                
            # Минимальная длина для обработки (1 секунда)
            min_length = self.sample_rate
            
            if mic_len >= min_length and system_len >= min_length:
                # Обнаруживаем задержку между потоками
                self._detect_delay()
                
                # Синхронизируем и смешиваем потоки
                mixed_audio = self._mix_streams()
                
                if mixed_audio is not None and len(mixed_audio) > 0:
                    self.output_queue.put(mixed_audio)
                    
            time.sleep(0.05)  # 50ms цикл
            
    def _detect_delay(self):
        """
        Обнаруживает задержку между микрофоном и системным звуком
        используя кросс-корреляцию
        """
        with self.mic_lock:
            mic_data = np.array(list(self.mic_buffer))
        with self.system_lock:
            system_data = np.array(list(self.system_buffer))
            
        # Берем последние 2 секунды для анализа
        analysis_length = min(self.sample_rate * 2, len(mic_data), len(system_data))
        
        if analysis_length < self.sample_rate:
            return
            
        mic_segment = mic_data[-analysis_length:]
        system_segment = system_data[-analysis_length:]
        
        # Нормализуем сигналы
        mic_segment = mic_segment / (np.max(np.abs(mic_segment)) + 1e-6)
        system_segment = system_segment / (np.max(np.abs(system_segment)) + 1e-6)
        
        # Вычисляем кросс-корреляцию
        correlation = np.correlate(mic_segment, system_segment, mode='full')
        
        # Находим пик корреляции
        peak_idx = np.argmax(np.abs(correlation))
        peak_value = np.abs(correlation[peak_idx])
        
        # Если корреляция достаточно высокая, обновляем задержку
        if peak_value > self.correlation_threshold:
            # Преобразуем индекс в задержку в сэмплах
            delay = peak_idx - (len(system_segment) - 1)
            
            # Применяем сглаживание для стабильности
            self.delay_samples = int(0.9 * self.delay_samples + 0.1 * delay)
            
    def _mix_streams(self):
        """
        Смешивает синхронизированные потоки
        
        Returns:
            numpy array со смешанным аудио
        """
        # Определяем размер чанка для обработки
        chunk_size = self.sync_window_samples * 10  # 500ms чанки
        
        with self.mic_lock:
            if len(self.mic_buffer) < chunk_size:
                return None
            # Извлекаем данные из буфера микрофона
            mic_data = np.array([self.mic_buffer.popleft() for _ in range(chunk_size)])
            
        with self.system_lock:
            if len(self.system_buffer) < chunk_size + abs(self.delay_samples):
                return None
                
            # Применяем компенсацию задержки
            if self.delay_samples > 0:
                # Системный звук опережает микрофон
                start_idx = self.delay_samples
            else:
                # Микрофон опережает системный звук
                start_idx = 0
                
            # Извлекаем данные из буфера системного звука
            system_data = np.array([self.system_buffer.popleft() 
                                   for _ in range(chunk_size)])
            
        # Нормализуем уровни
        mic_rms = np.sqrt(np.mean(mic_data**2))
        system_rms = np.sqrt(np.mean(system_data**2))
        
        # Адаптивное микширование на основе уровней
        if mic_rms > 0.01:  # Есть звук с микрофона
            if system_rms > 0.01:  # Есть системный звук
                # Смешиваем с адаптивными весами
                mic_weight = 0.7
                system_weight = 0.3
            else:
                # Только микрофон
                mic_weight = 1.0
                system_weight = 0.0
        else:
            if system_rms > 0.01:  # Только системный звук
                mic_weight = 0.0
                system_weight = 1.0
            else:
                # Тишина
                mic_weight = 0.5
                system_weight = 0.5
                
        # Смешиваем потоки
        mixed = mic_weight * mic_data + system_weight * system_data
        
        # Предотвращаем клиппинг
        max_val = np.max(np.abs(mixed))
        if max_val > 0.95:
            mixed = mixed * 0.95 / max_val
            
        return mixed
        
    def reset_buffers(self):
        """Сбрасывает буферы"""
        with self.mic_lock:
            self.mic_buffer.clear()
        with self.system_lock:
            self.system_buffer.clear()
        self.delay_samples = 0


class EnhancedAudioProcessor:
    """
    Простой процессор аудио без зависимости от scipy
    """
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        
    def process(self, audio_data):
        """
        Обрабатывает аудио данные (простая нормализация)
        
        Args:
            audio_data: numpy array с аудио
            
        Returns:
            Обработанное аудио
        """
        # Простая нормализация
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            return audio_data * 0.9 / max_val
        return audio_data
