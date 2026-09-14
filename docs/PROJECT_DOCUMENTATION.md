# Документация проекта "Психологическая служба МосПоли"

**Последнее обновление**: 15 декабря 2025 г.

## Содержание

1. [Обзор проекта](#обзор-проекта-психологическая-служба-мосполи)
   - Описание
   - Цели и задачи
   - Целевая аудитория
   - Ключевые функции
   - Преимущества системы
   - Технологический стек
   - Быстрый старт

2. [Бизнес-логика системы](#бизнес-логика-системы)
   - Основные бизнес-процессы
   - Бизнес-правила и ограничения
   - Валидация данных
   - Транзакции и целостность данных
   - Безопасность
   - Реализованные возможности

3. [Компоненты системы](#компоненты-системы)
   - Main Application
   - Configuration (database, logging, __init__)
   - Models
   - Repositories
   - Services
   - Routes/Controllers
   - Schemas
   - Tests
   - Взаимодействие компонентов
   - Конфигурация и окружение
   - Зависимости

---

# Обзор проекта "Психологическая служба МосПоли"

## Описание

Проект представляет собой веб-приложение для автоматизации работы психологической службы МосПоли. Система позволяет студентам записываться на консультации к психологам университета, а психологам — эффективно управлять своим расписанием и взаимодействовать с клиентами.

## Цели и задачи

### Основные цели:
1. **Упрощение процесса записи** - студенты могут самостоятельно записаться на консультацию
2. **Централизация информации** - вся информация о психологах и записях в одном месте
3. **Автоматизация управления** - уменьшение административной нагрузки
4. **Повышение доступности** - возможность онлайн-консультаций

### Задачи системы:
- ✅ Регистрация и аутентификация пользователей
- ✅ Управление профилями психологов с детальной информацией
- ✅ Создание и отмена записей на консультации
- ✅ Поддержка онлайн и офлайн встреч
- ✅ Система уведомлений о предстоящих встречах
- ✅ Сбор и отображение отзывов о консультациях
- ✅ Разграничение прав доступа по ролям

## Целевая аудитория

### 1. Студенты
- Основные пользователи системы
- Записываются на консультации
- Просматривают информацию о психологах
- Оставляют отзывы после встреч

### 2. Психологи
- Просматривают свои записи
- Управляют расписанием
- Проводят консультации (онлайн и офлайн)

### 3. Администраторы
- Управляют пользователями
- Добавляют и редактируют информацию о психологах
- Модерируют контент

### 4. Персонал (Stuff)
- Вспомогательный персонал службы
- Помогают с организацией консультаций

## Ключевые функции

### Управление пользователями
- Регистрация с валидацией данных
- Вход через email и пароль
- JWT-аутентификация с HTTP-only cookies
- Профили пользователей с контактной информацией

### Система записей
- Создание записи на консультацию
- Выбор типа встречи (онлайн/офлайн)
- Указание причины обращения
- Напоминания о предстоящих встречах
- Отмена записей
- История встреч

### Профили психологов
- Подробная информация о специалистах
- Опыт работы и квалификация
- Области консультирования
- Образование
- Номер кабинета
- Фотография
- Краткое и полное описание

### Отзывы
- Отзывы привязаны к конкретной встрече
- Временная метка
- Текстовый контент

## Преимущества системы

1. **Доступность 24/7** - запись в любое время
2. **Прозрачность** - информация о психологах всегда доступна
3. **Удобство** - простой интерфейс и понятная навигация
4. **Безопасность** - защита персональных данных (JWT, bcrypt)
5. **Гибкость** - поддержка онлайн и офлайн форматов
6. **Аналитика** - возможность анализа загруженности службы
7. **Логирование** - полная трассировка всех операций
8. **Версионирование БД** - Alembic миграции для безопасных обновлений
9. **Контейнеризация** - легкое развертывание через Docker

## Технологический стек

### Backend
- **Python 3.8+** - Язык программирования
- **FastAPI 0.115.0** - Современный async веб-фреймворк
- **SQLAlchemy 2.0.35** - ORM для работы с БД
- **Pydantic 2+** - Валидация данных
- **Uvicorn** - ASGI сервер

### База данных
- **PostgreSQL 17** - Реляционная БД
- **asyncpg** - Асинхронный драйвер
- **Alembic** - Миграции схемы

### Безопасность
- **JWT (PyJWT)** - Токены аутентификации
- **bcrypt (Passlib)** - Хеширование паролей
- **HTTP-only cookies** - Защита от XSS

### Инфраструктура
- **Docker & Docker Compose** - Контейнеризация
- **Make** - Автоматизация
- **uv** - Быстрый менеджер пакетов Python

### Разработка
- **pytest** - Тестирование
- **logging** - Встроенная система логов

## Быстрый старт

### Запуск через Docker (рекомендуется)

```bash
# Клонировать репозиторий
git clone <repository-url>
cd mospoly-psychological-support

# Запустить сервисы
make up

# Приложение доступно на http://localhost:8000
```

### Запуск локально

```bash
# Установить зависимости (с uv)
uv sync

# Или с pip
pip install -e .

# Настроить переменные окружения
export POSTGRES_HOST=localhost
export SECRET_KEY=your-secret-key
# ... другие переменные

# Применить миграции
alembic upgrade head

# Запустить приложение
psychohelp

# Или напрямую
python -m psychohelp.main
```

### Полезные команды

```bash
# Остановить Docker сервисы
make down

# Создать миграцию
alembic revision --autogenerate -m "описание"

# Запустить тесты
pytest

# Проверить логи
docker compose logs -f app
```

# Бизнес-логика системы

## Основные бизнес-процессы

### 1. 🔐 Регистрация и аутентификация

#### Процесс регистрации

```
┌─────────────┐
│  Пользователь│
│  вводит     │
│  данные     │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────┐
│ Валидация данных (Pydantic)  │
│ - Email формат               │
│ - Телефон в формате E164     │
│ - Пароль минимум 8 символов  │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Проверка уникальности email  │
└──────┬───────────────────────┘
       │
       ├─── Email существует → Ошибка 422
       │
       ▼
┌──────────────────────────────┐
│ Хеширование пароля (bcrypt)  │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Создание записи в БД         │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Генерация JWT токена         │
│ - sub: user_id               │
│ - exp: текущее время + TTL   │
│ - iat: текущее время         │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Установка cookie с токеном   │
│ - HttpOnly                   │
│ - Secure (prod)              │
│ - SameSite=None              │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Возврат данных пользователя  │
│ (без пароля)                 │
└──────────────────────────────┘
```

**Код**: `psychohelp/services/users.py::register_user`

**Бизнес-правила**:
1. Email должен быть уникальным
2. Пароль хешируется и никогда не хранится в открытом виде
3. После регистрации пользователь автоматически аутентифицирован
4. По умолчанию пользователь не имеет ролей (если не указано иначе)

---

#### Процесс входа

```
┌─────────────┐
│ Пользователь│
│ вводит      │
│ email+pass  │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────┐
│ Поиск пользователя по email  │
└──────┬───────────────────────┘
       │
       ├─── Не найден → Ошибка 403
       │
       ▼
┌──────────────────────────────┐
│ Проверка пароля              │
│ bcrypt.verify(plain, hash)   │
└──────┬───────────────────────┘
       │
       ├─── Не совпадает → Ошибка 403
       │
       ▼
┌──────────────────────────────┐
│ Генерация JWT токенов        │
│ - Access token (30 мин)      │
│ - Refresh token (30 дней)    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Установка cookies            │
│ - access_token (HttpOnly)    │
│ - refresh_token (HttpOnly)   │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Возврат данных пользователя  │
└──────────────────────────────┘
```

**Код**: `psychohelp/services/users.py::login_user`

**Бизнес-правила**:
1. Неверные данные не раскрывают, что именно неверно (email или пароль) - всегда 403
2. Используется медленное хеширование bcrypt (защита от брутфорса)
3. Access token имеет время жизни 30 минут (по умолчанию)
4. Refresh token имеет время жизни 30 дней (по умолчанию)
5. Оба токена хранятся в HttpOnly cookies

#### Обновление токена (Refresh)

Система поддерживает обновление access token через refresh token:

**Endpoint**: `POST /users/refresh`

**Процесс**:
1. Извлечение refresh_token из cookie
2. Валидация refresh token
3. Генерация нового access token
4. Установка нового access token в cookie
5. Возврат данных пользователя

**Бизнес-правила**:
- Refresh token проверяется на истечение срока действия
- При невалидном refresh token возвращается 401
- Новый access token выдается на стандартный срок (30 минут)

---

### 2. 📅 Создание записи на консультацию

```
┌─────────────┐
│ Студент     │
│ выбирает    │
│ психолога   │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────┐
│ Заполнение формы записи:     │
│ - Тип (Online/Offline)       │
│ - Причина (опционально)      │
│ - Время напоминания          │
│ - Место встречи              │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Валидация данных             │
│ - patient_id существует      │
│ - therapist_id существует    │
│ - patient_id ≠ therapist_id  │
└──────┬───────────────────────┘
       │
       ├─── Ошибка → 400
       │
       ▼
┌──────────────────────────────┐
│ Создание записи:             │
│ - status = "Approved"        │
│ - last_change_time = now()   │
│ - venue = указанное или ""   │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Сохранение в БД              │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Возврат созданной записи     │
└──────────────────────────────┘
```

**Код**: `psychohelp/services/appointments.py::create_appointment`

**Бизнес-правила**:
1. **Пациент не может быть психологом** в одной записи
2. **Статус по умолчанию**: `Accepted` (принята психологом)
3. **Venue обязательно**: для Online - ссылка, для Offline - автоматически берется office психолога
4. **scheduled_time обязательно**: не может быть в прошлом
5. **remind_time опционально**: должно быть раньше scheduled_time и не в прошлом
6. **last_change_time**: автоматически устанавливается при создании/изменении
7. **comment опционально**: комментарий к записи (до 512 символов)
8. Причина обращения опциональна (конфиденциальность)

**Валидация времени**:
```python
# scheduled_time проверка
if scheduled_time_utc <= now:
    raise InvalidScheduledTimeException(scheduled_time)

# remind_time проверка
if remind_time_utc <= now:
    raise InvalidRemindTimeException(remind_time, "не может быть в прошлом")
if remind_time_utc >= scheduled_time_utc:
    raise InvalidRemindTimeException(remind_time, "должно быть раньше времени встречи")
```

**Возможные статусы записи**:
- `Approved` - Одобрена (создана)
- `Accepted` - Принята (психолог подтвердил)
- `Cancelled` - Отменена
- `Done` - Завершена

---

### 3. ❌ Отмена записи

```
┌─────────────┐
│ Пользователь│
│ отменяет    │
│ запись      │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────┐
│ Поиск записи по ID           │
└──────┬───────────────────────┘
       │
       ├─── Не найдена → 404
       │
       ▼
┌──────────────────────────────┐
│ Проверка текущего статуса    │
└──────┬───────────────────────┘
       │
       ├─── Уже отменена/завершена → 400
       │
       ▼
┌──────────────────────────────┐
│ Обновление записи:           │
│ - status = "Cancelled"       │
│ - last_change_time = now()   │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Сохранение изменений         │
└──────────────────────────────┘
```

**Код**: `psychohelp/services/appointments.py::cancel_appointment_by_id`

**Бизнес-правила**:
1. Нельзя отменить уже отмененную запись
2. Нельзя отменить завершенную запись
3. При отмене обновляется last_change_time
4. История сохраняется (запись не удаляется)

---

### 4. 👨‍⚕️ Управление профилями психологов

#### Структура информации о психологе

Психолог - это расширенная информация о пользователе с ролью `psychologist`:

```
User (базовая информация)
├── ФИО
├── Контакты (email, телефон, соцсети)
└── Аутентификация

Psychologist (профессиональная информация)
├── id (отдельный UUID, Primary Key)
├── user_id (Foreign Key к users, unique)
├── Опыт работы (experience)
├── Квалификация (qualification)
├── Области консультирования (consult_areas)
├── Образование (education)
├── Описание (description)
├── Краткое описание (short_description)
├── Номер кабинета (office)
└── Фотография (photo, опционально)
```

**Бизнес-правила**:
1. Профиль психолога создается отдельно от пользователя через API
2. Психолог имеет свой отдельный ID (не совпадает с user_id)
3. user_id - Foreign Key, обеспечивающий связь One-to-One
4. При создании профиля пользователь автоматически получает роль `psychologist`
5. При удалении профиля роль `psychologist` автоматически убирается
6. Создание и удаление психологов требует разрешения `psychologists.manage`
7. Фотография опциональна

---

### 5. 📝 Система отзывов

```
┌─────────────┐
│ Встреча     │
│ завершена   │
│ (Done)      │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────┐
│ Пациент может оставить отзыв │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Создание отзыва:             │
│ - appointment_id (PK)        │
│ - time = now()               │
│ - content                    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Сохранение в БД              │
└──────────────────────────────┘
```

**Бизнес-правила**:
1. **Один отзыв на одну встречу** (1:1 relationship)
2. Отзыв привязан к встрече, а не к психологу напрямую
3. При удалении встречи отзыв удаляется (CASCADE)
4. Отзыв должен оставляться после завершения встречи (рекомендуется добавить проверку)

---

### 6. 🔐 Система ролей и разрешений (RBAC)

#### Существующие роли

```python
class RoleCode(str, Enum):
    USER = "user"                        # Обычный пользователь (студент)
    PSYCHOLOGIST = "psychologist"        # Психолог
    ADMIN = "admin"                      # Администратор
    CONTENT_MANAGER = "content_manager"  # Контент-менеджер
```

#### Модель ролей

- Пользователь может иметь **несколько ролей** одновременно
- Роли хранятся в отдельной таблице `roles` с полями: id, code, name, description
- Связь пользователя и ролей через промежуточную таблицу `users_roles` (Many-to-Many)
- При регистрации пользователь автоматически получает роль `user`

#### Система разрешений (Permissions)

Каждая роль имеет набор разрешений (permissions). Разрешения определяют конкретные действия:

**Разрешения для записей (Appointments)**:
- `appointments.create_own` - Создание своих записей
- `appointments.view_own` - Просмотр своих записей
- `appointments.cancel_own` - Отмена своих записей
- `appointments.confirm_own` - Подтверждение своих записей
- `appointments.view_pending` - Просмотр ожидающих записей
- `appointments.accept` - Принятие записей
- `appointments.reschedule` - Перенос записей
- `appointments.reject` - Отклонение записей
- `appointments.view_all` - Просмотр всех записей
- `appointments.edit_all` - Редактирование всех записей
- `appointments.delete_all` - Удаление всех записей

**Разрешения для отзывов (Reviews)**:
- `reviews.create_own` - Создание своих отзывов
- `reviews.view_all` - Просмотр всех отзывов

**Разрешения для пользователей (Users)**:
- `users.edit_own_profile` - Редактирование своего профиля

**Разрешения для психологов (Psychologists)**:
- `psychologists.edit_own_profile` - Редактирование своего профиля психолога
- `psychologists.manage` - Управление психологами (создание, удаление)

**Другие разрешения**:
- `statistics.view` - Просмотр статистики
- `faq.edit` - Редактирование FAQ
- `materials.create`, `materials.edit`, `materials.delete` - Управление материалами
- `tests.create`, `tests.edit`, `tests.delete` - Управление тестами

#### Проверка разрешений

Система использует декоратор `@require_permission(PermissionCode)` для защиты endpoint'ов:

```python
@router.post("/create")
@require_permission(PermissionCode.APPOINTMENTS_CREATE_OWN)
async def create_appointment(request: Request, ...):
    # Endpoint доступен только пользователям с нужным разрешением
    pass
```

**Процесс проверки**:
1. Извлечение access token из HTTP-only cookie
2. Получение user_id из токена
3. Загрузка всех ролей пользователя
4. Загрузка всех разрешений из ролей
5. Проверка наличия требуемого разрешения

**✅ Реализовано**: Полная система RBAC с ролями, разрешениями и проверкой прав на уровне endpoint'ов.

---

## Бизнес-правила и ограничения

### Пользователи

1. ✅ Email должен быть уникальным
2. ✅ Пароль минимум 8 символов
3. ✅ Пароль всегда хешируется (bcrypt)
4. ✅ Телефон в международном формате E164 (+79001234567)
5. ✅ Отчество и соцсети опциональны

### Записи на консультации

1. ✅ Пациент ≠ Психолог (нельзя записаться к самому себе)
2. ✅ Оба пользователя должны существовать
3. ✅ Тип встречи: только Online или Offline
4. ✅ Статус по умолчанию: Accepted (принята психологом)
5. ✅ Venue обязательно: для Offline автоматически берется office психолога
6. ✅ scheduled_time обязательно: время назначенной встречи (timezone-aware)
7. ✅ last_change_time автоматически обновляется (timezone-aware)
8. ✅ remind_time опционально: время напоминания (timezone-aware)
9. ✅ comment опционально: комментарий к записи
10. ✅ Валидация времени: scheduled_time не может быть в прошлом
11. ✅ Валидация remind_time: должно быть раньше scheduled_time и не в прошлом

### Психологи

1. ✅ Психолог имеет отдельный ID (не совпадает с user_id)
2. ✅ user_id - Foreign Key к users (unique, обязательно)
3. ✅ При удалении пользователя профиль психолога удаляется (CASCADE)
4. ✅ При создании психолога автоматически назначается роль `psychologist`
5. ✅ При удалении профиля психолога роль `psychologist` убирается
6. ✅ Проверка роли psychologist реализована при создании записей
7. ✅ Управление психологами требует разрешения `psychologists.manage`

### Отзывы

1. ✅ Один отзыв на одну встречу
2. ✅ При удалении встречи отзыв удаляется

### Роли и разрешения

1. ✅ Пользователь может иметь несколько ролей
2. ✅ Роли хранятся в таблице `roles` с полями id, code, name, description
3. ✅ Связь many-to-many через таблицу `users_roles`
4. ✅ Разрешения хранятся в таблице `permissions`
5. ✅ Связь роли и разрешений через таблицу `roles_permissions`
6. ✅ При регистрации пользователь автоматически получает роль `user`
7. ✅ Декоратор `@require_permission` для защиты endpoint'ов

---

## Валидация данных

### Уровни валидации

#### 1. Pydantic (Schemas)
- Формат email
- Формат телефона (E164)
- Длина строк
- Обязательные поля
- Типы данных

**Пример**:
```python
class UserCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    phone_number: PhoneNumber
    password: str = Field(min_length=8, max_length=64)
```

#### 2. Service Layer
- Бизнес-правила
- Проверка существования связанных объектов
- Логические ограничения

**Пример**:
```python
if patient_id == therapist_id:
    raise ValueError("Нельзя записаться к самому себе")
```

#### 3. Database Layer
- Уникальность
- Foreign Key constraints
- NOT NULL constraints
- CASCADE правила

---

## Транзакции и целостность данных

### Использование транзакций

```python
async with get_async_db() as session:
    try:
        # Операции с БД
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise
```

**Важно**:
- Все операции в одной сессии выполняются атомарно
- При ошибке происходит rollback
- Транзакции обеспечивают консистентность данных

### CASCADE удаление

При удалении пользователя автоматически удаляются:
- Все его роли
- Профиль психолога (если есть)
- Все встречи (как пациента и как терапевта)
- Отзывы о его встречах

---

## Безопасность

### Защита паролей

1. **Хеширование**: bcrypt с автоматической солью
2. **Никогда не возвращаем**: пароль не включается в API ответы
3. **Проверка**: только через bcrypt.verify()

### JWT токены

**Access Token**:
```python
{
  "sub": "user_id",           # Subject - ID пользователя (UUID)
  "exp": 1697123456,          # Expiration time (timestamp)
  "iat": 1697037056           # Issued at (timestamp)
}
```

**Refresh Token**:
```python
{
  "sub": "user_id",           # Subject - ID пользователя (UUID)
  "exp": 1699715456,          # Expiration time (timestamp, +30 дней)
  "iat": 1697037056           # Issued at (timestamp)
}
```

**Параметры**:
- Алгоритм: HS256 (HMAC-SHA256)
- Secret key: хранится в переменных окружения (`SECRET_KEY`)
- Access token TTL: 30 минут (по умолчанию, `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Refresh token TTL: 30 дней (по умолчанию, `REFRESH_TOKEN_EXPIRE`)
- Оба токена проверяют подпись, exp и iat при декодировании

### HTTP-only Cookies

**Access Token Cookie**:
```python
response.set_cookie(
    key="access_token",
    value=token,
    httponly=True,      # Защита от XSS
    secure=False,       # ⚠️ Для разработки! В продакшене True
    # samesite="None",  # ⚠️ Закомментировано для разработки
    expires=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE)
)
```

**Refresh Token Cookie**:
```python
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,      # Защита от XSS
    secure=True,        # Всегда True для refresh token
    samesite="None",    # Для кросс-доменных запросов
    expires=datetime.now(timezone.utc) + timedelta(days=30)
)
```

**Особенности**:
- Оба токена недоступны JavaScript (HttpOnly)
- Refresh token всегда с флагом Secure
- Access token в разработке без Secure для удобства
- При выходе оба cookie удаляются

---

## Реализованные возможности

### Аутентификация и безопасность
1. ✅ **JWT токены** - Access (30 мин) и Refresh (30 дней) tokens
2. ✅ **HttpOnly cookies** - Защита от XSS атак
3. ✅ **Bcrypt** - Безопасное хеширование паролей
4. ✅ **RBAC система** - Роли и разрешения с детальным контролем доступа
5. ✅ **Permission декоратор** - `@require_permission` для защиты endpoints
6. ✅ **Refresh токен** - Обновление access token без повторного входа
7. ✅ **Path Traversal защита** - Полная защита images endpoint

### Бизнес-логика
8. ✅ **Валидация времени** - Проверка scheduled_time и remind_time
9. ✅ **Timezone-aware datetime** - Все временные поля с timezone
10. ✅ **Автоматическое управление ролями** - При создании/удалении психолога
11. ✅ **Venue автоматизация** - Для Offline берется office психолога
12. ✅ **Проверка существования** - Пациента и психолога при создании записи
13. ✅ **Проверка статуса** - Нельзя отменить уже отмененную или завершенную запись

### Архитектура и инфраструктура
14. ✅ **Логирование** - Полная система логирования с настраиваемыми уровнями
15. ✅ **Миграции БД** - Alembic для версионирования схемы
16. ✅ **Кастомные исключения** - Типизированная обработка ошибок в сервисном слое
17. ✅ **Структурированная архитектура** - Разделение на репозитории/сервисы/контроллеры
18. ✅ **Docker** - Контейнеризация приложения и PostgreSQL
19. ✅ **Makefile** - Автоматизация команд (миграции, запуск)
20. ✅ **Пагинация** - Для списков психологов (skip/take с ограничениями)
21. ✅ **Eager loading** - Оптимизация запросов (joinedload/selectinload)
22. ✅ **Модульная структура** - Разделение по функциональности (users/, psychologists/, rbac/)

### Тестирование
23. ✅ **Unit тесты** - Для пользователей, токенов, безопасности
24. ✅ **Security тесты** - Path traversal, null byte injection, расширения файлов
25. ✅ **Token expiration тесты** - Проверка истечения токенов

### Управление данными
26. ✅ **CRUD для психологов** - Создание, чтение, обновление, удаление
27. ✅ **CRUD для записей** - С валидацией и проверкой прав
28. ✅ **Управление ролями** - Назначение и удаление ролей
29. ✅ **Cascade удаление** - Корректная очистка связанных данных

# Компоненты системы

## Обзор компонентов

Система состоит из следующих основных компонентов:

```
┌─────────────────────────────────────────────────┐
│                   FastAPI App                   │
│                  (main.py)                      │
└────────┬───────────────────────────┬────────────┘
         │                           │
         ▼                           ▼
┌─────────────────┐         ┌─────────────────────┐
│  API Routers    │         │   Middleware        │
│  (routes/)      │         │   (CORS, Auth)      │
└────────┬────────┘         └─────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│             Controllers (routes/controllers/)    │
│  ┌──────────┬──────────┬──────────┬──────────┐ │
│  │  Users   │  Appts   │Therapists│ Reviews  │ │
│  └──────────┴──────────┴──────────┴──────────┘ │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│             Services (services/)                 │
│  ┌──────────┬──────────┬──────────┬──────────┐ │
│  │  Users   │  Appts   │Therapists│ Reviews  │ │
│  └──────────┴──────────┴──────────┴──────────┘ │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│           Repositories (repositories/)           │
│  ┌──────────┬──────────┬──────────┬──────────┐ │
│  │  Users   │  Appts   │Therapists│ Reviews  │ │
│  └──────────┴──────────┴──────────┴──────────┘ │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│              Models (models/)                    │
│  ┌──────────┬──────────┬──────────┬──────────┐ │
│  │  User    │Appointment│Therapist │ Review   │ │
│  └──────────┴──────────┴──────────┴──────────┘ │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│              PostgreSQL Database                 │
└─────────────────────────────────────────────────┘
```

---

## 1. Main Application (main.py)

**Файл**: `psychohelp/main.py`

**Ответственность**:
- Создание и настройка FastAPI приложения
- Подключение роутеров
- Настройка CORS
- Инициализация логирования
- Инициализация БД при старте

### Инициализация логирования

```python
log_level = os.getenv("LOG_LEVEL", "DEBUG")
log_file_path = os.getenv("LOG_FILE")

setup_logging(
    level=log_level,
    log_file=Path(log_file_path) if log_file_path else None,
)

logger = get_logger(__name__)
```

**Особенности**:
- Логи настраиваются до создания приложения
- Уровень и путь файла конфигурируются через переменные окружения
- Логгер доступен во всех модулях приложения

### Основные функции

#### `get_application() -> FastAPI`
Создает и настраивает экземпляр приложения.

**Настройки**:
```python
application = FastAPI()
application.include_router(api_router)

# CORS Configuration
application.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://psychohelp.example.com",
        "https://185.128.105.126",
        "http://localhost:3000",
        "http://localhost:8000",
        # ... другие origins
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### `reset_database(engine: AsyncEngine) -> None`
Удаляет и пересоздает все таблицы БД.

```python
async def reset_database(engine: AsyncEngine) -> None:
    logger.warning("Resetting database - dropping all tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database reset completed")
```

**Логирование**:
- Warning при начале сброса БД
- Info после успешного завершения

#### Lifecycle Events
```python
@application.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting application")
    if RESET_DB_ON_START:
        await reset_database(engine)
    logger.info("Application started successfully")

@application.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down application")
```

#### `main() -> None`
Точка входа для запуска приложения.

```python
def main() -> None:
    uvicorn.run(
        "psychohelp.main:app",
        host="0.0.0.0",
        reload=True,
        log_config=None,  # Используем свою конфигурацию логов
        log_level=log_level.lower(),
    )
```

---

## 2. Configuration (config/)

### database.py

**Файл**: `psychohelp/config/database.py`

**Ответственность**:
- Конфигурация подключения к БД
- Управление сессиями
- Создание Base для ORM моделей

#### Config Class
```python
class Config:
    POSTGRES_USER = os.getenv("POSTGRES_USER", "myuser")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "mypassword")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "mydatabase")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = "5432"  # Фиксированный порт для Docker
    
    DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:..."
```

#### Async Session Manager
```python
@asynccontextmanager
async def get_async_db():
    session: AsyncSession = async_session()
    try:
        yield session
    except exc.SQLAlchemyError:
        await session.rollback()
        raise
    finally:
        await session.close()
```

**Использование**:
```python
async with get_async_db() as session:
    result = await session.execute(query)
```

---

### __init__.py

**Файл**: `psychohelp/config/__init__.py`

**Статус**: Пустой файл (только package marker)

**⚠️ Важно**: Константы для JWT и настройки находятся в `config.database.Config` классе, а не в `__init__.py`.

**Правильный импорт**:
```python
# Импорт конфигурации
from psychohelp.config.database import config

# Использование
config.SECRET_KEY
config.ALGORITHM
config.ACCESS_TOKEN_EXPIRE_MINUTES
config.REFRESH_TOKEN_EXPIRE
```

**Примечание**: В коде есть несоответствие - в `routes/controllers/__init__.py` импортируются `ACCESS_TOKEN_EXPIRE` и `REFRESH_TOKEN_EXPIRE` из `psychohelp.config`, но этот файл пустой. Это требует исправления.

---

### logging.py

**Файл**: `psychohelp/config/logging.py`

**Ответственность**:
- Настройка системы логирования приложения
- Конфигурация обработчиков логов
- Управление уровнями логирования

#### setup_logging()
Настраивает логирование для всего приложения.

**Параметры**:
- `level`: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
- `log_file`: Опциональный путь к файлу логов
- `format_string`: Формат сообщений

**Особенности**:
- Логи выводятся в stdout
- Опционально в файл
- Подавляет verbose логи SQLAlchemy и Uvicorn

```python
setup_logging(
    level="DEBUG",
    log_file=Path("/path/to/logs.log"),
)
```

#### get_logger()
Возвращает логгер для модуля.

```python
logger = get_logger(__name__)
logger.info("Application started")
logger.error("Error occurred", exc_info=True)
```

**Использование в коде**:
```python
from psychohelp.config.logging import get_logger

logger = get_logger(__name__)
logger.info("Processing request")
```

---

## 3. Models (models/)

ORM модели, представляющие таблицы БД.

### users.py

**Класс**: `User`

**Описание**: Базовая модель пользователя

**Ключевые поля**:
- `id`: UUID (Primary Key)
- `first_name`: String(50) - Имя (обязательно)
- `middle_name`: String(50) - Отчество (опционально)
- `last_name`: String(50) - Фамилия (обязательно)
- `email`: String(64) - Email (unique, **обязательно**) - используется для входа
- `phone_number`: String(20) - Телефон в формате E164 (обязательно)
- `password`: String(64) - Хешированный пароль bcrypt (обязательно)
- `social_media`: String(50) - Ссылки на соцсети (опционально)

**Relationships**:
```python
roles = relationship("Role", secondary="users_roles", back_populates="users")
appointments_as_patient = relationship("Appointment", foreign_keys="[Appointment.patient_id]", back_populates="patient")
psychologist_info = relationship("Psychologist", back_populates="user", uselist=False)  # One-to-One
```

---

### psychologists.py

**Класс**: `Psychologist`

**Описание**: Расширенная информация о психологах

**Особенности**:
- `id` - UUID (Primary Key, отдельный от user_id)
- `user_id` - Foreign Key к `users.id` (unique, обязательно)
- One-to-One relationship с User через user_id
- CASCADE удаление при удалении User
- При создании профиля пользователь получает роль `psychologist`
- При удалении профиля роль `psychologist` убирается

**Ключевые поля**:
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key к users, unique)
- `experience`: Опыт работы (String 64)
- `qualification`: Квалификация и сертификаты (String 128)
- `consult_areas`: Области консультирования (String 128)
- `education`: Образование (String 127)
- `office`: Номер кабинета (String 128)
- `description`: Полное описание (String 256)
- `short_description`: Краткое описание (String 2047)
- `photo`: Путь к фото (String 127, опционально)

**Relationships**:
```python
user = relationship("User", back_populates="psychologist_info")
appointments = relationship("Appointment", back_populates="psychologist")
```

---

### appointments.py

**Класс**: `Appointment`

**Описание**: Записи на консультации

**Enum Types**:
```python
class AppointmentType(enum.Enum):
    Offline = "Offline"  # Очная встреча
    Online = "Online"    # Онлайн-консультация

class AppointmentStatus(enum.Enum):
    Approved = "Approved"    # Одобрена (создана)
    Accepted = "Accepted"    # Принята психологом
    Cancelled = "Cancelled"  # Отменена
    Done = "Done"            # Завершена
```

**Ключевые поля**:
- `id`: UUID (Primary Key)
- `patient_id`: Foreign Key к users (пациент)
- `psychologist_id`: Foreign Key к psychologists (психолог)
- `type`: Тип встречи (Online/Offline)
- `status`: Статус записи
- `reason`: Причина обращения (String 64, опционально)
- `scheduled_time`: Время назначенной встречи (DateTime with timezone, обязательно)
- `remind_time`: Время напоминания (DateTime with timezone, опционально)
- `last_change_time`: Время последнего изменения (DateTime with timezone, обязательно)
- `venue`: Место встречи - кабинет/ссылка (String 128, обязательно)
- `comment`: Комментарий к записи (String 512, опционально)

**Relationships**:
```python
patient = relationship("User", foreign_keys=[patient_id], back_populates="appointments_as_patient")
psychologist = relationship("Psychologist", foreign_keys=[psychologist_id], back_populates="appointments")
review = relationship("Review", back_populates="appointment", uselist=False)  # One-to-One
```

**Каскадное удаление**: 
- При удалении User удаляются все его записи как пациента
- При удалении Psychologist удаляются все его записи

**Валидация**:
- scheduled_time не может быть в прошлом
- remind_time должно быть раньше scheduled_time и не в прошлом
- Для Online встреч venue обязательно (ссылка)
- Для Offline встреч venue автоматически берется из office психолога

---

### reviews.py

**Класс**: `Review`

**Описание**: Отзывы о консультациях

**Особенности**:
- `appointment_id` как Primary Key
- One-to-One с Appointment
- CASCADE удаление при удалении Appointment

**Ключевые поля**:
- `appointment_id`: UUID (Primary Key, Foreign Key к appointments)
- `time`: Время создания отзыва
- `content`: Содержание отзыва

**Relationships**:
```python
appointment = relationship("Appointment", back_populates="review")
```

---

### roles.py

**Класс**: `Role`

**Описание**: Роли пользователей в системе RBAC

**Enum Type**:
```python
class RoleCode(str, Enum):
    USER = "user"                        # Обычный пользователь (студент)
    PSYCHOLOGIST = "psychologist"        # Психолог
    ADMIN = "admin"                      # Администратор
    CONTENT_MANAGER = "content_manager"  # Контент-менеджер
```

**Ключевые поля**:
- `id`: UUID (Primary Key)
- `code`: RoleCode Enum (unique, обязательно, индексируется)
- `name`: String(100) - Название роли (обязательно)
- `description`: String(255) - Описание роли (опционально)

**Промежуточная таблица `users_roles`**:
- `user_id`: UUID (Foreign Key к users, CASCADE, часть PK)
- `role_id`: UUID (Foreign Key к roles, CASCADE, часть PK)
- `assigned_at`: DateTime with timezone - Время назначения роли

**Особенности**:
- Роли имеют собственные ID (не композитный ключ)
- Один пользователь может иметь несколько ролей
- Many-to-Many relationship через промежуточную таблицу `users_roles`
- CASCADE удаление связей при удалении User или Role
- При регистрации пользователь автоматически получает роль `user`

**Relationships**:
```python
permissions = relationship("Permission", secondary=roles_permissions, back_populates="roles")
users = relationship("User", secondary=users_roles, back_populates="roles")
```

---

### permissions.py

**Класс**: `Permission`

**Описание**: Разрешения (права доступа) в системе RBAC

**Ключевые поля**:
- `id`: UUID (Primary Key)
- `code`: PermissionCode Enum (unique, обязательно, индексируется)
- `name`: String(100) - Название разрешения (обязательно)
- `description`: String(255) - Описание разрешения (опционально)
- `resource`: String(50) - Ресурс, к которому относится (обязательно, индексируется)

**Промежуточная таблица `roles_permissions`**:
- `role_id`: UUID (Foreign Key к roles, CASCADE, часть PK)
- `permission_id`: UUID (Foreign Key к permissions, CASCADE, часть PK)

**Relationships**:
```python
roles = relationship("Role", secondary="roles_permissions", back_populates="permissions")
```

**Примеры permissions**:
- `appointments.create_own` (resource: "appointments")
- `psychologists.manage` (resource: "psychologists")
- `users.edit_own_profile` (resource: "users")
- И многие другие (см. constants/rbac.py)

---

## 4. Repositories (repositories/)

Слой доступа к данным. Все взаимодействия с БД инкапсулированы здесь.

### Общие паттерны

#### CRUD операции
Каждый репозиторий реализует базовые операции:
- `create_*` - создание
- `get_*_by_id` - получение по ID
- `get_*_by_*` - получение по другим параметрам
- `update_*` - обновление
- `delete_*` - удаление

#### Использование AsyncSession
```python
async with get_async_db() as session:
    result = await session.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    return user
```

---

### repositories/__init__.py

**Утилиты безопасности**:

#### `create_access_token(sub: str) -> str`
Создает JWT access token.

**Параметры payload**:
- `sub`: User ID (subject) - автоматически
- `exp`: Время истечения - now + 30 минут (по умолчанию)
- `iat`: Время выдачи - now

```python
encoded = jwt.encode(
    {"sub": str(sub), "exp": expire, "iat": now},
    config.SECRET_KEY,
    algorithm=config.ALGORITHM,
)
```

#### `create_refresh_token(sub: str) -> str`
Создает JWT refresh token.

**Параметры payload**:
- `sub`: User ID (subject) - автоматически
- `exp`: Время истечения - now + 30 дней (по умолчанию)
- `iat`: Время выдачи - now

#### `refresh_access_token(refresh_token: str) -> str`
Обновляет access token используя refresh token.

**Процесс**:
1. Декодирует и валидирует refresh token
2. Извлекает user_id из sub
3. Генерирует новый access token
4. Возвращает новый access token

**Исключения**:
- `jwt.InvalidTokenError` - если refresh token невалидный
- `jwt.ExpiredSignatureError` - если refresh token истек

#### `get_user_id_from_token(token: str) -> UUID`
Декодирует токен и извлекает User ID.

**Проверки**:
- Подпись
- Время истечения
- Время выдачи

#### `hash_password(password: str) -> str`
Хеширует пароль с использованием bcrypt.

#### `verify_password(plain: str, hashed: str) -> bool`
Проверяет пароль.

---

### repositories/users.py

**Основные функции**:

#### `create_user(...) -> User`
Создает нового пользователя.

**Валидация**:
- Проверка уникальности email
- Хеширование пароля должно быть выполнено до вызова

#### `get_user_by_id(user_id: UUID) -> User | None`
Получает пользователя по ID.

#### `get_user_by_email(email: str) -> User | None`
Получает пользователя по email.

#### `get_user_by_token(token: str) -> User | None`
Получает пользователя по JWT токену.

**Процесс**:
1. Декодирует токен
2. Извлекает user_id
3. Загружает пользователя из БД

---

### repositories/appointments.py

**Основные функции**:

#### `create_appointment(...) -> Appointment`
Создает новую запись.

**Автоматические поля**:
- `id`: генерируется UUID
- `status`: устанавливается "Approved"
- `last_change_time`: текущее время

#### `get_appointment_by_id(id: UUID) -> Appointment | None`
Получает запись по ID.

#### `get_appointments_by_user_id(user_id: UUID) -> list[Appointment]`
Получает все записи пользователя (как пациент и как терапевт).

**Запрос**:
```python
appointments = await session.execute(
    select(Appointment).where(
        (Appointment.patient_id == user_id) | 
        (Appointment.therapist_id == user_id)
    )
)
```

#### `cancel_appointment_by_id(appointment_id: UUID, current_user_id: UUID) -> Appointment`
Отменяет запись.

**Действия**:
1. Находит запись по ID
2. Проверяет, что пациент совпадает с current_user_id
3. Проверяет статус (не Cancelled)
4. Устанавливает status = "Cancelled"
5. Обновляет last_change_time

**Исключения**:
- `ValueError("Встреча не найдена")` - запись не существует
- `ValueError("Только пациент может отменить свою запись")` - неверный пользователь
- `ValueError("Встреча уже отменена")` - уже отменена

**⚠️ Важно**: В сервисном слое используются функции `cancel_appointment_by_patient` и `get_appointment_for_user`, которые отсутствуют в репозитории. Это несоответствие требует исправления.

---

### repositories/psychologists/exceptions.py

**Кастомные исключения для психологов**:

```python
class UserNotFoundForPsychologistException(Exception):
    """Пользователь не найден при создании психолога"""
    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(f"User with ID {user_id} not found")

class PsychologistRoleNotFoundException(Exception):
    """Роль psychologist не найдена в БД"""
    super().__init__("Role 'psychologist' not found in database")

class PsychologistNotFoundException(Exception):
    """Психолог не найден"""
    def __init__(self, psychologist_id):
        self.psychologist_id = psychologist_id

class PsychologistAlreadyExistsException(Exception):
    """Психолог для пользователя уже существует"""
    def __init__(self, user_id):
        self.user_id = user_id
```

---

### repositories/psychologists/psychologists.py

**Основные функции**:

#### `get_psychologist_by_id(id: UUID) -> Psychologist | None`
Получает информацию о психологе с eager loading данных пользователя.

**Особенности**:
- Использует `selectinload` для загрузки связи с User
- Возвращает ORM объект или None

#### `get_psychologists(skip: int = 0, take: int = 10) -> list[Psychologist]`
Получает список психологов с пагинацией.

**Параметры**:
- `skip` - Offset для пагинации (по умолчанию 0)
- `take` - Limit для пагинации (по умолчанию 10)

**Особенности**:
- Использует `joinedload` для оптимизации загрузки User данных
- Поддерживает пагинацию через offset/limit

#### `create_psychologist(user_id: UUID, psychologist_data: dict) -> Psychologist`
Создает профиль психолога.

**Процесс**:
1. Проверяет существование пользователя
2. Проверяет, что профиль не существует
3. Создает профиль психолога
4. Загружает роль `psychologist`
5. Назначает роль пользователю (если еще нет)
6. Возвращает созданный профиль с загруженными связями

**Исключения**:
- `UserNotFoundForPsychologistException` - пользователь не найден
- `PsychologistAlreadyExistsException` - профиль уже существует
- `PsychologistRoleNotFoundException` - роль не найдена в БД

#### `delete_psychologist(psychologist_id: UUID) -> bool`
Удаляет профиль психолога и убирает роль.

**Процесс**:
1. Находит психолога с загруженными user и roles
2. Удаляет роль `psychologist` у пользователя
3. Удаляет профиль психолога
4. Возвращает True при успехе, False если не найден

**Реализовано**:
- ✅ Пагинация
- ✅ Eager loading (joinedload, selectinload)
- ✅ CRUD операции
- ✅ Автоматическое управление ролями

---

### repositories/reviews.py

**Основные функции**:

#### `get_review(appointment_id: UUID) -> Review | None`
Получает отзыв о встрече по ID записи.

---

### repositories/rbac/exceptions.py

**Кастомные исключения для RBAC**:

```python
class UserNotFoundException(Exception):
    """Пользователь не найден"""
    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(f"User with ID {user_id} not found")

class RoleNotFoundException(Exception):
    """Роль не найдена"""
    def __init__(self, role_code: RoleCode):
        self.role_code = role_code
        super().__init__(f"Role '{role_code.value}' not found")
```

---

### repositories/rbac/rbac.py

**Основные функции**:

#### `get_user_permissions(user_id: UUID) -> list[str]`
Получает все коды разрешений пользователя через его роли.

**Процесс**:
1. Загружает пользователя с eager loading ролей и разрешений
2. Собирает уникальные коды разрешений из всех ролей
3. Возвращает список строк (permission codes)

**Особенности**:
- Использует `selectinload` для оптимизации (User -> Roles -> Permissions)
- Возвращает пустой список если пользователь не найден
- Убирает дубликаты через set

#### `assign_role_to_user(user_id: UUID, role_code: RoleCode) -> bool`
Назначает роль пользователю.

**Процесс**:
1. Загружает пользователя с ролями
2. Загружает роль по code
3. Проверяет, что роль еще не назначена
4. Добавляет роль в список ролей пользователя
5. Сохраняет изменения

**Возвращает**:
- `True` - роль успешно назначена
- `False` - роль уже была назначена

**Исключения**:
- `UserNotFoundException` - пользователь не найден
- `RoleNotFoundException` - роль не найдена

#### `remove_role_from_user(user_id: UUID, role_code: RoleCode) -> bool`
Убирает роль у пользователя.

**Процесс**:
1. Загружает пользователя с ролями
2. Ищет роль в списке ролей пользователя
3. Удаляет роль из списка
4. Сохраняет изменения

**Возвращает**:
- `True` - роль успешно убрана
- `False` - роль не была назначена

**Исключения**:
- `UserNotFoundException` - пользователь не найден

---

## 5. Services (services/)

Бизнес-логика приложения. Координирует работу репозиториев и применяет бизнес-правила.

### Паттерн использования

```
Controller → Service → Repository → Database
```

**Преимущества**:
- Разделение ответственности
- Переиспользование логики
- Упрощение тестирования
- Легкость добавления сложной логики

---

### services/users/

**Структура**: Модуль разделен на несколько файлов для лучшей организации кода.

#### services/users/users.py

**Основные функции**:

##### `register_user(...) -> tuple[User, str]`
Регистрирует нового пользователя.

**Процесс**:
1. Хеширует пароль
2. Создает пользователя через репозиторий
3. Генерирует JWT токен
4. Возвращает (user, token)

**Бизнес-логика**:
- Автоматическое хеширование пароля
- Генерация токена для автоматической аутентификации

##### `login_user(email: str, password: str) -> UserWithToken`
Аутентифицирует пользователя.

**Процесс**:
1. Получает пользователя по email
2. Проверяет пароль
3. Генерирует токен
4. Возвращает `UserWithToken` или выбрасывает исключение

**Бизнес-логика**:
- Проверка пароля через bcrypt
- Выбрасывает `UserNotFound` если пользователь не найден
- Выбрасывает `WrongPassword` если пароль неверный

**Исключения**:
```python
raise exceptions.UserNotFound()  # Пользователь не найден
raise exceptions.WrongPassword()  # Неверный пароль
```

##### `get_user_by_*(...) -> User | None`
Прокси-функции к репозиторию.

**Цель**: Единая точка доступа к данным пользователей

#### services/users/exceptions.py

**Кастомные исключения**:

```python
class UserNotFound(Exception):
    """Выбрасывается, когда пользователь не найден"""
    pass

class WrongPassword(Exception):
    """Выбрасывается при неверном пароле"""
    pass
```

**Использование**:
Позволяет контроллерам обрабатывать ошибки более специфично.

#### services/users/models.py

**Модели данных для сервисного слоя**:

```python
@dataclass(frozen=True, slots=True)
class UserWithToken:
    user: models.User
    token: str
```

**Назначение**: Типобезопасная передача данных между слоями приложения.

---

### services/appointments.py

**Основные функции**:

#### `create_appointment(...) -> Appointment`
Создает новую запись.

**Бизнес-логика**:
1. Проверяет, что пациент ≠ терапевт
2. Устанавливает статус "Approved"
3. Устанавливает текущее время в last_change_time
4. Устанавливает venue (если не указано)

**Валидация**:
```python
if patient_id == therapist_id:
    raise ValueError("Пациент не может быть терапевтом")
```

#### `cancel_appointment_by_id(id: UUID) -> None`
Отменяет запись.

**Бизнес-логика**:
1. Проверяет существование записи
2. Проверяет, что статус не "Cancelled" или "Done"
3. Обновляет статус и время

#### `get_appointments_by_token(token: str) -> list[Appointment]`
Получает записи текущего пользователя.

**Процесс**:
1. Декодирует токен
2. Извлекает user_id
3. Получает все записи пользователя

---

### services/psychologists.py

**Основные функции**:

#### `get_psychologist_by_id(psychologist_id: UUID) -> Psychologist | None`
Получает информацию о психологе.

**Процесс**:
- Вызывает репозиторий для получения ORM объекта
- Возвращает ORM модель или None

#### `get_psychologists(skip: int = 0, take: int = 10) -> list[Psychologist]`
Получает список психологов с пагинацией.

**Параметры**:
- `skip` - Количество записей для пропуска (offset)
- `take` - Количество записей для возврата (limit)

**Возвращает**: Список ORM моделей Psychologist.

**Особенности**:
- Поддержка пагинации (skip/take)
- Eager loading связанных данных пользователя

#### `create_psychologist(user_id: UUID, psychologist_data: dict) -> Psychologist`
Создает профиль психолога.

**Параметры**:
- `user_id` - ID пользователя
- `psychologist_data` - Словарь с данными психолога

**Процесс**:
- Вызывает репозиторий для создания
- Автоматически назначается роль `psychologist`

**Исключения**:
- `UserNotFoundForPsychologistException`
- `PsychologistRoleNotFoundException`
- `PsychologistAlreadyExistsException`

#### `delete_psychologist(psychologist_id: UUID) -> bool`
Удаляет профиль психолога.

**Возвращает**: True если удален, False если не найден

---

### services/reviews.py

**Основные функции**:

#### `get_review_by_appointment_id(id: UUID) -> Review | None`
Получает отзыв о встрече.

---

### services/rbac/permissions.py

**Основные функции**:

#### `get_user_permissions(user_id: UUID) -> list[str]`
Получает все коды разрешений пользователя.
- Прокси к репозиторию
- Возвращает список строк с кодами разрешений

#### `user_has_permission(user_id: UUID, permission_code: PermissionCode) -> bool`
Проверяет наличие конкретного разрешения у пользователя.
- Загружает все разрешения
- Проверяет наличие указанного кода
- Возвращает True/False

#### `user_has_any_permission(user_id: UUID, permission_codes: list[PermissionCode]) -> bool`
Проверяет наличие хотя бы одного из указанных разрешений.
- Полезно для "ИЛИ" логики
- Возвращает True при первом найденном разрешении

#### `require_permission(permission_code: PermissionCode)`
Декоратор для защиты endpoint'ов.

**Процесс**:
1. Извлекает Request из аргументов функции
2. Получает access_token из cookie
3. Декодирует токен и извлекает user_id
4. Проверяет наличие разрешения
5. Вызывает функцию если разрешение есть
6. Возвращает 401/403 если нет доступа

**Использование**:
```python
@router.post("/create")
@require_permission(PermissionCode.APPOINTMENTS_CREATE_OWN)
async def create_appointment(request: Request, ...):
    # Доступ только с разрешением
    pass
```

**Обработка ошибок**:
- `401` - Нет токена или токен невалидный
- `403` - Недостаточно прав

---

## 6. Routes/Controllers (routes/controllers/)

API endpoints. Обрабатывают HTTP запросы и формируют ответы.

### Общие паттерны

#### Структура контроллера
```python
router = APIRouter(prefix="/resource", tags=["resource"])

@router.get("/{id}")
async def get_resource(id: UUID):
    resource = await service.get_resource(id)
    if not resource:
        raise HTTPException(404, detail="Not found")
    return resource
```

#### Обработка ошибок
```python
try:
    result = await service.create_resource(...)
except ValueError as e:
    raise HTTPException(400, detail=str(e))
```

---

### routes/controllers/__init__.py

**Утилиты**:

#### `set_token_in_cookie(response: Response, token: str)`
Устанавливает JWT токен в HTTP-only cookie.

**Параметры cookie**:
```python
response.set_cookie(
    key="access_token",
    value=token,
    expires=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE),
    httponly=True,
    secure=False,  # Для разработки, в продакшене должно быть True
    # samesite="None",  # Закомментировано для разработки
)
```

---

### routes/controllers/users.py

**Router**: `/users`

**Endpoints**:

#### `GET /user`
Получить текущего пользователя (требует аутентификации).
- Извлекает access_token из cookie
- Возвращает данные пользователя или 401/404

#### `GET /user/{id}`
Получить пользователя по ID.
- Публичный endpoint
- Возвращает данные пользователя или 404

#### `POST /register`
Регистрация нового пользователя.
- Валидирует данные через `UserCreateRequest`
- Хеширует пароль
- Создает пользователя с ролью `user`
- Генерирует access и refresh tokens
- Устанавливает оба токена в cookies
- Возвращает 201 CREATED с данными пользователя

#### `POST /login`
Вход в систему.
- Валидирует email и пароль
- Генерирует access и refresh tokens
- Устанавливает оба токена в cookies
- Возвращает 200 OK с данными пользователя

#### `POST /logout`
Выход из системы.
- Требует access_token в cookie
- Удаляет оба cookie (access_token и refresh_token)
- Возвращает 200 OK

#### `POST /refresh`
Обновление access token.
- Извлекает refresh_token из cookie
- Валидирует refresh token
- Генерирует новый access token
- Устанавливает новый access token в cookie
- Возвращает 200 OK с данными пользователя

**Особенности**:
- Cookie-based authentication (HttpOnly)
- Валидация через Pydantic
- Разделение публичных и защищенных endpoints
- Логирование всех операций через `get_logger(__name__)`
- Обработка кастомных исключений из сервисного слоя
- Поддержка refresh token для обновления доступа

**Обработка ошибок**:
```python
# При регистрации
except ValueError as exc:
    raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

# При входе
except (users_exceptions.UserNotFound, users_exceptions.WrongPassword):
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Неверные данные")

# При обновлении токена
except users_exceptions.InvalidToken:
    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Недействительный токен обновления")
```

**Статус-коды**:
- `200 OK` - Успешный вход/выход/обновление токена
- `201 CREATED` - Успешная регистрация
- `401 UNAUTHORIZED` - Пользователь не авторизован / невалидный токен
- `403 FORBIDDEN` - Неверные учетные данные
- `404 NOT_FOUND` - Пользователь не найден
- `422 UNPROCESSABLE_ENTITY` - Ошибка валидации

---

### routes/controllers/appointments.py

**Router**: `/appointments`

**Endpoints**:

#### `GET /`
Получить список записей.
- Параметры: `user_id` (UUID, опционально)
- Если user_id не указан - возвращает записи текущего пользователя (требует auth)
- Если user_id указан - проверяет права доступа (свои записи или admin)
- Использует `get_optional_user` dependency

#### `POST /create`
Создать новую запись на прием.
- **Требует разрешение**: `appointments.create_own`
- Использует декоратор `@require_permission`
- Body: `AppointmentCreateRequest`
- Проверяет, что patient_id совпадает с current_user
- Валидирует scheduled_time (не в прошлом)
- Валидирует remind_time (раньше scheduled_time, не в прошлом)
- Для Offline автоматически берет office психолога
- Для Online требует venue

**Обработка ошибок**:
- `400` - Время в прошлом, некорректное напоминание, venue обязательно
- `403` - Попытка создать запись для другого пользователя
- `404` - Пациент или психолог не найден
- `422` - Пользователь не является психологом
- `500` - Неожиданная ошибка

#### `GET /{id}`
Получить информацию о конкретной записи.
- **Требует разрешение**: `appointments.view_own`
- Проверяет права доступа (свои записи)
- Использует `get_appointment_for_user`
- Возвращает 404 если не найдена или нет доступа

#### `PUT /{id}/cancel`
Отменить запись на прием.
- **Требует разрешение**: `appointments.cancel_own`
- Проверяет, что пользователь - пациент этой записи
- Устанавливает status = Cancelled
- Обновляет last_change_time

**Обработка ошибок**:
- `400` - Встреча не найдена, уже отменена, не пациент
- `401` - Не авторизован
- `403` - Недостаточно прав

**Особенности**:
- Защита через RBAC на всех endpoints
- Детальная валидация времени
- Логирование всех операций
- Проверка прав доступа к чужим записям

---

### routes/controllers/therapists.py

**Router**: `/therapists`

**Endpoints**:

#### `GET /{psychologist_id}`
Получить информацию о конкретном психологе.
- Публичный endpoint
- Возвращает 404 если не найден
- Использует `PsychologistResponse.from_orm_psychologist()`

#### `GET /`
Получить список всех психологов с пагинацией.
- Публичный endpoint
- Параметры: `skip` (≥0, по умолчанию 0), `take` (>0, ≤100, по умолчанию 10)
- Возвращает список психологов с данными пользователя
- Eager loading через `joinedload`

#### `POST /`
Создать профиль психолога.
- **Требует разрешение**: `psychologists.manage`
- Использует декоратор `@require_permission`
- Body: `PsychologistCreateRequest` (user_id + данные психолога)
- Автоматически назначает роль `psychologist`
- Возвращает 201 CREATED

**Обработка ошибок**:
- `404` - Пользователь не найден
- `400` - Психолог уже существует
- `500` - Роль psychologist не найдена в БД

#### `DELETE /{psychologist_id}`
Удалить профиль психолога.
- **Требует разрешение**: `psychologists.manage`
- Использует декоратор `@require_permission`
- Удаляет профиль и убирает роль `psychologist`
- Возвращает 404 если не найден

**Параметры пагинации**:
```
GET /therapists?skip=0&take=10
```
- `skip` (int, ≥0, по умолчанию 0) - Сколько записей пропустить
- `take` (int, >0, ≤100, по умолчанию 10) - Сколько записей вернуть

**Особенности**:
- Защита через RBAC (создание/удаление)
- Логирование всех операций через `get_logger(__name__)`
- Использует `joinedload` для загрузки связанных данных пользователя
- Автоматическое управление ролями

**Примеры**:
```bash
# Первые 10 психологов
GET /therapists

# Следующие 10 психологов
GET /therapists?skip=10&take=10

# Создать психолога (требует права)
POST /therapists
Body: {
  "user_id": "uuid",
  "experience": "10 лет",
  ...
}

# Удалить психолога (требует права)
DELETE /therapists/{id}
```

---

### routes/controllers/reviews.py

**Router**: `/reviews`

**Endpoints**:
- `GET /{review_id}` - Отзыв по ID

---

### routes/controllers/roles.py

**Router**: `/roles`

**Endpoints**:

#### `POST /{user_id}/assign`
Назначить роль пользователю.
- Body: `RoleAssignRequest` с полем `role_code`
- Принимает одну роль за раз
- Если роль уже назначена - возвращает информационное сообщение
- Возвращает 200 OK с сообщением

**Обработка ошибок**:
- `404` - Пользователь или роль не найдены
- `500` - Неожиданная ошибка

#### `POST /{user_id}/remove`
Убрать роль у пользователя.
- Body: `RoleRemoveRequest` с полем `role_code`
- Принимает одну роль за раз
- Если роль не была назначена - возвращает информационное сообщение
- Возвращает 200 OK с сообщением

**Обработка ошибок**:
- `404` - Пользователь не найден
- `500` - Неожиданная ошибка

**Особенности**:
- Использует enum `RoleCode` для безопасности
- Одна роль за запрос (не массив)
- Детальное логирование всех операций
- Идемпотентные операции (повторное назначение не ошибка)

**Примеры использования**:
```bash
# Назначить роль психолога
POST /roles/{user_id}/assign
Body: { "role_code": "psychologist" }

# Убрать роль администратора
POST /roles/{user_id}/remove
Body: { "role_code": "admin" }
```

**Доступные роли**:
- `user` - Обычный пользователь
- `psychologist` - Психолог
- `admin` - Администратор
- `content_manager` - Контент-менеджер

---

### routes/controllers/images.py

**Router**: `/image` (без префикса `/images`)

**Endpoints**:

#### `GET /image/{filename}`
Получить изображение по имени файла.
- Публичный endpoint
- Директория: `/srv/images` (настраивается через `IMAGE_DIR`)
- Поддерживаемые форматы: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.svg`, `.bmp`, `.ico`

**Безопасность (Path Traversal Protection)**:

1. **Проверка на подозрительные символы**:
   - Блокирует `..`, `/`, `\` в имени файла
   - Возвращает 400 при обнаружении

2. **Whitelist расширений**:
   - Только разрешенные форматы изображений
   - Проверка case-insensitive
   - Возвращает 400 для недопустимых типов

3. **Безопасный путь**:
   - Использует `os.path.basename()` для извлечения имени
   - Проверяет, что файл внутри базовой директории
   - Использует `.resolve()` и `.relative_to()` для валидации

4. **Обработка null bytes**:
   - Защита от null byte injection
   - Возвращает 400 при обнаружении

**Обработка ошибок**:
- `400` - Недопустимое имя файла, тип или символы
- `403` - Доступ за пределы базовой директории
- `404` - Файл не найден

**Особенности**:
- Автоматическое определение MIME типа
- Возврат через `FileResponse`
- Полное покрытие тестами безопасности
- Защита от всех известных векторов Path Traversal

**Примеры**:
```bash
# Получить изображение
GET /image/photo.jpg

# Попытка path traversal (блокируется)
GET /image/../../../etc/passwd  → 400

# Недопустимый тип (блокируется)
GET /image/script.js  → 400
```

---

## 7. Schemas (schemas/)

Pydantic модели для валидации и сериализации.

### Типы схем

#### Request Schemas
Для входящих данных (POST/PUT).

**Пример**:
```python
class UserCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)
```

#### Response Schemas
Для исходящих данных (GET).

**Пример**:
```python
class UserResponse(BaseModel):
    id: UUID
    first_name: str
    email: EmailStr
    
    class Config:
        from_attributes = True  # Для ORM моделей
```

#### Base Schemas
Полные модели с всеми полями.

---

### schemas/users.py

**Модели**:
- `UserCreateRequest` - Для регистрации
- `UserBase` - Полная модель с password
- `UserResponse` - Для ответов (без пароля)
- `LoginRequest` - Для входа
- `TokenResponse` - Ответ с токеном

**Валидаторы**:
- `EmailStr` - Pydantic email validator (nullable в схеме)
- `PhoneNumber` - Валидатор для E164 формата (из pydantic-extra-types)

**Настройки PhoneNumber**:
```python
PhoneNumber.phone_format = "E164"  # Формат +79001234567
PhoneNumber.default_region_code = "+7"  # Россия по умолчанию
```

**Особенности**:
- `email` **обязательный** (`EmailStr`, не None!)
- `middle_name` опциональный (`str | None`)
- `social_media` опциональный (`str | None`)
- Пароль минимум 8, максимум 256 символов
- Телефон валидируется в формате E164 (международный)
- Email валидируется через Pydantic EmailStr

---

### schemas/appointments.py

**Модели**:
- `AppointmentBase` - Полная модель для ответов
- `AppointmentCreateRequest` - Для создания записи

**Enum импорты**:
```python
from psychohelp.repositories.appointments import (
    AppointmentType,
    AppointmentStatus,
)
```

**Особенности**:
- `venue` может быть опциональным при создании (None для Offline)
- `reason` опциональный
- `remind_time` опциональный

---

## 8. Tests (tests/)

Тесты для проверки функциональности приложения.

### __init__.py

Содержит фабрику для создания HTTP клиента:
```python
def client():
    return httpx.AsyncClient(base_url="http://localhost:8000", follow_redirects=True)
```

### conftest.py

**Фикстуры**:

#### `async def user()`
Создает тестового пользователя:
- Регистрирует пользователя через API
- Проверяет успешную регистрацию (201)
- Сохраняет cookies для последующих запросов
- Возвращает данные пользователя

**Использование в тестах**:
```python
async def test_get_user(user):
    async with client() as c:
        r = await c.get(f"/users/user/{user['id']}")
        assert r.status_code == 200
```

### test_users.py

Тесты для пользовательских операций:
- `test_get_user` - Получение пользователя по ID и email
- Проверка валидации email
- Проверка валидации UUID
- Проверка 404 для несуществующих пользователей

### test_token_expiration.py

Тесты для проверки JWT токенов:

1. **`test_token_creation_with_configurable_expiration`**
   - Создание токена
   - Декодирование и проверка user_id

2. **`test_token_expiration_with_short_lifetime`**
   - Токен с коротким временем жизни (2 секунды)
   - Проверка валидности сразу после создания
   - Проверка истечения через 2 секунды

3. **`test_token_with_different_expiration_times`**
   - Проверка разных TTL (1, 5, 30, 60, 1440 минут)

4. **`test_invalid_token_handling`**
   - Пустой токен
   - Невалидный токен
   - Токен с неверной подписью

5. **`test_environment_variable_override`**
   - Проверка переопределения через переменные окружения

6. **`test_token_structure`**
   - Проверка структуры JWT (3 части)
   - Проверка payload (sub, exp, iat)
   - Проверка корректности exp

### test_images.py

Тесты безопасности для images endpoint:

#### TestImagesPathTraversal
1. **`test_valid_image_access`** - Легитимный доступ к изображению
2. **`test_path_traversal_with_dots`** - Блокировка `..` атак
3. **`test_path_traversal_with_slash`** - Блокировка абсолютных путей
4. **`test_invalid_file_extension`** - Блокировка недопустимых типов
5. **`test_valid_image_extensions`** - Разрешенные расширения
6. **`test_nonexistent_file`** - 404 для несуществующих файлов
7. **`test_double_extension_bypass_attempt`** - Двойное расширение
8. **`test_null_byte_injection`** - Null byte атаки

#### TestImagesSecurityHeaders
- **`test_correct_content_type`** - Проверка Content-Type

#### TestImagesEdgeCases
- **`test_empty_filename`** - Пустое имя файла
- **`test_filename_with_spaces`** - Имена с пробелами
- **`test_case_sensitivity`** - Регистронезависимость расширений

**Особенности тестов**:
- Использует временные директории (`tempfile`)
- Создает реальные файлы для тестирования
- Проверяет все известные векторы Path Traversal атак
- Использует `monkeypatch` для изменения `IMAGE_DIR`

---

## Взаимодействие компонентов

### Пример: Создание записи

```
1. HTTP Request
   POST /appointments/create
   Body: {patient_id, therapist_id, ...}

2. Controller (routes/controllers/appointments.py)
   - Получает Request Body
   - Валидирует через AppointmentCreateRequest
   - Вызывает service.create_appointment()

3. Service (services/appointments.py)
   - Применяет бизнес-правила
   - Проверяет patient_id ≠ therapist_id
   - Вызывает repository.create_appointment()

4. Repository (repositories/appointments.py)
   - Создает объект Appointment
   - Сохраняет в БД через SQLAlchemy
   - Возвращает созданный объект

5. Service
   - Получает результат
   - Возвращает в Controller

6. Controller
   - Сериализует через AppointmentBase
   - Возвращает HTTP Response
```

---

## Конфигурация и окружение

### Переменные окружения

```bash
# Database
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=mydatabase
POSTGRES_HOST=localhost
# POSTGRES_PORT фиксирован на 5432 в коде для Docker

# Application
RESET_DB_ON_START=false           # Сбрасывать БД при старте
RESET_COOKIE_ON_START=true        # Сбрасывать cookie при старте
APP_PORT=8000                      # Порт приложения
APP_HOST=127.0.0.1                # Хост приложения

# Logging
LOG_LEVEL=DEBUG                    # DEBUG, INFO, WARNING, ERROR
LOG_FILE=/path/to/logs.log        # Опционально, путь к файлу логов

# Security
SECRET_KEY=your-secret-key                  # Ключ для подписи JWT
JWT_ALGORITHM=HS256                         # Алгоритм JWT
ACCESS_TOKEN_EXPIRE_MINUTES=30              # Время жизни access token (минуты)
REFRESH_TOKEN_EXPIRE=30                     # Время жизни refresh token (дни)

# Images
IMAGE_DIR=/srv/images              # Директория для изображений
```

**Значения по умолчанию**:
- `POSTGRES_*`: Значения для локальной разработки
- `RESET_DB_ON_START`: `false` (не сбрасывать БД при старте)
- `RESET_COOKIE_ON_START`: `true` (сбрасывать cookie)
- `APP_PORT`: `8000`
- `APP_HOST`: `127.0.0.1`
- `LOG_LEVEL`: `DEBUG`
- `SECRET_KEY`: `"secret-key"` (⚠️ изменить в продакшене!)
- `JWT_ALGORITHM`: `HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES`: `30` минут
- `REFRESH_TOKEN_EXPIRE`: `30` дней (обратите внимание: в днях, не минутах!)
- `IMAGE_DIR`: `/srv/images`

**⚠️ Важно для продакшена**:
- Установить сильный `SECRET_KEY`
- Установить `RESET_DB_ON_START=false`
- Настроить `secure=True` для cookies в коде

### Docker

**Dockerfile**:
- Base: Python 3.13-slim
- Package manager: uv
- Workdir: /app
- Устанавливает зависимости из pyproject.toml
- CMD: запуск приложения через uv

**docker-compose.yml**:
- Service `app`: FastAPI приложение
  - Порт: `${APP_PORT}:8000`
  - Volume: текущая директория монтируется в `/app`
  - Volume: `./images:/srv/images` для изображений
  - Зависит от `db`
- Service `db`: PostgreSQL 17
  - Порт: `${POSTGRES_PORT:-5432}:5432`
  - Volume: `mospoly-psychological-pg-data` для данных
  - Persistent storage для базы данных

**Команды**:
```bash
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Применить миграции (Makefile)
make migrate

# Создать миграцию
make migrate-create MESSAGE="описание"

# Просмотр логов
docker-compose logs -f app
```

---

## Известные проблемы и TODO

### Критические

1. **❌ Отсутствуют функции в `repositories/appointments.py`**:
   - `cancel_appointment_by_patient(appointment_id: UUID, patient_id: UUID)`
   - `get_appointment_for_user(appointment_id: UUID, user_id: UUID)`
   - Эти функции импортируются в сервисном слое, но не реализованы

2. **❌ Проблема с импортом констант**:
   - В `routes/controllers/__init__.py` импортируются `ACCESS_TOKEN_EXPIRE` и `REFRESH_TOKEN_EXPIRE` из `psychohelp.config`
   - Файл `config/__init__.py` пустой
   - Нужно либо экспортировать константы, либо исправить импорты

3. **❌ Отсутствует импорт в `repositories/__init__.py`**:
   - Используется `REFRESH_TOKEN_EXPIRE` без импорта (строка 25)
   - Должен быть `from psychohelp.config.database import config`

### Рекомендуется

4. **⚠️ Email в User модели**:
   - Поле `email` теперь nullable=False (обязательно)
   - Миграция `23020d3e0038_make_email_required` исправила это
   - ✅ Исправлено

5. **⚠️ Безопасность cookies в продакшене**:
   - Access token cookie имеет `secure=False` для разработки
   - Нужно включить `secure=True` и `samesite="None"` для продакшена

6. **⚠️ Проверка прав для пользователей**:
   - В `appointments` GET `/` есть проверка `is_admin`, но этот атрибут не определен в модели
   - Нужно реализовать через RBAC систему

---

## Зависимости

Основные зависимости из `pyproject.toml`:

```toml
dependencies = [
    "fastapi==0.115.0",
    "uvicorn[standard]>=0.24.0",
    "sqlalchemy==2.0.35",
    "asyncpg==0.30.0",
    "passlib[bcrypt]",
    "pyjwt==2.9.0",
    "pydantic[email]>=2.0.0",
    "pydantic-extra-types",
    "phonenumbers",
    "httpx",
    "anyio",
    "greenlet",
    "bcrypt==4.3.0",
    "alembic>=1.14.1",
    "psycopg2-binary>=2.9.10",
]

dev = [
    "pytest>=8.3.5",
    "pytest-asyncio",
]
```

**Примечания**:
- `asyncpg` для асинхронной работы с PostgreSQL
- `psycopg2-binary` для Alembic миграций (синхронный драйвер)
- `pydantic-extra-types` для валидации телефонных номеров
- `httpx` и `anyio` для асинхронных HTTP запросов в тестах
