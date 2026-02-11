import os
import json
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import hashlib
import time

from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb


# Альтернативный вариант с ChromaDB (проще в использовании)
class ChromaIndexCreator:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        self.model_name = model_name
        self.embedding_function = SentenceTransformerEmbeddingFunction(model_name=model_name)
        self.client = chromadb.PersistentClient(path="./chroma_db")

    def create_index(self, knowledge_base_dir: str, collection_name: str = "knowledge_base"):
        """
        Создает индекс в ChromaDB
        """
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        start_time = time.time()

        # Создаем или получаем коллекцию
        collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}  # Используем косинусное расстояние
        )

        # Обрабатываем файлы
        text_extensions = {'.txt', '.md', '.rst', '.text'}

        # Размер батча для добавления в ChromaDB (меньше лимита)
        batch_size = 1000  # Можно установить 1000, 2000, 3000 и т.д., но меньше 5461

        all_documents = []
        all_metadatas = []
        all_ids = []

        total_documents_added = 0
        total_files_processed = 0

        for file_path in Path(knowledge_base_dir).rglob('*'):
            if file_path.suffix.lower() in text_extensions:
                print(f"Обработка файла: {file_path}")
                total_files_processed += 1

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Разбиваем на чанки
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=500,
                    chunk_overlap=50,
                    length_function=len
                )
                chunks = text_splitter.split_text(content)

                # Добавляем в временные списки
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{file_path.stem}_{i}"
                    all_ids.append(chunk_id)
                    all_documents.append(chunk)
                    all_metadatas.append({
                        "source": str(file_path),
                        "chunk_index": i,
                        "file_name": file_path.name,
                        "total_chunks": len(chunks)
                    })

                    # Добавляем батч, когда достигли batch_size
                    if len(all_documents) >= batch_size:
                        collection.add(
                            documents=all_documents,
                            metadatas=all_metadatas,
                            ids=all_ids
                        )
                        total_documents_added += len(all_documents)
                        print(f"Добавлено {len(all_documents)} документов (всего: {total_documents_added})")

                        # Очищаем списки для следующего батча
                        all_documents = []
                        all_metadatas = []
                        all_ids = []

        # Добавляем оставшиеся документы (последний батч)
        if all_documents:
            collection.add(
                documents=all_documents,
                metadatas=all_metadatas,
                ids=all_ids
            )
            total_documents_added += len(all_documents)
            print(f"Добавлено {len(all_documents)} документов (всего: {total_documents_added})")

        end_time = time.time()
        generation_time = end_time - start_time

        # Выводим статистику
        print(f"\n=== ИНФОРМАЦИЯ О СОЗДАНИИ ИНДЕКСА ===")
        print(f"Использованная модель: {self.model_name}")
        print(f"База знаний: {knowledge_base_dir}")
        print(f"Обработано файлов: {total_files_processed}")
        print(f"Всего чанков в индексе: {total_documents_added}")
        print(f"Время генерации: {generation_time:.2f} секунд ({generation_time / 60:.2f} минут)")
        print(f"Скорость обработки: {total_documents_added / generation_time:.2f} чанков/сек")
        print(f"===============================\n")

        print(f"Создана коллекция '{collection_name}' с {total_documents_added} документами")
        return collection, {
            "model": self.model_name,
            "knowledge_base": knowledge_base_dir,
            "total_chunks": total_documents_added,
            "total_files": total_files_processed,
            "generation_time_seconds": generation_time,
            "generation_time_minutes": generation_time / 60
        }


def main():
    """
    Основная функция для создания векторного индекса
    """
    # Конфигурация
    KNOWLEDGE_BASE_DIR = "./warm_pages/themes"  # Директория с текстовыми файлами
    OUTPUT_DIR = "./vector_index"
    MODEL_NAME = "all-MiniLM-L6-v2"

    # Вариант: ChromaDB
    print("\n=== Создание индекса с ChromaDB ===")
    print(f"Начало создания индекса в: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    chroma_creator = ChromaIndexCreator(model_name=MODEL_NAME)
    collection, stats = chroma_creator.create_index(KNOWLEDGE_BASE_DIR)

    print(f"\nЗавершено создание индекса в: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Сохраняем статистику в файл
    stats_file = "./index_creation_stats.json"
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"Статистика сохранена в файл: {stats_file}")


if __name__ == "__main__":
    main()