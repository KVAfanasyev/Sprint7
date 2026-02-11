import time
import os
import json
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from collections import Counter

# Настройки
BASE_URL = "https://starwars.fandom.com/wiki"
DOWNLOAD_DIR = "starwars_pages"
THEMES_DIR = os.path.join(DOWNLOAD_DIR, "themes")
REQUEST_DELAY = 2

# Таймауты
DRIVER_TIMEOUT = 10
ELEMENT_TIMEOUT = 15
PAGE_LOAD_TIMEOUT = 25

# Список страниц
PAGES_TO_DOWNLOAD = [
    "Luke_Skywalker",
    "Darth_Vader",
    "Yoda",
    "Han_Solo",
    "Princess_Leia",
    "Obi-Wan_Kenobi",
    "Chewbacca",
    "R2-D2",
    "C-3PO",
    "Emperor_Palpatine"
]

# Определение тем и их ключевых слов
THEMES = {
    "biography": {
        "keywords": ["born", "birth", "early life", "childhood", "grew up", "family",
                     "parents", "mother", "father", "origins", "background", "upbringing"],
        "description": "Биографические сведения, происхождение, детство и семья"
    },
    "appearance": {
        "keywords": ["appearance", "looks", "height", "weight", "hair", "eyes", "skin",
                     "clothing", "armor", "costume", "physical", "features", "species"],
        "description": "Физическое описание, внешность, одежда и отличительные черты"
    },
    "personality": {
        "keywords": ["personality", "character", "traits", "behavior", "attitude",
                     "morals", "beliefs", "values", "philosophy", "temperament", "mindset"],
        "description": "Черты характера, личностные особенности, моральные принципы"
    },
    "abilities": {
        "keywords": ["abilities", "skills", "powers", "force", "lightsaber", "combat",
                     "training", "master", "expert", "proficient", "talent", "capabilities"],
        "description": "Силы, навыки, боевые умения, владение Силой и другие способности"
    },
    "equipment": {
        "keywords": ["weapon", "lightsaber", "blaster", "armor", "tool", "device",
                     "equipment", "gear", "ship", "vehicle", "technology", "droid"],
        "description": "Оружие, снаряжение, техника, корабли и другие инструменты"
    },
    "relationships": {
        "keywords": ["friend", "ally", "enemy", "rival", "master", "apprentice",
                     "relationship", "love", "hate", "family", "comrade", "companion"],
        "description": "Отношения с другими персонажами, друзья, враги, союзники"
    },
    "story_arc": {
        "keywords": ["story", "plot", "events", "battle", "war", "mission", "journey",
                     "adventure", "conflict", "quest", "saga", "timeline", "history"],
        "description": "Сюжетные линии, ключевые события, битвы и приключения"
    },
    "affiliations": {
        "keywords": ["jedi", "sith", "rebel", "empire", "alliance", "faction",
                     "organization", "group", "order", "guild", "affiliation", "loyalty"],
        "description": "Принадлежность к организациям, фракциям, орденам и группам"
    },
    "achievements": {
        "keywords": ["achievement", "accomplishment", "victory", "defeat", "success",
                     "failure", "honor", "award", "medal", "rank", "title", "legacy"],
        "description": "Достижения, победы, награды, звания и наследие"
    },
    "quotes": {
        "keywords": ["said", "quote", "spoke", "uttered", "exclaimed", "declared",
                     "words", "speech", "dialogue", "phrase", "statement", "remark"],
        "description": "Известные цитаты, высказывания, диалоги и реплики персонажа"
    }
}

# Словарь для замены имен
CHARACTER_REPLACEMENTS = {
    "Luke": "Jack",
    "Skywalker": "Thompson",
    "Darth": "Victor",
    "Vader": "Darkwood",
    "Yoda": "Yorin",
    "Han": "Hank",
    "Solo": "Sullivan",
    "Princess": "Princess",
    "Leia": "Leah",
    "Obi-Wan": "Benjamin",
    "Kenobi": "Stone",
    "Chewbacca": "Chester",
    "R2-D2": "Artoo",
    "C-3PO": "See-Threepio",
    "Emperor": "Emperor",
    "Palpatine": "Paladin",
    "Jedi": "Guardians",
    "Sith": "Shadow Knights",
    "Galactic": "Imperial",
    "Empire": "Union",
    "Rebel": "Freedom",
    "Force": "Energy",
    "Lightsaber": "Lightblade",
    "Star": "Worm",
    "Wars": "Copulation",
}

COMPOUND_REPLACEMENTS = {
    "Darth Vader": "Victor Darkwood",
    "Luke Skywalker": "Jack Thompson",
    "Han Solo": "Hank Sullivan",
    "Princess Leia": "Princess Leah",
    "Obi-Wan Kenobi": "Benjamin Stone",
    "Emperor Palpatine": "Emperor Paladin",
    "Star Wars": "The Worm Copulation",
    "The Force": "The Energy",
}


def setup_nltk():
    """Настроить и загрузить необходимые ресурсы NLTK"""
    try:
        print("Настройка NLTK...")

        # Список необходимых ресурсов
        resources = ['punkt', 'punkt_tab', 'stopwords', 'averaged_perceptron_tagger']

        for resource in resources:
            try:
                if resource == 'punkt_tab':
                    # Для punkt_tab используем альтернативный подход
                    nltk.download('punkt', quiet=True)
                else:
                    nltk.download(resource, quiet=True)
                print(f"  Ресурс '{resource}' загружен")
            except Exception as e:
                print(f"  Предупреждение: Не удалось загрузить '{resource}': {e}")

        # Проверяем доступность стоп-слов
        try:
            stopwords.words('english')
            print("  Стоп-слова доступны")
        except:
            print("  Предупреждение: Стоп-слова недоступны")

    except Exception as e:
        print(f"Ошибка при настройке NLTK: {e}")
        print("Продолжаем без NLTK...")


def simple_sentence_tokenize(text):
    """Простая токенизация предложений без NLTK"""
    if not text:
        return []

    # Разделяем на предложения по точкам, восклицательным и вопросительным знакам
    sentences = []
    current_sentence = []

    for char in text:
        current_sentence.append(char)
        if char in '.!?':
            sentences.append(''.join(current_sentence).strip())
            current_sentence = []

    # Добавляем последнее предложение, если оно есть
    if current_sentence:
        sentences.append(''.join(current_sentence).strip())

    # Фильтруем пустые предложения и короткие строки
    sentences = [s for s in sentences if len(s) > 10]

    return sentences


def extract_themes_from_text(text, page_name):
    """
    Разбить текст на темы на основе ключевых слов

    Args:
        text: Текст для анализа
        page_name: Имя страницы

    Returns:
        Словарь с темами и соответствующими предложениями
    """
    if not text or len(text.strip()) < 50:
        return {}

    try:
        # Пытаемся использовать NLTK для токенизации
        try:
            sentences = sent_tokenize(text)
        except:
            # Если NLTK не работает, используем простую токенизацию
            sentences = simple_sentence_tokenize(text)

        # Создаем словарь для хранения предложений по темам
        theme_sentences = {theme_name: [] for theme_name in THEMES.keys()}
        other_sentences = []

        for sentence in sentences:
            sentence_lower = sentence.lower()

            # Подсчитываем совпадения с ключевыми словами каждой темы
            theme_matches = {}

            for theme_name, theme_info in THEMES.items():
                matches = 0
                keywords = theme_info["keywords"]

                # Проверяем каждое ключевое слово
                for keyword in keywords:
                    keyword_pattern = r'\b' + re.escape(keyword) + r'\b'
                    if re.search(keyword_pattern, sentence_lower):
                        matches += 2  # Полное совпадение
                    elif keyword in sentence_lower:
                        matches += 1  # Частичное совпадение

                theme_matches[theme_name] = matches

            # Находим тему с максимальным количеством совпадений
            if theme_matches:
                best_theme = max(theme_matches, key=theme_matches.get)
                if theme_matches[best_theme] > 0:
                    theme_sentences[best_theme].append(sentence)
                else:
                    other_sentences.append(sentence)
            else:
                other_sentences.append(sentence)

        # Добавляем тему "other" для неклассифицированных предложений
        theme_sentences["other"] = other_sentences

        # Удаляем пустые темы
        theme_sentences = {k: v for k, v in theme_sentences.items() if v}

        # Логируем результаты классификации
        print(f"  Классификация для {page_name}:")
        for theme_name, sent_list in theme_sentences.items():
            if theme_name in THEMES:
                print(f"    - {theme_name}: {len(sent_list)} предложений")

        if theme_sentences.get("other"):
            print(f"    - other: {len(theme_sentences['other'])} предложений")

        return theme_sentences

    except Exception as e:
        print(f"  Ошибка при классификации тем: {e}")
        # Возвращаем весь текст как одну тему
        return {"all_text": [text]}


def save_themes_to_files(theme_sentences, page_name, counter, original_name):
    """
    Сохранить предложения по темам в отдельные файлы
    """
    # Создаем поддиректорию для этой страницы
    page_themes_dir = os.path.join(THEMES_DIR, f"{counter:03d}_{page_name}")
    if not os.path.exists(page_themes_dir):
        os.makedirs(page_themes_dir)

    # Сохраняем каждую тему в отдельный файл
    theme_files = []

    for theme_name, sentences in theme_sentences.items():
        if not sentences:
            continue

        # Формируем имя файла для темы
        if theme_name in THEMES:
            theme_description = THEMES[theme_name]["description"]
            filename = f"{counter:03d}_{page_name}_{theme_name}.txt"
        elif theme_name == "other":
            theme_description = "Не классифицированные предложения"
            filename = f"{counter:03d}_{page_name}_other.txt"
        else:
            theme_description = "Весь текст"
            filename = f"{counter:03d}_{page_name}_all.txt"

        filepath = os.path.join(page_themes_dir, filename)

        # Сохраняем тему в файл
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Тема: {theme_name}\n")
                f.write(f"Описание: {theme_description}\n")
                f.write(f"Персонаж: {page_name}\n")
                f.write(f"Оригинальное имя: {original_name}\n")
                f.write(f"Количество предложений: {len(sentences)}\n")
                f.write("=" * 60 + "\n\n")

                for i, sentence in enumerate(sentences, 1):
                    f.write(f"{i:03d}. {sentence}\n\n")

            theme_files.append({
                "theme": theme_name,
                "file": filename,
                "sentences_count": len(sentences),
                "description": theme_description
            })

        except Exception as e:
            print(f"  Ошибка сохранения темы {theme_name}: {e}")

    # Сохраняем метаданные о темах
    if theme_files:
        try:
            metadata_file = os.path.join(page_themes_dir, f"{counter:03d}_{page_name}_themes_meta.json")
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "page_name": page_name,  # Замененное имя
                    "original_name": original_name,  # Оригинальное имя
                    "themes": theme_files,
                    "total_sentences": sum(len(s) for s in theme_sentences.values())
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  Ошибка сохранения метаданных тем: {e}")

    return theme_files


def replace_starwars_names(text):
    """Заменить имена персонажей Star Wars на обычные имена"""
    if not text:
        return text

    # Сначала заменяем составные выражения
    for starwars_name, normal_name in COMPOUND_REPLACEMENTS.items():
        pattern = r'\b' + re.escape(starwars_name) + r'\b'
        text = re.sub(pattern, normal_name, text, flags=re.IGNORECASE)

    # Затем заменяем отдельные слова
    for starwars_name, normal_name in CHARACTER_REPLACEMENTS.items():
        pattern = r'\b' + re.escape(starwars_name) + r'\b'
        text = re.sub(pattern, normal_name, text, flags=re.IGNORECASE)

    return text


def setup_driver():
    """Настройка Selenium WebDriver"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        driver.set_script_timeout(30)
        return driver
    except Exception as e:
        print(f"Ошибка при настройке драйвера: {e}")
        return None


def extract_description(soup):
    """Извлечь описание со страницы"""
    content = soup.find('div', {'class': 'mw-parser-output'})

    if not content:
        content = soup.find('main') or soup.find('article') or soup.find('div', {'id': 'content'})

    if not content:
        return "Основной контент страницы не найден."

    # Удаляем ненужные элементы
    elements_to_remove = ['table', 'div', 'span', 'aside', 'nav', 'figure', 'script', 'style', 'iframe']
    for elem in content.find_all(elements_to_remove):
        if elem and hasattr(elem, 'attrs') and elem.attrs is not None:
            class_list = elem.get('class', [])
            if class_list:
                class_str = ' '.join(class_list)
                if any(x in class_str for x in ['infobox', 'navbox', 'reference', 'toc',
                                                'metadata', 'sidebar', 'portable-infobox',
                                                'pi', 'wds-tabber', 'quote', 'thumb',
                                                'noviewer', 'mw-references-wrap', 'mbox',
                                                'hatnote', 'mw-editsection']):
                    elem.decompose()
            else:
                if elem.name in ['script', 'style', 'iframe', 'nav', 'aside']:
                    elem.decompose()

    # Извлекаем текст из параграфов
    paragraphs = content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
    text = ''

    for elem in paragraphs:
        if elem and elem.text:
            elem_text = elem.text.strip()
            if elem_text and len(elem_text) > 5:
                text += elem_text + '\n\n'

    return text.strip() if text else "Не удалось извлечь текст со страницы."


def download_page_with_selenium(driver, page_name, counter):
    """Скачать одну страницу"""
    url = f"{BASE_URL}/{page_name}"
    html_content = None
    success = False

    try:
        print(f"\n[{counter}/{len(PAGES_TO_DOWNLOAD)}] Скачиваю: {page_name}")
        print(f"  URL: {url}")

        try:
            driver.get(url)
            time.sleep(3)  # Даем время на загрузку

            # Проверяем, загрузилась ли страница
            if "404" in driver.title or "Not Found" in driver.title:
                print(f"  Ошибка: Страница не найдена")
                html_content = f"<html><body>Страница не найдена: {url}</body></html>"
            else:
                html_content = driver.page_source
                success = True

        except TimeoutException:
            print(f"  Предупреждение: Таймаут загрузки страницы")
            try:
                html_content = driver.execute_script("return document.documentElement.outerHTML;")
                if html_content and len(html_content) > 100:
                    success = True
                    print("  Получен частично загруженный контент")
            except:
                html_content = "<html><body>Таймаут загрузки страницы</body></html>"

        except Exception as e:
            print(f"  Ошибка загрузки: {e}")
            html_content = f"<html><body>Ошибка загрузки: {str(e)}</body></html>"

        # Парсим HTML
        soup = BeautifulSoup(html_content, 'html.parser') if html_content else BeautifulSoup("<html></html>",
                                                                                             'html.parser')

        # Извлекаем заголовок
        title_elem = soup.find('h1')
        title = title_elem.text.strip() if title_elem else page_name

        # Извлекаем описание
        description = extract_description(soup)

        # ЗАМЕНА ИМЕН
        title = replace_starwars_names(title)
        description = replace_starwars_names(description)

        # Формируем имя файла с использованием замененного имени
        # Создаем безопасное имя файла из заголовка после замены
        safe_title = re.sub(r'[^\w\-_]', '_', title)
        filename = f"{counter:03d}_{safe_title}.txt"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        status_info = "STATUS: УСПЕШНО" if success else "STATUS: ЧАСТИЧНО ЗАГРУЖЕНО"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"Original URL: {url}\n")
            f.write(f"Download Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{status_info}\n")
            f.write("=" * 80 + "\n\n")
            f.write(description)

        print(f"  Сохранено: {filename} ({'успешно' if success else 'частично'})")

        # --- РАЗБИЕНИЕ НА ТЕМЫ ---
        if description and len(description) > 100:
            print("  Разбиваю текст на темы...")

            # Разбиваем текст на темы
            theme_sentences = extract_themes_from_text(description, safe_title)

            if theme_sentences:
                # Сохраняем темы в отдельные файлы (используем safe_title вместо оригинального имени)
                theme_files = save_themes_to_files(theme_sentences, safe_title, counter, page_name)
                print(f"  Создано {len(theme_files)} тематических файлов")
            else:
                print("  Предупреждение: Не удалось выделить темы из текста")
        else:
            print("  Предупреждение: Текст слишком короткий для разбивки на темы")

        return success

    except Exception as e:
        print(f"  Критическая ошибка: {e}")

        # Создаем файл с ошибкой
        safe_title = re.sub(r'[^\w\-_]', '_', page_name)
        filename = f"{counter:03d}_{safe_title}_ERROR.txt"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Title: Ошибка загрузки: {page_name}\n")
            f.write(f"Original URL: {url}\n")
            f.write(f"Download Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("STATUS: ОШИБКА\n")
            f.write(f"Error: {str(e)}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Не удалось загрузить страницу. Ошибка: {str(e)}")

        return False


def create_themes_summary():
    """Создать сводный файл по всем темам"""
    if not os.path.exists(THEMES_DIR):
        return

    summary_file = os.path.join(THEMES_DIR, "ALL_THEMES_SUMMARY.txt")

    try:
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("СВОДКА ПО ВСЕМ ТЕМАМ\n")
            f.write(f"Дата создания: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            f.write("ОПРЕДЕЛЕННЫЕ ТЕМЫ И ИХ КЛЮЧЕВЫЕ СЛОВА:\n")
            f.write("=" * 80 + "\n")

            for theme_name, theme_info in THEMES.items():
                f.write(f"\nТЕМА: {theme_name.upper()}\n")
                f.write(f"Описание: {theme_info['description']}\n")
                f.write(f"Ключевые слова: {', '.join(theme_info['keywords'][:5])}...\n")

            # Собираем статистику
            f.write("\n\nСТАТИСТИКА ПО СТРАНИЦАМ:\n")
            f.write("=" * 80 + "\n")

            theme_stats = {theme_name: 0 for theme_name in THEMES.keys()}
            theme_stats["other"] = 0
            total_pages = 0

            # Проходим по директориям
            for item in os.listdir(THEMES_DIR):
                item_path = os.path.join(THEMES_DIR, item)
                if os.path.isdir(item_path):
                    total_pages += 1

                    # Ищем метаданные
                    meta_files = [f for f in os.listdir(item_path) if f.endswith('_themes_meta.json')]
                    if meta_files:
                        try:
                            meta_file = os.path.join(item_path, meta_files[0])
                            with open(meta_file, 'r', encoding='utf-8') as mf:
                                meta_data = json.load(mf)

                            f.write(f"\n{meta_data.get('page_name', 'Unknown')}:\n")
                            f.write(f"  (оригинал: {meta_data.get('original_name', 'Unknown')})\n")

                            for theme_info in meta_data.get('themes', []):
                                theme_name = theme_info['theme']
                                count = theme_info['sentences_count']
                                if theme_name in theme_stats:
                                    theme_stats[theme_name] += 1
                                f.write(f"  - {theme_name}: {count} предложений\n")

                        except Exception as e:
                            f.write(f"\n{item}: Ошибка чтения: {e}\n")

            f.write("\n\nОБЩАЯ СТАТИСТИКА:\n")
            f.write("=" * 80 + "\n")
            f.write(f"Всего страниц с темами: {total_pages}\n")
            f.write("Наиболее частые темы:\n")

            for theme_name, count in sorted(theme_stats.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    f.write(f"  - {theme_name}: {count} страниц\n")

        print(f"\nСводный файл по темам создан: {summary_file}")

    except Exception as e:
        print(f"Ошибка создания сводного файла: {e}")


def main():
    """Основная функция"""
    # Создаем директории
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)

    # Настраиваем NLTK
    setup_nltk()

    print(f"\nСкачиваю {len(PAGES_TO_DOWNLOAD)} страниц со Star Wars Wiki...")
    print("Примечание:")
    print("  - Имена персонажей будут заменены на обычные имена")
    print("  - Текст будет разбит на тематические файлы")
    print("  - 'Star Wars' заменяется на 'The Worm Copulation'")

    # Настраиваем драйвер
    driver = setup_driver()
    if not driver:
        print("Ошибка: Не удалось инициализировать WebDriver")
        return

    successful = 0
    partial = 0
    failed = 0

    try:
        for i, page in enumerate(PAGES_TO_DOWNLOAD, 1):
            result = download_page_with_selenium(driver, page, i)

            if result:
                successful += 1
            else:
                # Проверяем, есть ли файл с ошибкой
                safe_page_name = re.sub(r'[^\w\-_]', '_', page)
                error_file = os.path.join(DOWNLOAD_DIR, f"{i:03d}_{safe_page_name}_ERROR.txt")
                if os.path.exists(error_file):
                    failed += 1
                else:
                    partial += 1

            # Задержка между запросами
            if i < len(PAGES_TO_DOWNLOAD):
                time.sleep(REQUEST_DELAY)

    except Exception as e:
        print(f"\nОшибка в основном цикле: {e}")

    finally:
        if driver:
            try:
                driver.quit()
                print("\nДрайвер закрыт.")
            except:
                pass

    # Создаем сводку по темам
    create_themes_summary()

    print(f"\n{'=' * 60}")
    print("ИТОГИ СКАЧИВАНИЯ:")
    print(f"  Успешно: {successful}/{len(PAGES_TO_DOWNLOAD)}")
    print(f"  Частично: {partial}/{len(PAGES_TO_DOWNLOAD)}")
    print(f"  Ошибки: {failed}/{len(PAGES_TO_DOWNLOAD)}")
    print(f"\nФайлы сохранены в: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"Темы сохранены в: {os.path.abspath(THEMES_DIR)}")

    # Создаем индексный файл
    index_file = os.path.join(DOWNLOAD_DIR, "INDEX.txt")
    try:
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write("ИНДЕКС СКАЧАННЫХ СТРАНИЦ STAR WARS WIKI\n")
            f.write(f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            f.write("СТАТИСТИКА:\n")
            f.write(f"  Всего страниц: {len(PAGES_TO_DOWNLOAD)}\n")
            f.write(f"  Успешно: {successful}\n")
            f.write(f"  Частично: {partial}\n")
            f.write(f"  Ошибки: {failed}\n\n")

            f.write("СПИСОК СТРАНИЦ:\n")
            for i, page in enumerate(PAGES_TO_DOWNLOAD, 1):
                safe_page_name = re.sub(r'[^\w\-_]', '_', page)
                txt_file = os.path.join(DOWNLOAD_DIR, f"{i:03d}_{safe_page_name}.txt")
                error_file = os.path.join(DOWNLOAD_DIR, f"{i:03d}_{safe_page_name}_ERROR.txt")

                if os.path.exists(error_file):
                    status = "[ОШИБКА]"
                elif os.path.exists(txt_file):
                    try:
                        with open(txt_file, 'r', encoding='utf-8') as tf:
                            content = tf.read(200)
                            if "STATUS: УСПЕШНО" in content:
                                status = "[OK]"
                            elif "STATUS: ЧАСТИЧНО" in content:
                                status = "[ЧАСТИЧНО]"
                            else:
                                status = "[ФАЙЛ]"
                    except:
                        status = "[ФАЙЛ]"
                else:
                    status = "[НЕТ]"

                f.write(f"{i:03d}. {page} {status}\n")

        print(f"\nИндексный файл создан: {index_file}")

    except Exception as e:
        print(f"Ошибка создания индексного файла: {e}")


if __name__ == "__main__":
    main()