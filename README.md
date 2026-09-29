# Психологическая Служба Московского политехнического университета

Веб-сервис для организации психологической поддержки студентов Московского политехнического университета.

Описание API экстренного контакта записи и порядок выпуска: [экстренный контакт](docs/emergency-contact.md).

## Структура каталогов

```
mospoly-psychological-support/
├── psychohelp/                  # Основной пакет приложения
│   ├── config/                  # Конфигурация базы данных
│   │   ├── __init__.py
│   │   └── database.py
│   ├── models/                  # SQLAlchemy модели
│   │   ├── appointments.py      # Модель записей на консультации
│   │   ├── reviews.py           # Модель отзывов
│   │   ├── roles.py             # Модель ролей пользователей
│   │   ├── therapists.py        # Модель психологов
│   │   └── users.py             # Модель пользователей
│   ├── repositories/            # Слой доступа к данным
│   │   ├── appointments.py
│   │   ├── reviews.py
│   │   ├── roles.py
│   │   ├── therapists.py
│   │   └── users.py
│   ├── routes/                   # API маршруты
│   │   └── controllers/          # Контроллеры для обработки запросов
│   │       ├── appointments.py
│   │       ├── images.py
│   │       ├── reviews.py
│   │       ├── roles.py
│   │       ├── therapists.py
│   │       └── users.py
│   ├── schemas/                  # Pydantic схемы для валидации
│   │   ├── appointments.py
│   │   ├── reviews.py
│   │   ├── therapists.py
│   │   └── users.py
│   ├── services/                 # Бизнес-логика
│   │   ├── appointments.py
│   │   ├── reviews.py
│   │   ├── roles.py
│   │   ├── therapists.py
│   │   └── users/               # Модульная структура users
│   │       ├── exceptions.py    # Кастомные исключения
│   │       ├── models.py        # Модели данных сервисного слоя
│   │       └── users.py         # Логика работы с пользователями
│   └── main.py                   # Точка входа приложения
├── tests/                        # Тесты
│   ├── conftest.py
│   └── test_users.py
├── docker-compose.yml            # Docker Compose конфигурация
├── Dockerfile                    # Docker образ
├── pyproject.toml                # Конфигурация проекта и зависимости
├── swagger.yaml                  # OpenAPI спецификация
└── uv.lock                       # Файл блокировки зависимостей
```

## Используемый стек

### Backend

-   **FastAPI** - современный веб-фреймворк для создания API
-   **SQLAlchemy** - ORM для работы с базой данных
-   **PostgreSQL** - реляционная база данных
-   **AsyncPG** - асинхронный драйвер PostgreSQL
-   **Alembic** - система миграций базы данных
-   **Pydantic** - валидация данных и сериализация
-   **JWT** - аутентификация через токены
-   **Passlib** - хеширование паролей

### Инфраструктура

-   **Docker** - контейнеризация приложения
-   **Docker Compose** - оркестрация сервисов
-   **UV** - быстрый менеджер пакетов Python
-   **Uvicorn** - ASGI сервер для FastAPI

### Разработка

-   **Pytest** - фреймворк для тестирования
-   **Pytest-asyncio** - поддержка асинхронного тестирования
-   **Python logging** - стандартное логирование

## Установка и запуск

### Предварительные требования

-   Python 3.13
-   Docker и Docker Compose
-   UV

### Локальная разработка

1. **Клонирование репозитория:**

    ```
    git clone https://github.com/nikitabel0/mospoly-psychological-support.git
    cd mospoly-psychological-support
    ```

2. **Установка зависимостей:**

    ```
    uv pip install -e .
    ```

3. **Запуск базы данных:**

    ```
    docker-compose up db -d
    ```

4. **Запуск приложения:**
    ```
    uv run python -m psychohelp.main
    ```

### Docker (рекомендуется)

1. **Запуск всех сервисов:**

    ```
    docker-compose up --build
    ```

2. **Запуск в фоновом режиме:**

    ```
    docker-compose up -d --build
    ```

3. **Остановка сервисов:**
    ```
    docker-compose down
    ```

## Базовые команды

### Разработка

```
# Установка зависимостей для разработки
uv pip install -e ".[dev]"

# Запуск тестов
pytest

# Запуск тестов с покрытием
pytest --cov=psychohelp

# Запуск линтера (если настроен)
flake8 psychohelp/
```

### Docker

```bash
# Пересборка и запуск
docker-compose up --build

# Просмотр логов
docker-compose logs -f app

# Выполнение команд в контейнере
docker-compose exec app bash

# Очистка volumes
docker-compose down -v
```

### База данных

```bash
# Подключение к базе данных
docker-compose exec db psql -U postgres -d psychohelp

# Создание резервной копии
docker-compose exec db pg_dump -U postgres psychohelp > backup.sql

# Восстановление из резервной копии
docker-compose exec -T db psql -U postgres psychohelp < backup.sql
```

### Миграции базы данных

Проект использует Alembic для управления миграциями SQLAlchemy.

#### Переменные окружения для миграций

```bash
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
export POSTGRES_DB=postgres
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
```

#### Команды миграций

```bash
# Создание новой миграции с автогенерацией
POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=postgres POSTGRES_HOST=localhost POSTGRES_PORT=5432 uv run alembic revision --autogenerate -m "Описание изменений"

# Применение миграций
POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=postgres POSTGRES_HOST=localhost POSTGRES_PORT=5432 uv run alembic upgrade head

# Откат к предыдущей миграции
POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=postgres POSTGRES_HOST=localhost POSTGRES_PORT=5432 uv run alembic downgrade -1

# Просмотр текущей версии
POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=postgres POSTGRES_HOST=localhost POSTGRES_PORT=5432 uv run alembic current

# Просмотр истории миграций
POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=postgres POSTGRES_HOST=localhost POSTGRES_PORT=5432 uv run alembic history
```

#### Работа с Docker Compose

```bash
# Применение миграций в Docker окружении
docker-compose exec app bash -c "POSTGRES_HOST=db uv run alembic upgrade head"

# Создание миграции в Docker окружении
docker-compose exec app bash -c "POSTGRES_HOST=db uv run alembic revision --autogenerate -m 'Описание изменений'"
```

### Логирование

Проект использует встроенный модуль `logging` Python.

#### Переменные окружения для настройки логирования

```bash
export LOG_LEVEL=INFO
export LOG_FILE=/path/to/logfile.log
```

#### Уровни логирования

-   `DEBUG` - детальная информация для отладки (по умолчанию)
-   `INFO` - общая информация о работе приложения
-   `WARNING` - предупреждения
-   `ERROR` - ошибки
-   `CRITICAL` - критические ошибки

#### Пример запуска с настройками логирования

```bash
# По умолчанию используется DEBUG
uv run python -m psychohelp.main

# Изменить уровень на INFO
LOG_LEVEL=INFO uv run python -m psychohelp.main
```
