"""
Скрипт автоматического обновления векторного индекса
Автоматически находит новые/измененные файлы, обновляет базу знаний и логирует процесс
"""

import os
import json
import hashlib
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set
import sys

# Импорты для работы с векторной БД
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ConfigLoader:
    """Класс для загрузки и управления конфигурацией"""

    DEFAULT_CONFIG = {
        "knowledge_base": {
            "source_dir": "./warm_pages/themes",
            "extensions": [".txt", ".md", ".rst", ".text", ".json", ".py"]
        },
        "vector_index": {
            "collection_name": "knowledge_base",
            "db_path": "./chroma_db",
            "model_name": "all-MiniLM-L6-v2"
        },
        "update_settings": {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "batch_size": 1000,
            "check_interval_minutes": 1440  # 24 часа
        },
        "scheduler": {
            "enabled": True,
            "schedule": "0 6 * * *",
            "timezone": "Europe/Moscow"
        },
        "logging": {
            "log_file": "./update_index.log",
            "max_size_mb": 10,
            "backup_count": 5,
            "level": "INFO",
            "console_output": True
        },
        "state_files": {
            "state_file": "./index_state.json",
            "stats_file": "./update_stats.json",
            "last_run_file": "./last_run.json"
        }
    }

    def __init__(self, config_path: str = "./config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из файла или создание по умолчанию"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)

                # Рекурсивное объединение конфигураций
                config = self._merge_configs(self.DEFAULT_CONFIG.copy(), user_config)
                print(f"✅ Конфигурация загружена из {self.config_path}")
                return config

            except Exception as e:
                print(f"⚠️ Ошибка загрузки конфигурации: {e}. Использую значения по умолчанию")
                return self.DEFAULT_CONFIG.copy()
        else:
            # Создаем файл конфигурации по умолчанию
            self._create_default_config()
            print(f"📁 Создан файл конфигурации по умолчанию: {self.config_path}")
            return self.DEFAULT_CONFIG.copy()

    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Рекурсивное объединение конфигураций"""
        for key, value in user.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                default[key] = self._merge_configs(default[key], value)
            else:
                default[key] = value
        return default

    def _create_default_config(self):
        """Создание конфигурационного файла по умолчанию"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка создания файла конфигурации: {e}")

    def get(self, key_path: str, default=None) -> Any:
        """Получение значения из конфигурации по пути"""
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def save(self):
        """Сохранение текущей конфигурации в файл"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"✅ Конфигурация сохранена в {self.config_path}")
        except Exception as e:
            print(f"❌ Ошибка сохранения конфигурации: {e}")


class VectorIndexUpdater:
    """
    Класс для автоматического обновления векторного индекса
    """

    def __init__(self, config: ConfigLoader = None):
        # Загружаем конфигурацию
        self.config = config if config else ConfigLoader()

        # Извлекаем параметры из конфигурации
        self.knowledge_base_dir = Path(self.config.get("knowledge_base.source_dir"))
        self.collection_name = self.config.get("vector_index.collection_name")
        self.model_name = self.config.get("vector_index.model_name")
        self.db_path = self.config.get("vector_index.db_path")

        # Настройки обновления
        self.chunk_size = self.config.get("update_settings.chunk_size", 500)
        self.chunk_overlap = self.config.get("update_settings.chunk_overlap", 50)
        self.batch_size = self.config.get("update_settings.batch_size", 1000)

        # Файлы состояния
        self.state_file = self.config.get("state_files.state_file")
        self.stats_file = self.config.get("state_files.stats_file")
        self.last_run_file = self.config.get("state_files.last_run_file")

        # Настройка логирования
        self._setup_logging()

        # Инициализация ChromaDB
        self._init_chromadb()

        # Загрузка состояния предыдущего индекса
        self.state = self._load_state()

    def _setup_logging(self):
        """Настройка системы логирования на основе конфигурации"""
        log_file = self.config.get("logging.log_file", "./update_index.log")
        log_level = self.config.get("logging.level", "INFO")
        console_output = self.config.get("logging.console_output", True)

        # Преобразуем строку уровня логирования в константу
        level_mapping = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        log_level = level_mapping.get(log_level.upper(), logging.INFO)

        # Создаем директорию для логов, если она не существует
        log_path = Path(log_file)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # Если не удалось создать директорию, используем текущую
            print(f"⚠️ Не удалось создать директорию для логов: {e}")
            log_file = "./update_index.log"

        # Настройка логгера
        handlers = []

        # Файловый обработчик
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            handlers.append(file_handler)
        except Exception as e:
            print(f"⚠️ Не удалось создать файловый обработчик логов: {e}")
            # Если не удалось создать файловый обработчик, используем только консольный

        # Консольный обработчик (если включен)
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            handlers.append(console_handler)

        # Если нет обработчиков, создаем хотя бы консольный
        if not handlers:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            handlers.append(console_handler)

        logging.basicConfig(
            level=log_level,
            handlers=handlers
        )
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"Логирование настроено. Уровень: {log_level}, Файл: {log_file}")


    def _init_chromadb(self):
        """Инициализация ChromaDB на основе конфигурации"""
        try:
            self.client = chromadb.PersistentClient(path=self.db_path)
            self.embedding_function = SentenceTransformerEmbeddingFunction(
                model_name=self.model_name
            )
            self.logger.info(f"ChromaDB инициализирована. Путь: {self.db_path}, модель: {self.model_name}")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации ChromaDB: {e}")
            raise

    def _load_state(self) -> Dict[str, Any]:
        """Загрузка состояния предыдущего индекса"""
        state_file_path = Path(self.state_file)
        if state_file_path.exists():
            try:
                with open(state_file_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self.logger.info(f"Загружено состояние из {self.state_file}")
                return state
            except Exception as e:
                self.logger.warning(f"Ошибка загрузки состояния: {e}. Создаю новое состояние.")

        # Создаем начальное состояние
        initial_state = {
            "config_version": "1.0",
            "last_update": None,
            "file_hashes": {},
            "total_files": 0,
            "total_chunks": 0,
            "update_history": [],
            "settings": {
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "model_name": self.model_name
            }
        }
        self.logger.info("Создано начальное состояние")
        return initial_state

    def _save_state(self):
        """Сохранение текущего состояния"""
        try:
            state_file_path = Path(self.state_file)
            state_file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(state_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Состояние сохранено в {self.state_file}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения состояния: {e}")

    def _save_last_run_info(self, stats: Dict[str, Any]):
        """Сохранение информации о последнем запуске"""
        try:
            last_run_info = {
                "last_run_timestamp": datetime.now().isoformat(),
                "status": "success" if stats["success"] else "failed",
                "new_chunks": stats.get("new_chunks", 0),
                "total_chunks": stats.get("total_chunks_in_index", 0),
                "duration_seconds": stats.get("duration_seconds", 0),
                "errors_count": len(stats.get("errors", [])),
                "config_used": {
                    "model": self.model_name,
                    "chunk_size": self.chunk_size,
                    "chunk_overlap": self.chunk_overlap
                }
            }

            last_run_path = Path(self.last_run_file)
            last_run_path.parent.mkdir(parents=True, exist_ok=True)

            with open(last_run_path, 'w', encoding='utf-8') as f:
                json.dump(last_run_info, f, ensure_ascii=False, indent=2)

            self.logger.debug(f"Информация о последнем запуске сохранена в {self.last_run_file}")

        except Exception as e:
            self.logger.error(f"Ошибка сохранения информации о последнем запуске: {e}")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Вычисление хэша файла для отслеживания изменений"""
        try:
            hasher = hashlib.md5()
            with open(file_path, 'rb') as f:
                buf = f.read()
                hasher.update(buf)
            return hasher.hexdigest()
        except Exception as e:
            self.logger.error(f"Ошибка вычисления хэша для {file_path}: {e}")
            return ""

    def _get_file_extensions(self) -> Set[str]:
        """Получение списка расширений файлов из конфигурации"""
        extensions = self.config.get("knowledge_base.extensions", [".txt", ".md", ".rst", ".text"])
        return {ext.lower() for ext in extensions}

    def _find_new_or_modified_files(self) -> Tuple[List[Path], List[Path]]:
        """
        Поиск новых или измененных файлов

        Возвращает:
            Tuple[List[Path], List[Path]]: (новые_файлы, измененные_файлы)
        """
        extensions = self._get_file_extensions()
        new_files = []
        modified_files = []

        self.logger.info(f"Сканирование директории: {self.knowledge_base_dir}")
        self.logger.info(f"Поддерживаемые расширения: {', '.join(extensions)}")

        # Сканируем все файлы в директории
        file_count = 0
        for file_path in self.knowledge_base_dir.rglob('*'):
            if file_path.is_file():
                file_count += 1
                if file_path.suffix.lower() in extensions:
                    file_hash = self._calculate_file_hash(file_path)
                    file_str = str(file_path)

                    # Проверяем, новый ли файл
                    if file_str not in self.state["file_hashes"]:
                        new_files.append(file_path)
                        self.state["file_hashes"][file_str] = {
                            "hash": file_hash,
                            "last_modified": file_path.stat().st_mtime,
                            "path": str(file_path),
                            "size": file_path.stat().st_size,
                            "first_seen": datetime.now().isoformat()
                        }
                        self.logger.debug(f"Обнаружен новый файл: {file_path.name}")
                    else:
                        # Проверяем, изменился ли файл
                        old_hash = self.state["file_hashes"][file_str]["hash"]
                        if old_hash != file_hash:
                            modified_files.append(file_path)
                            self.state["file_hashes"][file_str].update({
                                "hash": file_hash,
                                "last_modified": file_path.stat().st_mtime,
                                "size": file_path.stat().st_size,
                                "last_updated": datetime.now().isoformat()
                            })
                            self.logger.debug(f"Обнаружен измененный файл: {file_path.name}")

        self.logger.info(f"Просканировано файлов: {file_count}")
        self.logger.info(f"Текстовых файлов для обработки: {len(new_files) + len(modified_files)}")

        return new_files, modified_files

    def _process_file_to_chunks(self, file_path: Path) -> List[str]:
        """Разбиение файла на чанки с использованием настроек из конфигурации"""
        try:
            # Определяем кодировку
            encodings = ['utf-8', 'cp1251', 'iso-8859-1', 'cp866']
            content = None

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                self.logger.warning(f"Не удалось прочитать файл {file_path} в поддерживаемых кодировках")
                return []

            # Используем параметры из конфигурации
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                length_function=len
            )

            chunks = text_splitter.split_text(content)
            self.logger.debug(f"Файл {file_path.name} разбит на {len(chunks)} чанков")
            return chunks

        except Exception as e:
            self.logger.error(f"Ошибка обработки файла {file_path}: {e}")
            return []

    def _add_chunks_to_index(self, file_path: Path, chunks: List[str],
                           collection, is_modified: bool = False) -> int:
        """Добавление чанков в индекс"""
        try:
            # Если файл изменен, удаляем старые чанки
            if is_modified:
                self._remove_file_from_index(file_path, collection)

            # Подготавливаем данные для добавления
            documents = []
            metadatas = []
            ids = []

            for i, chunk in enumerate(chunks):
                # Создаем уникальный ID на основе содержимого
                chunk_hash = hashlib.md5(chunk.encode()).hexdigest()[:12]
                chunk_id = f"{file_path.stem}_{chunk_hash}_{i}"

                documents.append(chunk)
                metadatas.append({
                    "source": str(file_path),
                    "chunk_index": i,
                    "file_name": file_path.name,
                    "total_chunks": len(chunks),
                    "last_updated": datetime.now().isoformat(),
                    "chunk_size": len(chunk),
                    "file_size": file_path.stat().st_size
                })
                ids.append(chunk_id)

            # Добавляем в коллекцию батчами (если много чанков)
            total_added = 0
            batch_size = self.batch_size

            for i in range(0, len(documents), batch_size):
                batch_end = min(i + batch_size, len(documents))

                collection.add(
                    documents=documents[i:batch_end],
                    metadatas=metadatas[i:batch_end],
                    ids=ids[i:batch_end]
                )

                batch_added = batch_end - i
                total_added += batch_added
                self.logger.debug(f"Добавлен батч {i//batch_size + 1}: {batch_added} чанков")

            self.logger.info(f"Добавлено {total_added} чанков из {file_path.name}")
            return total_added

        except Exception as e:
            self.logger.error(f"Ошибка добавления чанков в индекс: {e}")
            return 0

    def _remove_file_from_index(self, file_path: Path, collection):
        """Удаление всех чанков файла из индекса"""
        try:
            # Получаем все элементы с данным source
            results = collection.get(
                where={"source": str(file_path)}
            )

            if results and results['ids']:
                collection.delete(ids=results['ids'])
                self.logger.info(f"Удалено {len(results['ids'])} старых чанков из {file_path.name}")

        except Exception as e:
            self.logger.error(f"Ошибка удаления чанков: {e}")

    def _cleanup_orphaned_files(self, collection):
        """Очистка файлов, которые были удалены из исходной директории"""
        try:
            # Получаем все источники из индекса
            all_items = collection.get()
            if not all_items or not all_items['metadatas']:
                return

            # Собираем все источники из индекса
            indexed_sources = set()
            for metadata in all_items['metadatas']:
                if metadata and 'source' in metadata:
                    indexed_sources.add(metadata['source'])

            # Проверяем, какие файлы существуют
            files_to_remove = []
            for source in indexed_sources:
                source_path = Path(source)
                if not source_path.exists():
                    files_to_remove.append(source)

            # Удаляем чанки несуществующих файлов
            removed_count = 0
            for source in files_to_remove:
                try:
                    results = collection.get(where={"source": source})
                    if results and results['ids']:
                        collection.delete(ids=results['ids'])
                        removed_count += len(results['ids'])
                        self.logger.info(f"Удалены чанки отсутствующего файла: {Path(source).name}")
                except Exception as e:
                    self.logger.error(f"Ошибка удаления чанков для {source}: {e}")

            if removed_count > 0:
                self.logger.info(f"Всего удалено {removed_count} чанков из {len(files_to_remove)} отсутствующих файлов")

        except Exception as e:
            self.logger.error(f"Ошибка очистки orphaned файлов: {e}")

    def update_index(self) -> Dict[str, Any]:
        """
        Основной метод обновления индекса

        Возвращает:
            Dict[str, Any]: Статистика обновления
        """
        start_time = time.time()
        self.logger.info("=" * 60)
        self.logger.info(f"НАЧАЛО ОБНОВЛЕНИЯ ИНДЕКСА: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Источник данных: {self.knowledge_base_dir}")
        self.logger.info(f"Модель: {self.model_name}, Размер чанка: {self.chunk_size}, Перекрытие: {self.chunk_overlap}")

        stats = {
            "start_time": datetime.now().isoformat(),
            "config": {
                "model": self.model_name,
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "collection": self.collection_name
            },
            "new_files": 0,
            "modified_files": 0,
            "new_chunks": 0,
            "errors": [],
            "success": False
        }

        try:
            # Получаем или создаем коллекцию
            collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={
                    "hnsw:space": "cosine",
                    "model": self.model_name,
                    "last_updated": datetime.now().isoformat()
                }
            )

            # Поиск новых и измененных файлов
            new_files, modified_files = self._find_new_or_modified_files()
            stats["new_files"] = len(new_files)
            stats["modified_files"] = len(modified_files)

            self.logger.info(f"Найдено новых файлов: {len(new_files)}")
            self.logger.info(f"Найдено измененных файлов: {len(modified_files)}")

            # Обработка новых файлов
            total_chunks_added = 0

            # Сначала обрабатываем измененные файлы
            if modified_files:
                self.logger.info("Обработка измененных файлов...")
                for file_path in modified_files:
                    try:
                        self.logger.info(f"Обновление файла: {file_path.name}")

                        # Разбиваем на чанки
                        chunks = self._process_file_to_chunks(file_path)

                        if chunks:
                            # Добавляем в индекс (старые чанки удаляются автоматически)
                            chunks_added = self._add_chunks_to_index(
                                file_path, chunks, collection, is_modified=True
                            )
                            total_chunks_added += chunks_added

                    except Exception as e:
                        error_msg = f"Ошибка обновления файла {file_path}: {str(e)}"
                        self.logger.error(error_msg)
                        stats["errors"].append(error_msg)

            # Затем обрабатываем новые файлы
            if new_files:
                self.logger.info("Обработка новых файлов...")
                for file_path in new_files:
                    try:
                        self.logger.info(f"Добавление нового файла: {file_path.name}")

                        # Разбиваем на чанки
                        chunks = self._process_file_to_chunks(file_path)

                        if chunks:
                            # Добавляем в индекс
                            chunks_added = self._add_chunks_to_index(
                                file_path, chunks, collection, is_modified=False
                            )
                            total_chunks_added += chunks_added

                    except Exception as e:
                        error_msg = f"Ошибка добавления файла {file_path}: {str(e)}"
                        self.logger.error(error_msg)
                        stats["errors"].append(error_msg)

            # Очистка удаленных файлов
            self.logger.info("Очистка удаленных файлов...")
            self._cleanup_orphaned_files(collection)

            # Получаем статистику индекса
            index_count = collection.count()
            stats["total_chunks_in_index"] = index_count
            stats["new_chunks"] = total_chunks_added

            # Обновляем состояние
            self.state["last_update"] = datetime.now().isoformat()
            self.state["total_files"] = len(self.state["file_hashes"])
            self.state["total_chunks"] = index_count

            # Добавляем запись в историю (сохраняем только последние 100 записей)
            update_record = {
                "timestamp": datetime.now().isoformat(),
                "new_files": len(new_files),
                "modified_files": len(modified_files),
                "chunks_added": total_chunks_added,
                "total_chunks": index_count,
                "errors": len(stats["errors"]),
                "duration_seconds": 0  # Будет обновлено позже
            }
            self.state["update_history"].append(update_record)

            # Ограничиваем историю 100 записями
            if len(self.state["update_history"]) > 100:
                self.state["update_history"] = self.state["update_history"][-100:]

            # Сохраняем состояние
            self._save_state()

            end_time = time.time()
            duration = round(end_time - start_time, 2)

            # Обновляем последнюю запись в истории
            update_record["duration_seconds"] = duration
            self.state["update_history"][-1] = update_record
            self._save_state()  # Сохраняем еще раз с обновленной длительностью

            # Обновляем статистику
            stats["end_time"] = datetime.now().isoformat()
            stats["duration_seconds"] = duration
            stats["success"] = True

            # Сохраняем информацию о последнем запуске
            self._save_last_run_info(stats)

            # Логируем результат
            self.logger.info("=" * 60)
            self.logger.info("ОБНОВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО")
            self.logger.info(f"Добавлено чанков: {total_chunks_added}")
            self.logger.info(f"Всего чанков в индексе: {index_count}")
            self.logger.info(f"Время выполнения: {duration:.2f} сек")
            self.logger.info(f"Скорость: {total_chunks_added/duration if duration > 0 else 0:.2f} чанков/сек")
            self.logger.info(f"Ошибок: {len(stats['errors'])}")
            self.logger.info("=" * 60)

            if stats["errors"]:
                for error in stats["errors"]:
                    self.logger.warning(f"Ошибка: {error}")

        except Exception as e:
            error_msg = f"Критическая ошибка при обновлении индекса: {str(e)}"
            self.logger.error(error_msg)
            stats["errors"].append(error_msg)
            stats["end_time"] = datetime.now().isoformat()
            stats["duration_seconds"] = round(time.time() - start_time, 2)

            # Сохраняем информацию о неудачном запуске
            self._save_last_run_info(stats)

        # Сохраняем статистику в файл
        self._save_stats(stats)

        return stats

    def _save_stats(self, stats: Dict[str, Any]):
        """Сохранение статистики обновления"""
        try:
            stats_file_path = Path(self.stats_file)
            stats_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Если файл существует, загружаем историю
            all_stats = []
            if stats_file_path.exists():
                try:
                    with open(stats_file_path, 'r', encoding='utf-8') as f:
                        all_stats = json.load(f)
                except:
                    all_stats = []

            # Добавляем новую статистику (сохраняем только последние 50 записей)
            all_stats.append(stats)
            if len(all_stats) > 50:
                all_stats = all_stats[-50:]

            with open(stats_file_path, 'w', encoding='utf-8') as f:
                json.dump(all_stats, f, ensure_ascii=False, indent=2)

            self.logger.debug(f"Статистика сохранена в {self.stats_file}")

        except Exception as e:
            self.logger.error(f"Ошибка сохранения статистики: {e}")


def main():
    """Основная функция запуска обновления"""

    print("=" * 60)
    print("АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ ВЕКТОРНОГО ИНДЕКСА")
    print(f"Запуск: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Загружаем конфигурацию
    config = ConfigLoader()

    # Проверяем существование директории
    kb_dir = Path(config.get("knowledge_base.source_dir"))
    if not kb_dir.exists():
        print(f"❌ ОШИБКА: Директория {kb_dir} не существует!")
        print(f"   Проверьте путь в config.json: knowledge_base.source_dir")
        return

    # Создаем обновлятель с конфигурацией
    updater = VectorIndexUpdater(config)

    # Выполняем обновление
    stats = updater.update_index()

    # Вывод краткой информации в консоль
    print("\n" + "=" * 60)
    if stats["success"]:
        print("✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО")
        print(f"   Новые файлы: {stats['new_files']}")
        print(f"   Измененные файлы: {stats['modified_files']}")
        print(f"   Добавлено чанков: {stats['new_chunks']}")
        print(f"   Всего чанков: {stats['total_chunks_in_index']}")
        print(f"   Время выполнения: {stats['duration_seconds']:.2f} сек")

        if stats["errors"]:
            print(f"   Предупреждения/ошибки: {len(stats['errors'])}")
            for i, error in enumerate(stats['errors'][:3], 1):
                print(f"     {i}. {error[:100]}...")
    else:
        print("❌ ОБНОВЛЕНИЕ ЗАВЕРШЕНО С ОШИБКАМИ!")
        if stats["errors"]:
            for i, error in enumerate(stats['errors'], 1):
                print(f"   {i}. {error}")

    print(f"\n📊 Подробная статистика в файле: {config.get('state_files.stats_file')}")
    print(f"📝 Логи в файле: {config.get('logging.log_file')}")
    print("=" * 60)


if __name__ == "__main__":
    main()