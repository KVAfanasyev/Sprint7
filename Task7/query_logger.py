# query_logger.py
import csv
import os
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd


class QueryLogger:
    def __init__(self, log_file: str = "query_log.csv"):
        self.log_file = log_file
        self._ensure_log_file_exists()

    def _ensure_log_file_exists(self):
        """Создаем файл лога с заголовками, если его нет"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', newline='', encoding='cp1251') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'query',
                    'found_chunks',
                    'answer_length',
                    'is_successful',
                    'sources',
                    'response_time',
                    'rag_mode',
                    'security_blocks'
                ])

    def log_query(self,
                  query: str,
                  found_chunks: bool,
                  answer_length: int,
                  is_successful: bool,
                  sources: List[str],
                  response_time: float,
                  rag_mode: bool = True,
                  security_blocks: int = 0):
        """Логирует запрос и результат"""
        timestamp = datetime.now().isoformat()

        # Преобразуем источники в строку
        sources_str = ' '.join(sources) if sources else ''

        with open(self.log_file, 'a', newline='', encoding='cp1251') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                query[:500],  # Ограничиваем длину запроса
                found_chunks,
                answer_length,
                is_successful,
                sources_str,
                round(response_time, 2),
                rag_mode,
                security_blocks
            ])

    def get_stats(self) -> Dict:
        """Возвращает статистику по логам"""
        if not os.path.exists(self.log_file):
            return {}

        try:
            df = pd.read_csv(self.log_file, encoding='cp1251')
            if df.empty:
                return {}

            return {
                'total_queries': len(df),
                'success_rate': df['is_successful'].mean() * 100,
                'avg_response_time': df['response_time'].mean(),
                'avg_answer_length': df['answer_length'].mean(),
                'top_queries': df['query'].value_counts().head(10).to_dict(),
                'common_sources': df['sources'].str.split(';').explode().value_counts().head(5).to_dict()
            }
        except Exception as e:
            print(f"Ошибка при чтении статистики: {e}")
            return {}

    def export_to_excel(self, output_file: str = "query_log_analysis.xlsx"):
        """Экспортирует логи и статистику в Excel"""
        if not os.path.exists(self.log_file):
            return False

        try:
            df = pd.read_csv(self.log_file)

            # Создаем Excel writer
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # Основные логи
                df.to_excel(writer, sheet_name='Logs', index=False)

                # Статистика
                stats = {
                    'Metric': [
                        'Total Queries',
                        'Success Rate (%)',
                        'Avg Response Time (s)',
                        'Avg Answer Length',
                        'RAG Mode Queries',
                        'Failed Queries'
                    ],
                    'Value': [
                        len(df),
                        df['is_successful'].mean() * 100,
                        df['response_time'].mean(),
                        df['answer_length'].mean(),
                        df['rag_mode'].sum(),
                        len(df[df['is_successful'] == False])
                    ]
                }
                pd.DataFrame(stats).to_excel(writer, sheet_name='Statistics', index=False)

                # Распределение по времени
                df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
                hourly_stats = df.groupby('hour').size().reset_index(name='count')
                hourly_stats.to_excel(writer, sheet_name='Hourly Distribution', index=False)

            return True
        except Exception as e:
            print(f"Ошибка при экспорте в Excel: {e}")
            return False