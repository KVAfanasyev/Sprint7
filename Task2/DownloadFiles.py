import time
import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

# Настройки
BASE_URL = "https://starwars.fandom.com/wiki"
DOWNLOAD_DIR = "starwars_pages"
REQUEST_DELAY = 2

# Таймауты (в секундах)
DRIVER_TIMEOUT = 10  # Таймаут для загрузки страницы
ELEMENT_TIMEOUT = 15  # Таймаут для ожидания элементов
PAGE_LOAD_TIMEOUT = 25 # Общий таймаут загрузки страницы

# Список популярных страниц Star Wars для скачивания
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
    "Emperor_Palpatine",
    "Darth_Maul",
    "Padmé_Amidala",
    "Jabba_the_Hutt",
    "Lando_Calrissian",
    "Kylo_Ren",
    "Rey_(Star_Wars)",
    "Finn_(Star_Wars)",
    "Poe_Dameron",
    "BB-8",
    "The_Force",
    "Lightsaber",
    "Jedi",
    "Sith",
    "Galactic_Empire",
    "Rebel_Alliance",
    "Millennium_Falcon",
    "Tatooine",
    "Endor",
    "Naboo",
    "Kashyyyk",
    "Star_Destroyer",
    "X-wing",
    "TIE_Fighter",
    "Clone_Trooper",
    "Stormtrooper",
    "Wookiee",
    "Ewok",
    "Blaster",
    "Clone_Wars",
]

# Словарь для замены имен персонажей Star Wars на обычные имена
CHARACTER_REPLACEMENTS = {
    # Основные персонажи
    "Luke Skywalker": "Jack Thompson",
    "Darth Vader": "Victor Darkwood",
    "Yoda": "Elder Yorin",
    "Han Solo": "Hank Sullivan",
    "Princess Leia": "Leah Preston",
    "Obi-Wan Kenobi": "Benjamin Stone",
    "Chewbacca": "Chester Wookiee",
    "R2-D2": "Artoo",
    "C-3PO": "See-Threepio",
    "Emperor Palpatine": "Emperor Paladin",
    "Darth Maul": "Marcus Maul",
    "Padmé Amidala": "Padma Amari",
    "Jabba the Hutt": "Jabba Hutt",
    "Lando Calrissian": "Lando Carlisle",
    "Kylo Ren": "Kyle Renner",
    "Rey": "Reyna",
    "Finn": "Finnley",
    "Poe Dameron": "Paul Dameron",
    "BB-8": "BeeBee",

    # Группы и организации
    "Jedi": "Guardians",
    "Sith": "Shadow Knights",
    "Galactic Empire": "Imperial Union",
    "Rebel Alliance": "Freedom Alliance",
    "Clone Trooper": "Clone Soldier",
    "Stormtrooper": "Imperial Soldier",
    "Wookiee": "Wookie",
    "Ewok": "Ewokian",

    # Планеты и места
    "Tatooine": "Desertia",
    "Endor": "Forestia",
    "Naboo": "Aquaria",
    "Kashyyyk": "Kashyyyk Prime",

    # Корабли и техника
    "Millennium Falcon": "Millennium Hawk",
    "Star Destroyer": "Star Cruiser",
    "X-wing": "X-fighter",
    "TIE Fighter": "TIE Interceptor",

    # Другие термины
    "The Force": "The Energy",
    "Lightsaber": "Lightblade",
    "Blaster": "Energy Gun",
    "Clone Wars": "Clone Conflict"
}

# Также добавляем варианты с разными регистрами и формами
ADDITIONAL_REPLACEMENTS = {}
for original, replacement in CHARACTER_REPLACEMENTS.items():
    # Разные формы написания
    ADDITIONAL_REPLACEMENTS[original.lower()] = replacement.lower()
    ADDITIONAL_REPLACEMENTS[original.upper()] = replacement.upper()

    # Имена без фамилий (для упоминаний в тексте)
    if " " in original:
        first_name = original.split()[0]
        replacement_first = replacement.split()[0]
        ADDITIONAL_REPLACEMENTS[first_name] = replacement_first
        ADDITIONAL_REPLACEMENTS[first_name.lower()] = replacement_first.lower()

# Объединяем словари
FULL_REPLACEMENT_DICT = {**CHARACTER_REPLACEMENTS, **ADDITIONAL_REPLACEMENTS}

# Также заменяем названия страниц (используется в именах файлов)
PAGE_NAME_REPLACEMENTS = {
    "Luke_Skywalker": "Jack_Thompson",
    "Darth_Vader": "Victor_Darkwood",
    "Yoda": "Elder_Yorin",
    "Han_Solo": "Hank_Sullivan",
    "Princess_Leia": "Leah_Preston",
    "Obi-Wan_Kenobi": "Benjamin_Stone",
    "Chewbacca": "Chester_Wookiee",
    "R2-D2": "Artoo",
    "C-3PO": "See-Threepio",
    "Emperor_Palpatine": "Emperor_Paladin",
    "Darth_Maul": "Marcus_Maul",
    "Padmé_Amidala": "Padma_Amari",
    "Jabba_the_Hutt": "Jabba_Hutt",
    "Lando_Calrissian": "Lando_Carlisle",
    "Kylo_Ren": "Kyle_Renner",
    "Rey_(Star_Wars)": "Reyna",
    "Finn_(Star_Wars)": "Finnley",
    "Poe_Dameron": "Paul_Dameron",
    "BB-8": "BeeBee"
}


def replace_starwars_names(text):
    """Заменить имена персонажей Star Wars на обычные имена"""
    if not text:
        return text

    for starwars_name, normal_name in FULL_REPLACEMENT_DICT.items():
        if starwars_name in text:
            text = text.replace(starwars_name, normal_name)

    return text


def setup_driver():
    """Настройка Selenium WebDriver с увеличенными таймаутами"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Фоновый режим
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    # Отключаем некоторые функции для ускорения загрузки
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-logging')
    options.add_argument('--log-level=3')
    options.add_argument('--output=/dev/null')

    try:
        driver = webdriver.Chrome(options=options)

        # Устанавливаем таймауты
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        driver.set_script_timeout(30)

        return driver
    except Exception as e:
        print(f"Ошибка при настройке драйвера: {e}")
        raise


def extract_description(soup):
    """Извлечь описание со страницы"""
    # Основной контент на Fandom обычно в div с классом mw-parser-output
    content = soup.find('div', {'class': 'mw-parser-output'})

    if not content:
        # Попробуем найти любой контент
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
                # Удаляем некоторые элементы даже без классов
                if elem.name in ['script', 'style', 'iframe', 'nav', 'aside']:
                    elem.decompose()

    # Извлекаем текст из параграфов и заголовков
    paragraphs = content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
    text = ''

    for elem in paragraphs:
        if elem and elem.text:
            elem_text = elem.text.strip()
            if elem_text and len(elem_text) > 5:  # Уменьшил минимальную длину
                if elem.name and elem.name.startswith('h'):
                    text += '\n' + elem_text.upper() + '\n' + '=' * min(len(elem_text), 80) + '\n\n'
                else:
                    text += elem_text + '\n\n'

    return text.strip() if text else "Не удалось извлечь текст со страницы."


def extract_metadata(soup):
    """Извлечь метаданные со страницы"""
    metadata = {}

    try:
        # Заголовок
        title_elem = soup.find('h1', {'class': 'page-header__title'})
        if not title_elem:
            title_elem = soup.find('h1', {'id': 'firstHeading'})
        if not title_elem:
            title_elem = soup.find('h1')

        metadata['title'] = title_elem.text.strip() if title_elem else None

        # Описание из мета-тега
        meta_desc = soup.find('meta', {'name': 'description'})
        if not meta_desc:
            meta_desc = soup.find('meta', {'property': 'og:description'})

        if meta_desc and meta_desc.get('content'):
            metadata['description'] = meta_desc['content'].strip()

        # Категории
        categories = []
        cat_div = soup.find('div', {'class': 'page-header__categories'})
        if not cat_div:
            cat_div = soup.find('div', {'id': 'catlinks'})

        if cat_div:
            cat_links = cat_div.find_all('a')
            for cat in cat_links:
                if cat and cat.text:
                    cat_text = cat.text.strip()
                    if cat_text and not cat_text.startswith('['):
                        categories.append(cat_text)

        metadata['categories'] = categories[:10]  # Ограничиваем количество категорий

        # Дата последнего изменения
        lastmod = soup.find('li', {'id': 'footer-info-lastmod'})
        if lastmod and lastmod.text:
            metadata['last_modified'] = lastmod.text.strip()

    except Exception as e:
        print(f"Ошибка при извлечении метаданных: {e}")
        metadata['error'] = f"Ошибка метаданных: {str(e)}"

    return metadata


def download_page_with_selenium(driver, page_name, counter):
    """Скачать одну страницу с помощью Selenium с обработкой таймаутов"""
    url = f"{BASE_URL}/{page_name}"
    html_content = None
    success = False

    try:
        print(f"[{counter}/{len(PAGES_TO_DOWNLOAD)}] Скачиваю: {page_name}")
        print(f"  URL: {url}")

        # Пытаемся загрузить страницу с таймаутом
        try:
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.get(url)

            # Ждем загрузки контента, но с ограничением по времени
            wait = WebDriverWait(driver, ELEMENT_TIMEOUT)

            try:
                # Сначала ждем появления body
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                # Затем пытаемся найти основной контент
                try:
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "mw-parser-output")))
                except TimeoutException:
                    print("  Предупреждение: Основной контент не найден, продолжаем с тем что есть")

                # Даем дополнительное время для загрузки динамического контента
                time.sleep(1)

                # Получаем HTML после выполнения JavaScript
                html_content = driver.page_source
                success = True

            except TimeoutException as e:
                print(f"  Предупреждение: Таймаут ожидания элементов: {e}")
                # Пытаемся получить контент, даже если не все элементы загрузились
                if driver.page_source:
                    html_content = driver.page_source
                    success = True
                else:
                    html_content = "<html><body>Не удалось загрузить страницу</body></html>"

        except TimeoutException as e:
            print(f"  Предупреждение: Таймаут загрузки страницы: {e}")
            # Пытаемся получить то, что успело загрузиться
            try:
                html_content = driver.execute_script("return document.documentElement.outerHTML;")
                if html_content and len(html_content) > 100:
                    success = True
                    print("  Получен частично загруженный контент")
                else:
                    html_content = "<html><body>Страница не загрузилась полностью</body></html>"
            except:
                html_content = "<html><body>Ошибка получения контента</body></html>"

        except WebDriverException as e:
            print(f"  Ошибка WebDriver: {e}")
            html_content = f"<html><body>Ошибка WebDriver: {str(e)}</body></html>"

        except Exception as e:
            print(f"  Неожиданная ошибка при загрузке: {e}")
            html_content = f"<html><body>Неожиданная ошибка: {str(e)}</body></html>"

        # Сохраняем исходный HTML для диагностики
        if html_content:
            save_raw_html(page_name, html_content, counter, success)

        # Парсим HTML независимо от успешности загрузки
        soup = BeautifulSoup(html_content, 'html.parser') if html_content else BeautifulSoup("<html></html>",
                                                                                             'html.parser')

        # Извлекаем заголовок
        title_elem = soup.find('h1', {'class': 'page-header__title'})
        if not title_elem:
            title_elem = soup.find('h1')
        title = title_elem.text.strip() if title_elem else page_name

        # Извлекаем метаданные
        metadata = extract_metadata(soup)

        # Извлекаем описание
        description = extract_description(soup)

        # ЗАМЕНА ИМЕН: Применяем замену ко всем текстовым полям
        title = replace_starwars_names(title)
        description = replace_starwars_names(description)

        if metadata.get('description'):
            metadata['description'] = replace_starwars_names(metadata['description'])

        if metadata.get('categories'):
            metadata['categories'] = [replace_starwars_names(cat) for cat in metadata['categories']]

        # Используем замененное имя для имени файла, если доступно
        file_page_name = PAGE_NAME_REPLACEMENTS.get(page_name, page_name)
        filename = f"{counter:03d}_{file_page_name}.txt"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        # Добавляем информацию о статусе загрузки
        status_info = "STATUS: " + ("УСПЕШНО" if success else "ЧАСТИЧНО ЗАГРУЖЕНО")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"Original URL: {url}\n")
            f.write(f"Download Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{status_info}\n")

            if metadata.get('description'):
                f.write(f"Meta Description: {metadata['description']}\n")

            if metadata.get('categories'):
                f.write(f"Categories: {', '.join(metadata['categories'][:5])}\n")

            if metadata.get('last_modified'):
                f.write(f"Last Modified: {metadata['last_modified']}\n")

            f.write("=" * 80 + "\n\n")
            f.write(description)

        print(f"  Сохранено: {filename} ({'успешно' if success else 'частично'})")

        # Также сохраняем метаданные в JSON
        json_file = os.path.join(DOWNLOAD_DIR, f"{counter:03d}_{file_page_name}_meta.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            metadata['download_status'] = 'success' if success else 'partial'
            metadata['page_name'] = page_name
            metadata['replaced_page_name'] = file_page_name
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return success

    except Exception as e:
        print(f"  Критическая ошибка: {e}")
        import traceback
        print(f"  Трассировка: {traceback.format_exc()}")

        # Создаем файл с ошибкой
        file_page_name = PAGE_NAME_REPLACEMENTS.get(page_name, page_name)
        filename = f"{counter:03d}_{file_page_name}_ERROR.txt"
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


def save_raw_html(page_name, html_content, counter, success):
    """Сохранить исходный HTML для диагностики"""
    html_dir = os.path.join(DOWNLOAD_DIR, "raw_html")
    if not os.path.exists(html_dir):
        os.makedirs(html_dir)

    status = "success" if success else "partial"
    html_file = os.path.join(html_dir, f"{counter:03d}_{page_name}_{status}.html")

    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  Сохранен исходный HTML: {html_file}")
    except Exception as e:
        print(f"  Ошибка сохранения HTML: {e}")


def main():
    """Основная функция"""
    # Создаем директорию
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    print(f"Скачиваю {len(PAGES_TO_DOWNLOAD)} страниц со Star Wars Wiki...")
    print(f"Таймауты: загрузка={PAGE_LOAD_TIMEOUT}с, элементы={ELEMENT_TIMEOUT}с")
    print("Примечание: Имена персонажей Star Wars будут заменены на обычные имена.")

    # Настраиваем драйвер
    driver = None
    successful = 0
    partial = 0
    failed = 0

    try:
        driver = setup_driver()

        for i, page in enumerate(PAGES_TO_DOWNLOAD, 1):
            result = download_page_with_selenium(driver, page, i)

            if result:
                successful += 1
            else:
                # Проверяем, есть ли файл с ошибкой
                file_page_name = PAGE_NAME_REPLACEMENTS.get(page, page)
                error_file = os.path.join(DOWNLOAD_DIR, f"{i:03d}_{file_page_name}_ERROR.txt")
                if os.path.exists(error_file):
                    failed += 1
                else:
                    partial += 1

            # Задержка между запросами
            if i < len(PAGES_TO_DOWNLOAD):
                time.sleep(REQUEST_DELAY)

    except Exception as e:
        print(f"\nОшибка в основном цикле: {e}")
        import traceback
        print(f"Трассировка: {traceback.format_exc()}")

    finally:
        # Всегда закрываем драйвер
        if driver:
            try:
                driver.quit()
                print("\nДрайвер закрыт.")
            except:
                pass

    print(f"\nГотово! Итоги скачивания:")
    print(f"  Успешно: {successful}/{len(PAGES_TO_DOWNLOAD)}")
    print(f"  Частично: {partial}/{len(PAGES_TO_DOWNLOAD)}")
    print(f"  Ошибки: {failed}/{len(PAGES_TO_DOWNLOAD)}")
    print(f"Файлы сохранены в: {os.path.abspath(DOWNLOAD_DIR)}")

    # Выводим примеры замен
    print("\nПримеры замен имен:")
    print("  Luke Skywalker → Jack Thompson")
    print("  Darth Vader → Victor Darkwood")
    print("  Princess Leia → Leah Preston")
    print("  Jedi → Guardians")

    # Создаем индексный файл
    index_file = os.path.join(DOWNLOAD_DIR, "INDEX.txt")
    try:
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write("Индекс скачанных страниц Star Wars Wiki\n")
            f.write(f"Дата создания: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("ПРИМЕЧАНИЕ: Имена персонажей заменены на обычные имена\n")
            f.write("=" * 60 + "\n\n")

            f.write("Статистика:\n")
            f.write(f"  Всего страниц: {len(PAGES_TO_DOWNLOAD)}\n")
            f.write(f"  Успешно скачано: {successful}\n")
            f.write(f"  Частично скачано: {partial}\n")
            f.write(f"  Ошибки: {failed}\n\n")

            f.write("Список страниц:\n")
            for i, page in enumerate(PAGES_TO_DOWNLOAD, 1):
                replaced_name = PAGE_NAME_REPLACEMENTS.get(page, page)
                file_page_name = PAGE_NAME_REPLACEMENTS.get(page, page)

                # Проверяем статус файла
                txt_file = os.path.join(DOWNLOAD_DIR, f"{i:03d}_{file_page_name}.txt")
                error_file = os.path.join(DOWNLOAD_DIR, f"{i:03d}_{file_page_name}_ERROR.txt")

                if os.path.exists(error_file):
                    status = "[ОШИБКА]"
                elif os.path.exists(txt_file):
                    # Проверяем содержимое на статус
                    try:
                        with open(txt_file, 'r', encoding='utf-8') as tf:
                            content = tf.read(100)
                            if "STATUS: УСПЕШНО" in content:
                                status = "[OK]"
                            elif "STATUS: ЧАСТИЧНО" in content:
                                status = "[ЧАСТИЧНО]"
                            else:
                                status = "[?]"
                    except:
                        status = "[ФАЙЛ]"
                else:
                    status = "[НЕТ]"

                f.write(f"{i:03d}. {page} → {replaced_name} {status}\n")

            f.write("\nСловарь замен:\n")
            for original, replacement in CHARACTER_REPLACEMENTS.items():
                f.write(f"  {original} → {replacement}\n")

        print(f"\nИндексный файл создан: {index_file}")

    except Exception as e:
        print(f"Ошибка создания индексного файла: {e}")


if __name__ == "__main__":
    main()