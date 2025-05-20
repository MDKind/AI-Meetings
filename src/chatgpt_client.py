import os
import time
import json
from datetime import datetime
from openai import OpenAI
from utils.config import CHATGPT_SETTINGS

class ChatGPTClient:
    """
    Класс для взаимодействия с API ChatGPT
    """
    def __init__(self, api_key=None, model=CHATGPT_SETTINGS['default_model'], 
                 max_tokens=CHATGPT_SETTINGS['max_tokens']):
        """
        Инициализирует клиент ChatGPT
        
        Args:
            api_key (str, optional): API ключ OpenAI. Если None, берется из конфигурации или переменных окружения.
            model (str): Модель для использования
            max_tokens (int): Максимальное количество токенов в ответе
        """
        # Получаем API ключ из конфигурации или переменной окружения, если не передан
        if api_key is None:
            api_key = CHATGPT_SETTINGS.get('api_key') or os.getenv("OPENAI_API_KEY")
            if api_key is None:
                raise ValueError(
                    "Необходимо указать API ключ OpenAI через параметр api_key, "
                    "переменную окружения OPENAI_API_KEY или в файле конфигурации."
                )
        
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.conversation_history = []
        
        # Системный промпт из конфигурации
        self.system_prompt = CHATGPT_SETTINGS['system_prompt']
    
    def add_message(self, content, role="user"):
        """
        Добавляет сообщение в историю разговора
        
        Args:
            content (str): Содержимое сообщения
            role (str): Роль отправителя ("user", "assistant", "system")
        """
        self.conversation_history.append({"role": role, "content": content})
    
    def get_response(self, prompt=None):
        """
        Получает ответ от ChatGPT на основе истории разговора
        
        Args:
            prompt (str, optional): Новый запрос для добавления в историю
            
        Returns:
            str: Ответ от ChatGPT
        """
        if prompt:
            self.add_message(prompt)
        
        try:
            # Подготавливаем сообщения для API
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.conversation_history)
            
            # Выполняем запрос к API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.7
            )
            
            # Получаем ответ
            response_text = response.choices[0].message.content
            
            # Добавляем ответ в историю
            self.add_message(response_text, role="assistant")
            
            return response_text
            
        except Exception as e:
            print(f"Ошибка при получении ответа от ChatGPT: {e}")
            return f"Ошибка: {str(e)}"
    
    def generate_meeting_summary(self):
        """
        Генерирует саммари встречи на основе истории разговора
        
        Returns:
            str: Саммари встречи
        """
        summary_prompt = """
        Пожалуйста, создайте краткое саммари этой встречи, включающее:
        1. Основные обсуждаемые темы
        2. Ключевые решения и выводы
        3. Вопросы, которые остались открытыми
        4. Следующие шаги и назначенные задачи
        
        Формат: структурированное резюме в виде маркированных списков.
        """
        
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": summary_prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=2000,
                temperature=0.3
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Ошибка при генерации саммари: {e}")
            return f"Ошибка при создании саммари: {str(e)}"
    
    def save_conversation(self, filename=None):
        """
        Сохраняет историю разговора в файл
        
        Args:
            filename (str, optional): Имя файла для сохранения.
                                     Если None, генерируется на основе текущей даты и времени.
        
        Returns:
            str: Имя файла, в который была сохранена история
        """
        if filename is None:
            # Создаем имя файла на основе текущей даты и времени
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        print(f"История разговора сохранена в {filename}")
        
        return filename
    
    def load_conversation(self, filename):
        """
        Загружает историю разговора из файла
        
        Args:
            filename (str): Имя файла для загрузки
            
        Returns:
            bool: True, если загрузка выполнена успешно, иначе False
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.conversation_history = json.load(f)
            print(f"История разговора загружена из {filename}")
            return True
        except FileNotFoundError:
            print(f"Файл {filename} не найден.")
            return False
        except json.JSONDecodeError:
            print(f"Ошибка при декодировании JSON из файла {filename}.")
            return False
    
    def clear_conversation(self):
        """
        Очищает историю разговора
        """
        self.conversation_history = []
        print("История разговора очищена.")


# Тестовый код (выполняется только при запуске файла напрямую)
if __name__ == "__main__":
    # Проверяем наличие API ключа в переменных окружения
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ВНИМАНИЕ: Не найден API ключ OpenAI в переменных окружения.")
        print("Установите его через переменную OPENAI_API_KEY или создайте файл .env")
        api_key = input("Введите ваш API ключ OpenAI для теста: ")
    
    # Создаем клиент ChatGPT
    try:
        chatgpt = ChatGPTClient(api_key=api_key)
        
        # Тестовый запрос
        test_prompt = "Привет! Как эффективно организовать командную работу над проектом?"
        print(f"Тестовый запрос: {test_prompt}")
        
        response = chatgpt.get_response(test_prompt)
        print("\nОтвет ChatGPT:")
        print(response)
        
        # Добавляем еще несколько сообщений для теста
        chatgpt.add_message("На встрече мы обсудили распределение задач в новом проекте.")
        chatgpt.add_message("Петр будет отвечать за фронтенд, а Мария за бэкенд.")
        chatgpt.add_message("Дедлайн проекта - 15 июня.")
        
        # Генерируем тестовое саммари
        print("\nГенерация саммари встречи...")
        summary = chatgpt.generate_meeting_summary()
        print("\nСаммари встречи:")
        print(summary)
        
        # Сохраняем историю в файл
        filename = chatgpt.save_conversation()
        
        # Очищаем историю и загружаем ее снова для проверки
        chatgpt.clear_conversation()
        print("\nИстория очищена. Загружаем из файла...")
        chatgpt.load_conversation(filename)
        
        print("\nТест завершен успешно!")
        
    except Exception as e:
        print(f"Ошибка при тестировании: {e}")