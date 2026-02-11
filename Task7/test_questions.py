# test_questions.py
import os
from typing import List, Dict, Any


def load_questions_from_file(filename: str = "golden_questions.txt") -> Dict[str, List[Dict[str, Any]]]:
    """
    Загружает вопросы из конфигурационного файла.

    Формат файла:
    - Строки, начинающиеся с '#' - комментарии (названия категорий)
    - '---' разделитель между вопросами
    - Каждый вопрос содержит поля: question, expected_keywords, difficulty,
      category, опционально should_fail
    - expected_keywords: строка с ключевыми словами через запятую
    """

    questions = {
        "known_topics": [],
        "unknown_topics": [],
        "edge_cases": []
    }

    current_category = None

    # Определяем соответствие комментариев категориям
    category_map = {
        "known_topics": "known_topics",
        "unknown_topics": "unknown_topics",
        "edge_cases": "edge_cases"
    }

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        # Если файл не найден, пробуем другие пути
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Конфигурационный файл {filename} не найден")

    # Разбиваем на блоки вопросов
    blocks = content.strip().split('---')

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split('\n')

        # Проверяем, является ли блок комментарием-категорией
        if lines[0].startswith('#'):
            category_comment = lines[0][1:].strip().lower()
            # Определяем категорию по комментарию
            if "known" in category_comment:
                current_category = "known_topics"
            elif "unknown" in category_comment:
                current_category = "unknown_topics"
            elif "edge" in category_comment or "пограничные" in category_comment:
                current_category = "edge_cases"
            continue

        # Парсим вопрос
        question_data = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                if key == 'expected_keywords':
                    # Преобразуем строку с ключевыми словами в список
                    question_data[key] = [kw.strip() for kw in value.split(',') if kw.strip()]
                elif key == 'should_fail':
                    # Преобразуем строку в булево значение
                    question_data[key] = value.lower() == 'true'
                elif key == 'difficulty':
                    question_data[key] = value
                else:
                    question_data[key] = value

        # Добавляем вопрос в соответствующую категорию
        if question_data and current_category:
            questions[current_category].append(question_data)

    return questions


# Загружаем вопросы при импорте модуля
GOLDEN_QUESTIONS = load_questions_from_file()


def get_all_questions() -> List[Dict[str, Any]]:
    """Возвращает все вопросы из всех категорий"""
    all_questions = []
    for category in GOLDEN_QUESTIONS.values():
        all_questions.extend(category)
    return all_questions


def get_questions_by_category(category_name: str) -> List[Dict[str, Any]]:
    """Возвращает вопросы по категории"""
    return GOLDEN_QUESTIONS.get(category_name, [])


def get_question_statistics() -> Dict[str, Dict[str, Any]]:
    """Статистика по вопросам"""
    stats = {}
    for category, questions in GOLDEN_QUESTIONS.items():
        stats[category] = {
            'count': len(questions),
            'difficulty_distribution': {
                'easy': len([q for q in questions if q.get('difficulty') == 'easy']),
                'medium': len([q for q in questions if q.get('difficulty') == 'medium']),
                'hard': len([q for q in questions if q.get('difficulty') == 'hard']),
                'unknown': len([q for q in questions if q.get('difficulty') == 'unknown'])
            }
        }
    return stats


def reload_questions(filename: str = "golden_questions.txt") -> None:
    """Перезагружает вопросы из файла конфигурации"""
    global GOLDEN_QUESTIONS
    GOLDEN_QUESTIONS = load_questions_from_file(filename)