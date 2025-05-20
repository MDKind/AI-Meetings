import os
import json
from datetime import datetime
from utils.config import CHATGPT_SETTINGS

class MeetingSummarizer:
    """
    Класс для генерации саммари встречи и статистики
    """
    def __init__(self, chatgpt_client):
        """
        Инициализирует сумматор встреч
        
        Args:
            chatgpt_client: Экземпляр класса ChatGPTClient
        """
        self.chatgpt_client = chatgpt_client
        
    def generate_summary(self, title=None):
        """
        Генерирует структурированное саммари встречи
        
        Args:
            title (str): Название встречи (опционально)
            
        Returns:
            dict: Словарь с саммари и метаданными
        """
        # Формируем запрос для генерации саммари
        summary_prompt = """
        Пожалуйста, создайте структурированное саммари этой встречи, включающее:
        
        1. Основные темы обсуждения (до 5 ключевых тем)
        2. Ключевые решения и договоренности
        3. Назначенные задачи и ответственные лица
        4. Открытые вопросы, требующие дальнейшего обсуждения
        5. Следующие шаги
        
        Представьте результат в структурированном виде, избегая длинных абзацев.
        Для каждого пункта используйте маркированные списки.
        """
        
        try:
            # Получаем саммари от ChatGPT
            raw_summary = self.chatgpt_client.get_response(summary_prompt)
            
            # Получаем дополнительную статистику
            stats_prompt = """
            На основе предыдущего разговора, пожалуйста, предоставьте:
            1. Список участников встречи (кто говорил)
            2. Примерную длительность обсуждения каждой темы (в процентах)
            3. Эмоциональный тон обсуждения (позитивный/нейтральный/негативный)
            """
            
            statistics = self.chatgpt_client.get_response(stats_prompt)
            
            # Создаем полное саммари со всеми метаданными
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            summary = {
                "title": title or f"Встреча {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                "date": timestamp,
                "duration": self._estimate_meeting_duration(),
                "summary": raw_summary,
                "statistics": statistics,
                "raw_conversation": self._get_conversation_data()
            }
            
            return summary
            
        except Exception as e:
            print(f"Ошибка при генерации саммари: {e}")
            return {
                "title": title or f"Встреча {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e)
            }
    
    def save_summary_to_file(self, summary, filename=None):
        """
        Сохраняет саммари в файл
        
        Args:
            summary (dict): Словарь с саммари
            filename (str): Имя файла (если None, генерируется автоматически)
            
        Returns:
            str: Путь к сохраненному файлу
        """
        if filename is None:
            # Создаем имя файла на основе даты и названия встречи
            safe_title = summary["title"].replace(" ", "_").replace("/", "-")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"summary_{safe_title}_{timestamp}.json"
        
        # Сохраняем полное саммари
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # Создаем текстовую версию для удобства чтения
        txt_filename = os.path.splitext(filename)[0] + ".txt"
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(f"# {summary['title']}\n")
            f.write(f"Дата: {summary['date']}\n")
            f.write(f"Длительность: {summary.get('duration', 'N/A')}\n\n")
            f.write("## Саммари встречи\n\n")
            f.write(summary['summary'])
            f.write("\n\n## Статистика\n\n")
            f.write(summary.get('statistics', 'Статистика недоступна'))
        
        return filename
    
    def _estimate_meeting_duration(self):
        """
        Оценивает длительность встречи на основе истории разговора
        
        Returns:
            str: Оценка длительности
        """
        if not self.chatgpt_client.conversation_history:
            return "N/A"
        
        # В реальном сценарии здесь можно реализовать точный расчет
        # на основе временных меток сообщений
        return f"~{len(self.chatgpt_client.conversation_history) // 2} минут"
    
    def _get_conversation_data(self):
        """
        Получает данные разговора в структурированном виде
        
        Returns:
            list: Список сообщений с метаданными
        """
        conversation = []
        
        for message in self.chatgpt_client.conversation_history:
            # В истории ChatGPT храним только роль и содержимое
            # Здесь можно добавить дополнительные метаданные
            conversation.append({
                "role": message["role"],
                "content": message["content"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Это заглушка, реальные временные метки нужно сохранять отдельно
            })
        
        return conversation