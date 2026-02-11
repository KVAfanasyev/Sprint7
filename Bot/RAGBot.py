import numpy as np

if not hasattr(np, 'float_'):
    np.float_ = np.float64
    np.int_ = np.int64
    np.uint = np.uint64

# Теперь импортируем остальные библиотеки
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
import traceback
import re
import requests
import json
from typing import List, Dict, Optional
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = '8317799983:AAHEBTNTj7QD7lj5Oc9QQZBIkdp8zBCHlYs'

# Конфигурация LLM (используем локальную модель через Ollama)
LLM_CONFIG = {
    'type': 'ollama',  # 'ollama' или 'yandexgpt'
    'ollama_url': 'http://localhost:11434/api/generate',
    'model': 'gemma3:1b',  # или 'mistral', 'llama2', 'gemma:2b' и т.д.
    'temperature': 0.3,
    'max_tokens': 1000,
    'timeout': 30
}

# Примеры Few-shot для улучшения качества ответов
FEW_SHOT_EXAMPLES = [
    {
        "query": "Кто такой Джек Томпсон?",
        "context": "Джек Томпсон - главный герой оригинальной трилогии Червячных Спариваний. Он сын Энакина Томпсона и Падме Амидалы, воспитанный на Татуине.",
        "response": "Джек Томпсон - центральный персонаж оригинальной трилогии «Червьных Спариваний». Он сын Энакина Томпсона (впоследствии Виктора Дарквуда) и Падме Амидалы. После рождения был скрыт на планете Татуин, где его воспитывали дядя Оуэн и тётя Беру. Джек обучался пути Стража под руководством Бенджамина Стоуна и Йорина, в итоге став Стражем и сыграв ключевую роль в поражении Имперского Союза."
    },
    {
        "query": "Что такое Энергия в Червячных Спариваниях?",
        "context": "Энергия - это энергетическое поле, создаваемое всеми живыми существами. Она окружает и проникает во все живое. Энергия имеет светлую и темную стороны.",
        "response": "Энергия в мире «Червьных Спариваний» - это метафизическая энергия, создаваемая всеми живыми существами. Она пронизывает всю галактику и связывает все живое. Энергия имеет две основные стороны: светлую (используемую Стражами для защиты и помощи) и темную (используемую Рыцарями Тени для агрессии и контроля). Пользователи Энергии могут развивать различные способности: телекинез, предвидение, чтение мыслей, манипуляцию сознанием и ускоренное исцеление."
    }
]

# Инициализация ChromaDB
class ChromaSearch:
    def __init__(self, collection_name: str = "knowledge_base"):
        try:
            self.client = chromadb.PersistentClient(path="./chroma_db")

            # Используем встроенную функцию эмбеддингов
            self.embedding_function = SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )

            # Пробуем получить существующую коллекцию БЕЗ указания embedding_function
            try:
                self.collection = self.client.get_collection(
                    name=collection_name
                    # Не передаем embedding_function при получении существующей коллекции
                )
                logger.info(f"Коллекция '{collection_name}' успешно загружена")

            except Exception as e:
                logger.warning(f"Коллекция '{collection_name}' не найдена. Создаем новую. Ошибка: {e}")
                self.collection = self.client.create_collection(
                    name=collection_name,
                    embedding_function=self.embedding_function
                )

        except Exception as e:
            logger.error(f"Ошибка инициализации ChromaDB: {e}")
            logger.error(traceback.format_exc())
            self.collection = None

    def search(self, query: str, n_results: int = 5):
        """Поиск в векторном индексе"""
        if not self.collection:
            logger.error("Коллекция не инициализирована")
            return None

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )

            return results
        except Exception as e:
            logger.error(f"Ошибка при поиске: {e}")
            logger.error(traceback.format_exc())
            return None


# Инициализируем поиск
chroma_search = ChromaSearch()


class RAGPipeline:
    """Класс для реализации RAG пайплайна"""

    def __init__(self, llm_config: Dict = LLM_CONFIG):
        self.llm_config = llm_config
        self.available_models = self._check_available_models()

    def _check_available_models(self) -> List[str]:
        """Проверяет доступные локальные модели через Ollama"""
        try:
            if self.llm_config['type'] == 'ollama':
                response = requests.get('http://localhost:11434/api/tags', timeout=5)
                if response.status_code == 200:
                    models = [model['name'] for model in response.json().get('models', [])]
                    logger.info(f"Доступные модели Ollama: {models}")
                    return models
        except Exception as e:
            logger.warning(f"Не удалось подключиться к Ollama: {e}")
        return []

    def generate_prompt(self, query: str, contexts: List[str], use_few_shot: bool = True,
                       use_chain_of_thought: bool = True) -> str:
        """Генерирует промпт для LLM с использованием найденных контекстов"""

        # Объединяем контексты
        context_text = "\n\n".join([f"Контекст {i+1}: {ctx}" for i, ctx in enumerate(contexts)])

        # Few-shot примеры
        few_shot_text = ""
        if use_few_shot and FEW_SHOT_EXAMPLES:
            few_shot_text = "\n\nПримеры правильных ответов:\n"
            for example in FEW_SHOT_EXAMPLES:
                few_shot_text += f"\nВопрос: {example['query']}\n"
                few_shot_text += f"Контекст: {example['context']}\n"
                few_shot_text += f"Ответ: {example['response']}\n"
                few_shot_text += "-" * 50

        # Chain-of-Thought инструкции
        cot_instructions = ""
        if use_chain_of_thought:
            cot_instructions = """
Пожалуйста, следуй этой цепочке рассуждений:
1. Внимательно проанализируй вопрос пользователя
2. Изучи предоставленные контексты и найди релевантную информацию
3. Сформулируй полный, связный ответ на основе найденной информации
4. Если информация в контекстах противоречива, укажи на это
5. Если ответа нет в контекстах, честно скажи об этом

Теперь начни свой ответ с краткого рассуждения о том, как ты пришел к ответу:
"""

        prompt = f"""Ты - полезный ассистент с доступом к базе знаний о вселенной Червячных спариваний.
Твоя задача - отвечать на вопросы пользователя, используя ТОЛЬКО предоставленные контексты.
Если информации в контекстах недостаточно, честно скажи об этом.

{few_shot_text}

{cot_instructions}

Контексты из базы знаний:
{context_text}

Вопрос пользователя: {query}

Пожалуйста, предоставь подробный, точный ответ на основе контекстов выше.
Если используешь информацию из конкретного контекста, можешь указать это в скобках.
Ответ должен быть на русском языке."""

        return prompt

    def call_llm(self, prompt: str) -> Optional[str]:
        """Вызывает LLM через Ollama API"""
        try:
            if self.llm_config['type'] == 'ollama':
                payload = {
                    "model": self.llm_config['model'],
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.llm_config['temperature'],
                        "num_predict": self.llm_config['max_tokens']
                    }
                }

                response = requests.post(
                    self.llm_config['ollama_url'],
                    json=payload,
                    timeout=self.llm_config['timeout']
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', '').strip()
                else:
                    logger.error(f"Ошибка Ollama API: {response.status_code}")
                    return None

            elif self.llm_config['type'] == 'yandexgpt':
                # Резервный вариант для YandexGPT (требуется API ключ)
                # Для использования раскомментируйте и настройте
                """
                headers = {
                    'Authorization': f'Api-Key {YANDEX_API_KEY}',
                    'Content-Type': 'application/json'
                }

                payload = {
                    "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
                    "completionOptions": {
                        "stream": False,
                        "temperature": self.llm_config['temperature'],
                        "maxTokens": self.llm_config['max_tokens']
                    },
                    "messages": [
                        {"role": "system", "content": "Ты полезный ассистент."},
                        {"role": "user", "content": prompt}
                    ]
                }

                response = requests.post(
                    'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
                    headers=headers,
                    json=payload,
                    timeout=self.llm_config['timeout']
                )
                """
                return None  # Заглушка

        except Exception as e:
            logger.error(f"Ошибка при вызове LLM: {e}")
            logger.error(traceback.format_exc())
            return None

    def generate_response(self, query: str, search_results: Dict,
                         use_rag: bool = True) -> Dict:
        """Генерирует ответ используя RAG пайплайн"""

        if not search_results or not search_results['documents']:
            return {
                "answer": "К сожалению, я не нашел информации по вашему запросу в базе знаний.",
                "sources": [],
                "contexts": []
            }

        contexts = search_results['documents'][0]
        metadatas = search_results['metadatas'][0]

        # Извлекаем источники
        sources = []
        for metadata in metadatas:
            source = metadata.get('file_name', 'Неизвестный источник')
            if source not in sources:
                sources.append(source)

        if not use_rag or not self.available_models:
            # Если RAG отключен или модели нет, возвращаем простые результаты
            simple_answer = self._generate_simple_answer(contexts, query)
            return {
                "answer": simple_answer,
                "sources": sources[:3],
                "contexts": contexts[:3]
            }

        # Генерируем промпт с Few-shot и Chain-of-Thought
        prompt = self.generate_prompt(
            query=query,
            contexts=contexts[:3],  # Берем 3 самых релевантных контекста
            use_few_shot=True,
            use_chain_of_thought=True
        )

        # Вызываем LLM
        logger.info(f"Генерация ответа через LLM...")
        start_time = time.time()
        llm_response = self.call_llm(prompt)
        elapsed_time = time.time() - start_time

        if llm_response:
            logger.info(f"Ответ сгенерирован за {elapsed_time:.2f} секунд")
            return {
                "answer": llm_response,
                "sources": sources[:3],
                "contexts": contexts[:3],
                "generation_time": elapsed_time
            }
        else:
            # Fallback на простой ответ
            logger.warning("LLM не ответила, использую простой ответ")
            simple_answer = self._generate_simple_answer(contexts, query)
            return {
                "answer": simple_answer,
                "sources": sources[:3],
                "contexts": contexts[:3]
            }

    def _generate_simple_answer(self, contexts: List[str], query: str) -> str:
        """Генерирует простой ответ без LLM"""
        if not contexts:
            return "Информация по вашему запросу не найдена."

        # Берем самый релевантный контекст
        main_context = contexts[0]

        # Очищаем и обрезаем
        cleaned = self.clean_text(main_context)
        if len(cleaned) > 500:
            cleaned = cleaned[:497] + "..."

        answer = f"На основании найденной информации:\n\n{cleaned}\n\n"
        answer += f"Это ответ на ваш вопрос: '{query}'"

        return answer

    def clean_text(self, text: str) -> str:
        """Очищает текст от лишних символов"""
        # Удаляем множественные пробелы и переносы
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# Инициализируем RAG пайплайн
rag_pipeline = RAGPipeline()


def clean_markdown_text(text: str) -> str:
    """Очищает текст от символов, которые могут сломать Markdown разметку"""
    # Экранируем специальные символы Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

    for char in special_chars:
        text = text.replace(char, f'\\{char}')

    # Удаляем множественные переносы строк
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Обрезаем слишком длинные строки
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if len(line) > 200:
            line = line[:197] + '...'
        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Проверяем доступность индекса и LLM
    index_status = "⚠️ Векторный индекс не доступен."
    llm_status = "⚠️ Локальная LLM не доступна."

    if chroma_search.collection is not None:
        index_status = "✅ Векторный индекс загружен."

    if rag_pipeline.available_models:
        llm_status = f"✅ LLM доступна ({len(rag_pipeline.available_models)} моделей)"
    else:
        llm_status = "⚠️ LLM не доступна (используется простой поиск)"

    await update.message.reply_html(
        f"Привет, {user.mention_html()}! 🤖\n\n"
        f"Я умный бот с RAG-пайплайном:\n\n"
        f"🔍 {index_status}\n"
        f"🧠 {llm_status}\n\n"
        f"Просто напиши мне вопрос, и я найду информацию в базе знаний и сгенерирую развернутый ответ!\n\n"
        f"Используй /rag_on или /rag_off для переключения режима."
    )


# Обработчик команды /rag_on
async def rag_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if rag_pipeline.available_models:
        context.user_data['use_rag'] = True
        await update.message.reply_text(
            "✅ RAG-режим включен!\n\n"
            "Теперь я буду использовать LLM для генерации развернутых ответов на основе найденной информации."
        )
    else:
        await update.message.reply_text(
            "⚠️ Невозможно включить RAG режим.\n"
            "Убедитесь, что Ollama запущен и модели загружены.\n"
            "Текущий режим: простой поиск."
        )


# Обработчик команды /rag_off
async def rag_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['use_rag'] = False
    await update.message.reply_text(
        "✅ RAG-режим выключен!\n\n"
        "Теперь я буду показывать только найденные фрагменты без генерации ответов."
    )


# Обработчик команды /models
async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if rag_pipeline.available_models:
        models_text = "\n".join([f"• {model}" for model in rag_pipeline.available_models])
        await update.message.reply_text(
            f"✅ Доступные модели LLM ({len(rag_pipeline.available_models)}):\n\n"
            f"{models_text}\n\n"
            f"Текущая модель: {LLM_CONFIG['model']}"
        )
    else:
        await update.message.reply_text(
            "❌ Локальные модели не доступны.\n\n"
            "Убедитесь, что:\n"
            "1. Установлен Ollama (ollama.ai)\n"
            "2. Загружена хотя бы одна модель: ollama pull llama3.2:1b\n"
            "3. Ollama сервер запущен"
        )


# Обработчик команды /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if chroma_search.collection:
        try:
            count = chroma_search.collection.count()

            # Проверяем статус LLM
            if rag_pipeline.available_models:
                llm_status = f"✅ Доступна ({len(rag_pipeline.available_models)} моделей)"
            else:
                llm_status = "❌ Не доступна"

            # Проверяем текущий режим RAG
            use_rag = context.user_data.get('use_rag', True)
            rag_mode = "ВКЛЮЧЕН" if use_rag else "ВЫКЛЮЧЕН"

            await update.message.reply_text(
                f"📊 *Статус системы:*\n\n"
                f"🔍 Векторный индекс: ✅ Загружен\n"
                f"📚 Документов в базе: {count}\n"
                f"🧠 Локальная LLM: {llm_status}\n"
                f"🚀 RAG режим: {rag_mode}\n"
                f"🤖 Текущая модель: {LLM_CONFIG['model']}\n\n"
                f"Используйте /rag_on или /rag_off для переключения режима.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Ошибка при получении статуса: {e}")
            await update.message.reply_text(f"⚠️ Индекс доступен, но ошибка при проверке: {e}")
    else:
        await update.message.reply_text(
            "❌ Векторный индекс не загружен!\n\n"
            "Убедитесь, что:\n"
            "1. Запущен скрипт CreateVectorIndex.py\n"
            "2. Папка './chroma_db' существует\n"
            "3. Файлы в './starwars_pages/themes' доступны"
        )


# Обработчик команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *RAG Бот - Помощь*

📚 *Основные команды:*
/start - Начало работы
/help - Эта справка
/status - Статус системы
/models - Показать доступные модели LLM
/rag_on - Включить RAG режим (генерация ответов)
/rag_off - Выключить RAG режим (только поиск)

🔍 *Команды поиска:*
/search [запрос] - Поиск с генерацией ответа
/search5 [запрос] - Поиск с 5 результатами

💡 *Просто напиши вопрос* - и я найду ответ в базе знаний и сгенерирую развернутый ответ!

⚙️ *Технологии:*
• Векторный поиск (ChromaDB)
• RAG пайплайн
• Few-shot learning
• Chain-of-Thought
• Локальная LLM через Ollama

*Примеры вопросов:*
• Кто такой Виктор Дарквуд?
• Что такое световой клинок?
• Расскажи о планете Татуин
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


# Функция для выполнения RAG поиска
async def perform_rag_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, n_results: int = 5):
    # Проверяем доступность индекса
    if chroma_search.collection is None:
        await update.message.reply_text(
            "⚠️ Векторный индекс не доступен!\n\n"
            "Пожалуйста, сначала создайте индекс командой:\n"
            "python CreateVectorIndex.py\n\n"
            "Или проверьте команду /status"
        )
        return

    # Проверяем режим RAG из user_data
    use_rag = context.user_data.get('use_rag', True)

    # Показываем пользователю, что начался поиск
    mode_text = "с генерацией ответа" if use_rag else "без генерации"
    search_message = await update.message.reply_text(
        f"🔍 Ищу информацию по запросу: *{clean_markdown_text(query)}*\n"
        f"Режим: {mode_text}...",
        parse_mode='Markdown'
    )

    # Выполняем поиск
    results = chroma_search.search(query, n_results=n_results)

    if not results or not results['documents'] or not results['documents'][0]:
        await search_message.edit_text(
            f"По запросу *{clean_markdown_text(query)}* ничего не найдено 😔",
            parse_mode='Markdown'
        )
        return

    if not use_rag or not rag_pipeline.available_models:
        # Простой режим - показываем только результаты поиска
        await search_message.delete()
        await show_simple_results(update, query, results)
        return

    # RAG режим - генерируем ответ с помощью LLM
    try:
        await search_message.edit_text(
            f"🔍 Найдено {len(results['documents'][0])} фрагментов\n"
            f"🧠 Генерирую ответ с помощью LLM..."
        )

        # Генерируем ответ через RAG пайплайн
        rag_response = rag_pipeline.generate_response(query, results, use_rag=True)

        # Форматируем ответ
        answer = rag_response["answer"]
        sources = rag_response.get("sources", [])

        response_text = f"📚 *Ответ на запрос: \"{clean_markdown_text(query)}\"*\n\n"
        response_text += f"{clean_markdown_text(answer)}\n\n"

        if sources:
            sources_text = ", ".join([clean_markdown_text(s) for s in sources[:3]])
            response_text += f"📎 *Источники:* {sources_text}\n"

        if "generation_time" in rag_response:
            response_text += f"⏱ *Время генерации:* {rag_response['generation_time']:.2f} сек\n"

        response_text += f"\n⚙️ *Режим:* RAG с LLM ({LLM_CONFIG['model']})"

        # Отправляем ответ
        await search_message.delete()

        # Разбиваем длинное сообщение на части
        if len(response_text) > 4000:
            parts = [response_text[i:i + 4000] for i in range(0, len(response_text), 4000)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(response_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка в RAG пайплайне: {e}")
        logger.error(traceback.format_exc())

        # Fallback на простой режим
        await search_message.edit_text("⚠️ Ошибка генерации, показываю результаты поиска...")
        await show_simple_results(update, query, results)


async def show_simple_results(update: Update, query: str, results: Dict):
    """Показывает простые результаты поиска"""
    response = f"🔍 *Результаты поиска по запросу: \"{clean_markdown_text(query)}\"*\n\n"
    response += "⚠️ *Режим без генерации ответа*\n\n"

    documents = results['documents'][0]
    metadatas = results['metadatas'][0]

    for i, (doc, metadata) in enumerate(zip(documents[:3], metadatas[:3]), 1):
        source_file = metadata.get('file_name', 'Неизвестный файл')

        # Очищаем текст
        cleaned_doc = clean_markdown_text(doc)
        doc_preview = cleaned_doc[:400] + "..." if len(cleaned_doc) > 400 else cleaned_doc

        response += f"*Результат {i}*\n"
        response += f"📁 *Источник:* {clean_markdown_text(source_file)}\n"
        response += f"📝 *Содержание:* {doc_preview}\n"
        response += "━" * 30 + "\n\n"

    response += f"Найдено {len(documents)} фрагментов. Используйте /rag_on для генерации ответов."

    await update.message.reply_text(response, parse_mode='Markdown')


# Обработчик команды /search
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, укажи запрос для поиска.\n"
            "Например: /search Люк Скайуокер"
        )
        return

    query = " ".join(context.args)
    await perform_rag_search(update, context, query, n_results=3)


# Обработчик команды /search5
async def search5_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, укажи запрос для поиска.\n"
            "Например: /search5 Сила"
        )
        return

    query = " ".join(context.args)
    await perform_rag_search(update, context, query, n_results=5)


# Обработчик обычных текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text

    # Пропускаем команды
    if query.startswith('/'):
        return

    # Автоматически выполняем RAG поиск
    await perform_rag_search(update, context, query, n_results=3)


async def post_init(application: Application):
    """Функция, выполняемая после инициализации бота"""
    logger.info("Бот успешно инициализирован")

    if chroma_search.collection:
        try:
            count = chroma_search.collection.count()
            logger.info(f"✅ Векторный индекс загружен. Документов: {count}")
            print(f"✅ Векторный индекс загружен. Документов: {count}")
        except Exception as e:
            logger.warning(f"Ошибка при подсчете документов: {e}")
            print(f"⚠️ Ошибка при подсчете документов: {e}")
    else:
        logger.warning("❌ Векторный индекс не загружен!")
        print("❌ Векторный индекс не загружен!")
        print("Пожалуйста, сначала создайте индекс:")
        print("python CreateVectorIndex.py")

    # Проверяем доступность LLM
    if rag_pipeline.available_models:
        logger.info(f"✅ LLM доступны: {rag_pipeline.available_models}")
        print(f"✅ LLM модели доступны: {rag_pipeline.available_models}")
    else:
        logger.warning("❌ LLM не доступна! Используется простой режим.")
        print("❌ LLM не доступна!")
        print("Для использования RAG режима установите Ollama:")
        print("1. Установите Ollama: https://ollama.ai/")
        print("2. Загрузите модель: ollama pull llama3.2:1b")
        print("3. Запустите Ollama")

    print("=" * 50)
    print("🤖 Телеграм RAG бот с векторным поиском и LLM")
    print("=" * 50)
    print(f"Токен: {TOKEN}")
    print(f"Режим по умолчанию: RAG {'включен' if rag_pipeline.available_models else 'выключен'}")
    print("=" * 50)


def main():
    try:
        # Создаем Application
        application = Application.builder().token(TOKEN).post_init(post_init).build()

        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("models", models_command))
        application.add_handler(CommandHandler("rag_on", rag_on_command))
        application.add_handler(CommandHandler("rag_off", rag_off_command))
        application.add_handler(CommandHandler("search", search_command))
        application.add_handler(CommandHandler("search5", search5_command))

        # Регистрируем обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Запускаем бота в режиме Long Polling
        logger.info("Бот запущен...")

        # Запускаем polling
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        logger.error(f"Ошибка при запуске бota: {e}")
        print(f"Критическая ошибка: {e}")


if __name__ == '__main__':
    main()