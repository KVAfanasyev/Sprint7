import asyncio
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

# Добавляем путь к текущей директории для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем необходимые компоненты
from RAGBot import chroma_search, rag_pipeline, security_layer, SECURITY_CONFIG
from test_questions import get_all_questions, GOLDEN_QUESTIONS


class RAGTester:
    def __init__(self, output_file: str = "test_results.csv"):
        self.output_file = output_file
        self.results = []
        self.summary = {}

    def _check_answer_quality(self, answer: str, expected_keywords: List[str]) -> Dict:
        """Оценивает качество ответа"""
        if not answer or len(answer.strip()) < 10:
            return {
                'score': 0,
                'coverage': 0,
                'keywords_found': [],
                'is_empty': True
            }

        answer_lower = answer.lower()
        found_keywords = []

        for keyword in expected_keywords:
            if keyword.lower() in answer_lower:
                found_keywords.append(keyword)

        coverage = len(found_keywords) / len(expected_keywords) if expected_keywords else 0

        # Простая оценка
        score = 0
        if len(answer) > 50:  # Непустой ответ
            score += 1
        if coverage > 0.3:  # Хотя бы часть ключевых слов
            score += 1
        if coverage > 0.6:  # Большая часть ключевых слов
            score += 1
        if len(answer) > 200 and coverage > 0.5:  # Развернутый и релевантный
            score += 1

        return {
            'score': min(score, 4),  # Максимум 4 балла
            'coverage': round(coverage * 100, 1),  # В процентах
            'keywords_found': found_keywords,
            'keywords_missing': [k for k in expected_keywords if k.lower() not in answer_lower],
            'is_empty': False
        }

    async def test_question(self, question_data: Dict) -> Dict:
        """Тестирует один вопрос"""
        query = question_data['question']
        expected_keywords = question_data.get('expected_keywords', [])
        category = question_data.get('category', 'unknown')
        difficulty = question_data.get('difficulty', 'medium')
        should_fail = question_data.get('should_fail', False)

        print(f"\n{'=' * 60}")
        print(f"Тестируем: {query}")
        print(f"Категория: {category}, Сложность: {difficulty}")
        print(f"Ожидаемые ключевые слова: {expected_keywords}")
        print(f"{'=' * 60}")

        start_time = datetime.now()

        try:
            # Выполняем поиск
            search_results = chroma_search.search(query, n_results=3)

            if not search_results or not search_results['documents']:
                answer = "Информация не найдена"
                quality = self._check_answer_quality(answer, expected_keywords)
                result = {
                    'question': query,
                    'category': category,
                    'difficulty': difficulty,
                    'answer': answer,
                    'answer_length': len(answer),
                    'found_chunks': False,
                    'search_successful': False,
                    'quality_score': quality['score'],
                    'coverage_percent': quality['coverage'],
                    'keywords_found': ', '.join(quality['keywords_found']),
                    'keywords_missing': ', '.join(quality['keywords_missing']),
                    'sources': '',
                    'response_time_ms': 0,
                    'is_expected_to_fail': should_fail,
                    'test_passed': False,
                    'notes': 'Информация не найдена в базе'
                }

                print(f"❌ Информация не найдена")
                return result

            # Генерируем ответ через RAG
            rag_response = rag_pipeline.generate_enhanced_response(
                query=query,
                search_results=search_results,
                use_rag=True
            )

            answer = rag_response.get('answer', 'Нет ответа')
            sources = rag_response.get('sources', [])
            response_time = datetime.now().timestamp() - start_time.timestamp()

            # Оцениваем качество
            quality = self._check_answer_quality(answer, expected_keywords)

            # Определяем, прошел ли тест
            test_passed = True
            notes = ''

            if should_fail:
                # Для вопросов, где ожидаем неудачу
                if quality['coverage'] > 30:  # Если нашел слишком много
                    test_passed = False
                    notes = 'Найдено больше информации, чем ожидалось для отсутствующей темы'
                else:
                    test_passed = True
                    notes = 'Корректно не ответил на отсутствующую тему'
            else:
                # Для вопросов, где ожидаем ответ
                if quality['coverage'] < 40:  # Мало ключевых слов
                    test_passed = False
                    notes = f'Низкое покрытие тем: {quality["coverage"]}%'
                elif len(answer) < 30:  # Слишком короткий ответ
                    test_passed = False
                    notes = 'Ответ слишком короткий'
                else:
                    test_passed = True
                    notes = 'Ответ удовлетворительный'

            result = {
                'question': query,
                'category': category,
                'difficulty': difficulty,
                'answer': answer[:500] + '...' if len(answer) > 500 else answer,
                'answer_length': len(answer),
                'found_chunks': True,
                'search_successful': True,
                'quality_score': quality['score'],
                'coverage_percent': quality['coverage'],
                'keywords_found': ', '.join(quality['keywords_found']),
                'keywords_missing': ', '.join(quality['keywords_missing']),
                'sources': ', '.join(sources[:3]),
                'response_time_ms': round(response_time * 1000, 2),
                'is_expected_to_fail': should_fail,
                'test_passed': test_passed,
                'notes': notes
            }

            # Выводим результат
            if test_passed:
                print(f"✅ Тест пройден | Оценка: {quality['score']}/4 | Покрытие: {quality['coverage']}%")
            else:
                print(f"❌ Тест не пройден | Оценка: {quality['score']}/4 | Покрытие: {quality['coverage']}%")

            print(f"Найдено ключевых слов: {len(quality['keywords_found'])}/{len(expected_keywords)}")
            print(f"Источники: {', '.join(sources[:3]) if sources else 'нет'}")

            return result

        except Exception as e:
            print(f"⚠️ Ошибка при тестировании: {e}")
            return {
                'question': query,
                'category': category,
                'difficulty': difficulty,
                'answer': f'Ошибка: {str(e)}',
                'answer_length': 0,
                'found_chunks': False,
                'search_successful': False,
                'quality_score': 0,
                'coverage_percent': 0,
                'keywords_found': '',
                'keywords_missing': ', '.join(expected_keywords),
                'sources': '',
                'response_time_ms': 0,
                'is_expected_to_fail': should_fail,
                'test_passed': False,
                'notes': f'Ошибка выполнения: {str(e)}'
            }

    async def run_all_tests(self):
        """Запускает все тесты"""
        print("🚀 Начинаю автоматическое тестирование RAG-бота")
        print(f"Всего вопросов: {len(get_all_questions())}")

        all_questions = get_all_questions()

        for i, question_data in enumerate(all_questions, 1):
            print(f"\n📋 Вопрос {i}/{len(all_questions)}")
            result = await self.test_question(question_data)
            self.results.append(result)

            # Небольшая пауза между запросами
            await asyncio.sleep(0.5)

        # Анализируем результаты
        self._analyze_results()

        # Сохраняем результаты
        self._save_results()

        print("\n" + "=" * 60)
        print("🎯 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        print("=" * 60)
        self._print_summary()

    def _analyze_results(self):
        """Анализирует результаты тестирования"""
        if not self.results:
            return

        df = pd.DataFrame(self.results)

        # Общая статистика
        total_questions = len(df)
        passed_tests = df['test_passed'].sum()
        pass_rate = (passed_tests / total_questions) * 100

        # Статистика по категориям
        category_stats = {}
        for category in df['category'].unique():
            cat_df = df[df['category'] == category]
            cat_total = len(cat_df)
            cat_passed = cat_df['test_passed'].sum()
            cat_avg_score = cat_df['quality_score'].mean()
            cat_avg_coverage = cat_df['coverage_percent'].mean()

            category_stats[category] = {
                'total': cat_total,
                'passed': cat_passed,
                'pass_rate': (cat_passed / cat_total) * 100 if cat_total > 0 else 0,
                'avg_score': round(cat_avg_score, 2),
                'avg_coverage': round(cat_avg_coverage, 2)
            }

        # Статистика по сложности
        difficulty_stats = {}
        for difficulty in df['difficulty'].unique():
            diff_df = df[df['difficulty'] == difficulty]
            diff_total = len(diff_df)
            diff_passed = diff_df['test_passed'].sum()

            difficulty_stats[difficulty] = {
                'total': diff_total,
                'passed': diff_passed,
                'pass_rate': (diff_passed / diff_total) * 100 if diff_total > 0 else 0
            }

        # Проблемные вопросы
        failed_questions = df[~df['test_passed']][['question', 'category', 'coverage_percent', 'notes']]

        self.summary = {
            'total_questions': total_questions,
            'passed_tests': int(passed_tests),
            'pass_rate': round(pass_rate, 2),
            'avg_quality_score': round(df['quality_score'].mean(), 2),
            'avg_coverage': round(df['coverage_percent'].mean(), 2),
            'category_stats': category_stats,
            'difficulty_stats': difficulty_stats,
            'failed_questions': failed_questions.to_dict('records'),
            'top_scoring_questions': df.nlargest(5, 'quality_score')[['question', 'quality_score']].to_dict('records'),
            'worst_scoring_questions': df.nsmallest(5, 'quality_score')[['question', 'quality_score']].to_dict(
                'records')
        }

    def _save_results(self):
        """Сохраняет результаты в CSV и JSON"""
        if not self.results:
            return

        # Сохраняем в CSV
        df = pd.DataFrame(self.results)
        df.to_csv(self.output_file, index=False, encoding='cp1251')
        print(f"\n📊 Результаты сохранены в: {self.output_file}")

        # Сохраняем сводку в JSON
        summary_file = self.output_file.replace('.csv', '_summary.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(self.summary, f, ensure_ascii=False, indent=2)
        print(f"📋 Сводка сохранена в: {summary_file}")

        # Создаем Excel отчет
        excel_file = self.output_file.replace('.csv', '_report.xlsx')
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            # Детальные результаты
            df.to_excel(writer, sheet_name='Detailed Results', index=False)

            # Сводка по категориям
            cat_summary = pd.DataFrame([
                {
                    'Category': cat,
                    'Total': stats['total'],
                    'Passed': stats['passed'],
                    'Pass Rate (%)': stats['pass_rate'],
                    'Avg Score': stats['avg_score'],
                    'Avg Coverage (%)': stats['avg_coverage']
                }
                for cat, stats in self.summary['category_stats'].items()
            ])
            cat_summary.to_excel(writer, sheet_name='Category Summary', index=False)

            # Проблемные вопросы
            if self.summary['failed_questions']:
                failed_df = pd.DataFrame(self.summary['failed_questions'])
                failed_df.to_excel(writer, sheet_name='Failed Questions', index=False)

        print(f"📈 Excel отчет создан: {excel_file}")

    def _print_summary(self):
        """Выводит сводку результатов"""
        if not self.summary:
            print("Нет результатов для отображения")
            return

        print(f"\n📊 СВОДКА РЕЗУЛЬТАТОВ")
        print(f"Всего вопросов: {self.summary['total_questions']}")
        print(f"Пройдено тестов: {self.summary['passed_tests']}")
        print(f"Успешность: {self.summary['pass_rate']}%")
        print(f"Средняя оценка качества: {self.summary['avg_quality_score']}/4")
        print(f"Среднее покрытие тем: {self.summary['avg_coverage']}%")

        print(f"\n📈 ПО КАТЕГОРИЯМ:")
        for category, stats in self.summary['category_stats'].items():
            print(f"  {category}: {stats['passed']}/{stats['total']} ({stats['pass_rate']}%)")

        print(f"\n📉 ПО СЛОЖНОСТИ:")
        for difficulty, stats in self.summary['difficulty_stats'].items():
            print(f"  {difficulty}: {stats['passed']}/{stats['total']} ({stats['pass_rate']}%)")

        if self.summary['failed_questions']:
            print(f"\n⚠️ ПРОБЛЕМНЫЕ ВОПРОСЫ ({len(self.summary['failed_questions'])}):")
            for question in self.summary['failed_questions'][:5]:  # Первые 5
                print(f"  • {question['question'][:60]}... (покрытие: {question['coverage_percent']}%)")


async def main():
    """Основная функция тестирования"""
    print("🤖 Автоматический тестер RAG-бота")
    print("=" * 60)

    # Проверяем доступность компонентов
    if chroma_search.collection is None:
        print("❌ ОШИБКА: Векторный индекс не загружен!")
        print("Сначала запустите CreateVectorIndex.py")
        return

    if not rag_pipeline.available_models:
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: LLM не доступна. Тестирование будет в простом режиме.")

    print(f"✅ Векторный индекс загружен")
    print(f"✅ Система безопасности: {'ВКЛЮЧЕНА' if SECURITY_CONFIG['enable_preprompt_protection'] else 'ВЫКЛЮЧЕНА'}")
    print(f"✅ Доступно моделей LLM: {len(rag_pipeline.available_models) if rag_pipeline.available_models else 0}")

    # Запускаем тестирование
    tester = RAGTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())