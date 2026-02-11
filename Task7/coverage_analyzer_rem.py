import json
from typing import Dict, List, Set
from collections import defaultdict

# Список основных тем, которые должны быть в базе
REQUIRED_TOPICS = {
    "basic_concepts": [
        "определение квантовой биозоологии",
        "основные принципы",
        "история развития",
        "основатель"
    ],
    "phenomena": [
        "эффект Вейра",
        "квантовый компас",
        "реакция Ту-Шена",
        "феномен призрачной стаи",
        "зооквантовый шум"
    ],
    "species": [
        "сереброкрылая ласточка",
        "подвид альбиноса",
        "мигрирующие виды",
        "моллюски с арагонитом"
    ],
    "methods": [
        "протокол Энтэнгель",
        "энтэнглометр",
        "эксперимент Хорус-2026",
        "модель Вейра-Ковальского"
    ],
    "applications": [
        "биокомпьютинг",
        "квантовая эпидемиология",
        "экзобиология",
        "экономическое применение"
    ],
    "ethics": [
        "кодекс этики",
        "экспериментальные ограничения",
        "проблемы экспериментов",
        "гуманное обращение"
    ],
    "criticism": [
        "возражения классической этологии",
        "научные споры",
        "доказательная база"
    ],
    "future": [
        "проект Арка",
        "будущие исследования",
        "технологические перспективы"
    ]
}


class CoverageAnalyzer:
    def __init__(self, document_files: List[str]):
        self.document_files = document_files
        self.topics_coverage = defaultdict(set)
        self.gaps = []

    def analyze_documents(self):
        """Анализирует документы на покрытие тем"""
        all_text = ""

        # Читаем все документы
        for doc_file in self.document_files:
            try:
                with open(doc_file, 'r', encoding='utf-8') as f:
                    all_text += f.read().lower() + "\n"
            except Exception as e:
                print(f"Ошибка чтения {doc_file}: {e}")

        # Проверяем покрытие тем
        for category, topics in REQUIRED_TOPICS.items():
            covered_in_category = 0

            for topic in topics:
                topic_words = topic.lower().split()
                found = False

                # Проверяем по ключевым словам темы
                for word in topic_words:
                    if len(word) > 3 and word in all_text:
                        found = True
                        break

                if found:
                    covered_in_category += 1
                    self.topics_coverage[category].add(topic)
                else:
                    self.gaps.append({
                        'category': category,
                        'topic': topic,
                        'severity': 'high' if category in ['basic_concepts', 'phenomena'] else 'medium'
                    })

            coverage_rate = (covered_in_category / len(topics)) * 100
            print(f"{category}: {covered_in_category}/{len(topics)} ({coverage_rate:.1f}%)")

    def generate_gap_report(self) -> Dict:
        """Генерирует отчет о пробелах"""
        if not self.gaps:
            return {"status": "complete", "message": "Все основные темы покрыты"}

        # Группируем пробелы по категориям
        gaps_by_category = defaultdict(list)
        for gap in self.gaps:
            gaps_by_category[gap['category']].append(gap)

        report = {
            "total_gaps": len(self.gaps),
            "gaps_by_severity": {
                "high": [g for g in self.gaps if g['severity'] == 'high'],
                "medium": [g for g in self.gaps if g['severity'] == 'medium'],
                "low": [g for g in self.gaps if g['severity'] == 'low']
            },
            "gaps_by_category": gaps_by_category,
            "recommendations": []
        }

        # Рекомендации по заполнению пробелов
        if report["gaps_by_severity"]["high"]:
            report["recommendations"].append(
                "Добавить документы по основным концепциям и феноменам (высокий приоритет)"
            )

        if any(gap['category'] == 'applications' for gap in self.gaps):
            report["recommendations"].append(
                "Расширить раздел о практических применениях"
            )

        if any(gap['category'] == 'future' for gap in self.gaps):
            report["recommendations"].append(
                "Добавить информацию о будущих исследованиях и проектах"
            )

        return report

    def save_report(self, output_file: str = "coverage_report.json"):
        """Сохраняет отчет в файл"""
        report = {
            "analysis_date": "2024-01-20",
            "total_documents": len(self.document_files),
            "coverage_by_category": {
                cat: {
                    "covered": len(topics),
                    "total": len(REQUIRED_TOPICS[cat]),
                    "percentage": (len(topics) / len(REQUIRED_TOPICS[cat])) * 100
                }
                for cat, topics in self.topics_coverage.items()
            },
            "gaps": self.gaps,
            "recommendations": self.generate_gap_report()["recommendations"]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n📋 Отчет о покрытии сохранен в {output_file}")
        return report


def main():
    """Основная функция анализа"""
    # Получаем список текстовых файлов с документами
    import glob
    document_files = glob.glob("*.txt")

    print("📚 Анализ покрытия базы знаний")
    print(f"Найдено документов: {len(document_files)}")

    analyzer = CoverageAnalyzer(document_files)
    analyzer.analyze_documents()

    report = analyzer.save_report()

    # Выводим основные выводы
    print("\n🎯 ВЫВОДЫ:")
    print(f"Всего пробелов: {report['total_gaps']}")

    if report["gaps"]:
        print("Критические пробелы:")
        for gap in report["gaps"][:5]:  # Показываем первые 5
            print(f"  • {gap['topic']} ({gap['category']})")

    print("\n📈 РЕКОМЕНДАЦИИ:")
    for rec in report["recommendations"][:3]:
        print(f"  • {rec}")


if __name__ == "__main__":
    main()