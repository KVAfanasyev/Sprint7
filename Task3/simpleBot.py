# ФИКС ДЛЯ NUMPY 2.X - ДОБАВЬТЕ В САМОЕ НАЧАЛО
import numpy as np

# Исправление для numpy 2.x
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

# Включаем логирование, чтобы видеть ошибки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = '8317799983:AAHEBTNTj7QD7lj5Oc9QQZBIkdp8zBCHlYs'


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

    def search(self, query: str, n_results: int = 3):
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

    # Проверяем доступность индекса
    if chroma_search.collection is None:
        status_text = "⚠️ Векторный индекс не доступен. Проверьте наличие папки './chroma_db'."
    else:
        status_text = "✅ Векторный индекс загружен и готов к поиску."

    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я умный бот с поиском по знаниям.\n\n"
        f"{status_text}\n\n"
        "Просто напиши мне вопрос, и я найду самую релевантную информацию из базы знаний!"
    )


# Обработчик команды /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if chroma_search.collection:
        try:
            count = chroma_search.collection.count()
            await update.message.reply_text(
                f"✅ Бот работает нормально.\n"
                f"📊 В базе знаний: {count} документов\n"
                f"🔍 Индекс готов к поиску"
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
📚 *Доступные команды:*

/start - Начало работы
/help - Помощь
/status - Проверить состояние индекса
/search [запрос] - Поиск информации (3 результата)
/search5 [запрос] - Поиск информации (5 результатов)

💡 *Просто напиши вопрос* - и я найду ответы в базе знаний!

Примеры вопросов:
• Кто такой Люк Скайуокер?
• Что такое Сила?
• Какие виды световых мечей существуют?
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


# Обработчик команды /search
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, укажи запрос для поиска.\n"
            "Например: /search Люк Скайуокер"
        )
        return

    query = " ".join(context.args)
    await perform_search(update, query, n_results=3)


# Обработчик команды /search5
async def search5_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, укажи запрос для поиска.\n"
            "Например: /search5 Сила"
        )
        return

    query = " ".join(context.args)
    await perform_search(update, query, n_results=5)


# Функция для выполнения поиска
async def perform_search(update: Update, query: str, n_results: int):
    # Проверяем доступность индекса
    if chroma_search.collection is None:
        await update.message.reply_text(
            "⚠️ Векторный индекс не доступен!\n\n"
            "Пожалуйста, сначала создайте индекс командой:\n"
            "python CreateVectorIndex.py\n\n"
            "Или проверьте команду /status"
        )
        return

    # Показываем пользователю, что начался поиск
    search_message = await update.message.reply_text(f"🔍 Ищу информацию по запросу: *{clean_markdown_text(query)}*",
                                                     parse_mode='Markdown')

    # Выполняем поиск
    results = chroma_search.search(query, n_results=n_results)

    if not results or not results['documents'] or not results['documents'][0]:
        await search_message.edit_text(f"По запросу *{clean_markdown_text(query)}* ничего не найдено 😔",
                                       parse_mode='Markdown')
        return

    # Формируем ответ
    response = f"📚 *Результаты поиска по запросу: \"{clean_markdown_text(query)}\"*\n\n"

    documents = results['documents'][0]
    metadatas = results['metadatas'][0]
    distances = results.get('distances', [[]])[0]

    for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances), 1):
        source_file = metadata.get('file_name', 'Неизвестный файл')
        chunk_index = metadata.get('chunk_index', 0)
        total_chunks = metadata.get('total_chunks', 0)

        # Очищаем текст от проблемных символов Markdown
        cleaned_doc = clean_markdown_text(doc)

        # Форматируем текст (ограничиваем длину)
        doc_preview = cleaned_doc[:300] + "..." if len(cleaned_doc) > 300 else cleaned_doc

        # Добавляем релевантность (чем меньше расстояние, тем выше релевантность)
        relevance_score = max(0, 1 - distance) * 100

        # Используем Markdown только для заголовков, текст содержимого - обычный
        response += f"*Результат {i}* (релевантность: {relevance_score:.1f}%)\n"
        response += f"*Источник:* {clean_markdown_text(source_file)}\n"
        response += f"*Содержание:* {doc_preview}\n"
        response += "━" * 30 + "\n\n"

    # Добавляем общую информацию
    response += f"Найдено {len(documents)} наиболее релевантных фрагментов."

    # Вместо редактирования сообщения, отправляем новое
    try:
        await search_message.delete()
    except:
        pass

    # Разбиваем длинное сообщение на части (Telegram имеет ограничение на длину сообщения)
    if len(response) > 4000:
        parts = [response[i:i + 4000] for i in range(0, len(response), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await update.message.reply_text(response, parse_mode='Markdown')


# Обработчик обычных текстовых сообщений (интеллектуальный поиск)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text

    # Пропускаем команды
    if query.startswith('/'):
        return

    # Автоматически выполняем поиск для всех сообщений
    await perform_search(update, query, n_results=3)


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


def main():
    try:
        # Создаем Application
        application = Application.builder().token(TOKEN).post_init(post_init).build()

        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("search", search_command))
        application.add_handler(CommandHandler("search5", search5_command))

        # Регистрируем обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Запускаем бота в режиме Long Polling
        logger.info("Бот запущен...")
        print("=" * 50)
        print("🤖 Телеграм бот с поиском по векторному индексу")
        print("=" * 50)
        print(f"Токен: {TOKEN}")
        print("=" * 50)

        # Запускаем polling
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        print(f"Критическая ошибка: {e}")


if __name__ == '__main__':
    main()