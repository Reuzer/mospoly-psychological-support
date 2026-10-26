# Отчет по фиксу 401 для `POST /appointments/create`

## Контекст
Тестировщики воспроизводили `401 Unauthorized` на `POST /appointments/create` даже после успешного `POST /users/login` и наличия `access_token` в cookie.

## Причина
Проблема была в декораторе `require_permission`.
Он требовал объект `Request` в аргументах endpoint и возвращал `401` с `detail: "Request object not found"`, если `request` не был передан явно.

В `appointments`-endpoint'ах, включая `POST /appointments/create`, `request` действительно не передавался, поэтому возникал ложный `401`.

## Что исправлено
Изменен файл:
- `psychohelp/services/rbac/permissions.py`

Суть фикса:
- Декоратор теперь сначала использует `current_user` (если dependency уже его инжектнул).
- Доступ к cookie через `request` остался как fallback.
- Если нет ни `current_user`, ни `request`/cookie, только тогда возвращается `401 Не авторизован`.

Это убирает зависимость от обязательного `request` в сигнатуре каждого protected endpoint.

## Дополнительно
Добавлен тест:
- `tests/test_rbac_permissions.py`

Проверяет:
1. Декоратор корректно работает без `request`, если есть `current_user`.
2. Декоратор возвращает `401`, если нет и `request`, и `current_user`.

Локальный прогон:
- `python -m pytest -q tests/test_rbac_permissions.py`
- Результат: `2 passed`.

## Ветка
- `fix/appointments-request-object-401`

## Деплой на сервер
Сервер: `185.128.105.126`
Путь проекта: `/srv/mospoly-psychological-support`

Выполнено:
1. `git checkout fix/appointments-request-object-401`
2. `git pull --ff-only origin fix/appointments-request-object-401`
3. `docker compose up -d --build`

## Curl-проверки на сервере
База: `http://127.0.0.1:8000`

### 1) Логин
```bash
curl -s -c /tmp/ph_cookie.txt \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/users/login \
  -d '{"email":"usr@exmple.com","password":"StrongPassword23"}'
```

Результат: `HTTP 200`, получен пользователь и cookie.

### 2) Создание записи с датой в будущем (UTC)
```bash
curl -s -b /tmp/ph_cookie.txt \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/appointments/create \
  -d '{
    "patient_id":"ceec6a26-9ae8-4c41-bb5b-5f84c6f700ce",
    "psychologist_id":"fb1938f5-3cfd-4964-8456-77ee1ce47ef2",
    "type":"Offline",
    "scheduled_time":"2026-04-07T20:11:12.204971Z",
    "reason":"qa check",
    "venue":"office",
    "comment":"from curl"
  }'
```

Результат: `HTTP 200`, запись успешно создана.

### 3) Попытка создать запись с датой в прошлом
```bash
curl -s -b /tmp/ph_cookie.txt \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/appointments/create \
  -d '{
    "patient_id":"ceec6a26-9ae8-4c41-bb5b-5f84c6f700ce",
    "psychologist_id":"fb1938f5-3cfd-4964-8456-77ee1ce47ef2",
    "type":"Offline",
    "scheduled_time":"2026-04-07T16:11:12.238112Z",
    "reason":"qa check past",
    "venue":"office",
    "comment":"from curl"
  }'
```

Результат: `HTTP 400`, `"Время записи не может быть в прошлом"`.

## Проверка по исходному кейсу
- `401` из-за `Request object not found` устранен.
- Авторизация по cookie для `POST /appointments/create` работает.
- Валидация времени (UTC / прошлое) работает.

## Что не закрыто полностью в этом фиксе
Пункт про связку с `application_id` в рамках полного бизнес-процесса (создание/перевод статусов заявки до `confirm`) не расширялся в этом изменении и требует отдельного e2e-сценария с ролями менеджера/психолога.
