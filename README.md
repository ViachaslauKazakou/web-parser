# ForumScope

ForumScope — отдельное FastAPI-приложение для сбора публичных форумных обсуждений, детерминированного ранжирования ответов и сохранения истории запусков. Веб-интерфейс доступен напрямую, без входа и учётных записей.

> **Важно:** приложение намеренно не содержит авторизации и предназначено для `localhost` или доверенной частной сети. Не публикуйте порт 8040 в открытый интернет.

## Запуск через Docker Compose

В корне уже создан локальный `.env` с development-настройками. Для новой копии репозитория:

```bash
cp .env.example .env
```

Перед запуском в сети измените локальный пароль PostgreSQL в `.env`. Затем:

```bash
docker compose up --build
```

- UI: <http://localhost:8040>
- OpenAPI / Swagger: <http://localhost:8040/docs>
- Health: <http://localhost:8040/api/health>

Compose ждёт healthcheck PostgreSQL перед запуском приложения. Записи хранятся в локальном каталоге `data/postgres/` (он исключён из Git и Docker build context). `docker compose down` сохраняет базу; удаляйте каталог только если хотите очистить историю.

## Сценарии

- Разбор публичной темы по URL с предварительным просмотром постов.
- Поиск сообщений по ключевому слову на `searchengines.guru`.
- Сбор комментариев пользователя по числовому ID.
- Импорт обсуждения из JSON или CSV, либо ручной ввод.
- Ранжирование ответов по воспроизводимому hash-BOW/лексическому сигналу, с метриками и объяснениями факторов.
- Сохранение результатов в PostgreSQL и повторный просмотр из истории.
- Экспорт завершённого анализа в JSON или CSV.
- Опциональные LLM-оценки и пояснения через OpenAI-compatible Chat Completions; без LLM детерминированный анализ работает локально.

При поиске по имени парсер использует поисковую выдачу форума по keyword, как и исходный сервис; это не гарантирует полный список сообщений конкретного автора. Поиск по числовому ID идёт через страницу пользовательских комментариев.

## API

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/api/health` | Проверка приложения и БД |
| `POST` | `/api/parser/user` | Поиск по имени или сбор комментариев по ID |
| `POST` | `/api/parser/topic` | Разбор публичной темы |
| `POST` | `/api/analysis` | Анализ валидированного JSON payload |
| `POST` | `/api/analysis/import` | Multipart-импорт JSON/CSV и анализ |
| `POST` | `/api/analysis/from-parsed-topic` | Парсинг темы и анализ одним запросом |
| `GET` | `/api/runs` | Последние сохранённые запуски |
| `GET` | `/api/runs/{id}` | Полный результат запуска |
| `GET` | `/api/runs/{id}/export.json` | Скачать JSON |
| `GET` | `/api/runs/{id}/export.csv` | Скачать CSV |

### Пример JSON

```json
{
  "source_type": "manual",
  "topic": {
    "title": "Как настроить асинхронные сессии в FastAPI?",
    "description": "Практические рекомендации по SQLAlchemy async.",
    "first_message_content": "Как правильно создавать и закрывать сессии?"
  },
  "messages": [
    {
      "external_id": "reply-1",
      "author": "participant",
      "content": "Используйте async_sessionmaker и контекстный менеджер."
    }
  ],
  "options": {
    "use_community_weight": false,
    "use_llm_scoring": false,
    "use_llm_explain": false,
    "llm_score_weight": 0.35
  }
}
```

### CSV

Обязательные поля: `topic_title`, `content`. Дополнительные: `topic_description`, `first_message_content`, `topic_external_id`, `message_external_id`, `author`, `rating`, `created_at`. Файл должен быть UTF-8; BOM поддерживается. Лимит файла — 5 МБ, общий HTTP body — 10 МБ, предел одного анализа — 2000 ответов.

## Конфигурация

Настройки читаются из `.env` и переменных окружения:

| Переменная | Назначение |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Локальная БД Compose |
| `POSTGRES_DATA_DIR` | Каталог данных PostgreSQL на хосте, по умолчанию `./data/postgres` |
| `DATABASE_URL` | SQLAlchemy async URL; Compose строит его из `POSTGRES_*`, для запуска вне Compose задаётся напрямую |
| `APP_PORT` | Порт интерфейса на хосте, по умолчанию 8040 |
| `PARSER_ALLOWED_HOSTS` | Дополнительные домены парсинга через запятую; `searchengines.guru` всегда разрешён для перенесённых сценариев пользователя |
| `MAX_PARSER_PAGES` | Верхняя граница обхода страниц за один запуск, по умолчанию 20 |
| `MAX_PARSER_PAGE_CHARS` | Максимальный HTML размер одной разобранной страницы, по умолчанию 2 млн символов |
| `PARSER_TOTAL_TIMEOUT_SECONDS` | Общий deadline парсинга, по умолчанию 180 секунд |
| `MAX_UPLOAD_BYTES` | Максимальный размер файла; по умолчанию 5 МБ |
| `MAX_REQUEST_BODY_BYTES` | Верхняя граница тела API-запроса до разбора JSON/multipart; по умолчанию 10 МБ |
| `OPENAI_API_KEY` | Необязательный ключ для LLM-функций |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint, по умолчанию `https://api.openai.com/v1` |
| `OPENAI_MODEL` | Имя chat-модели, по умолчанию `gpt-4o-mini` |

Парсер принимает только HTTPS URL из allowlist. JavaScript сохраняется для совместимости с markup families, но RTCPeerConnection отключён, а Chromium policy блокирует непроксированный UDP. Локальный egress proxy проверяет каждый CONNECT/redirect, разрешает только доверенные домены, отклоняет private/link-local DNS-ответы, соединяется с pinned IP и ограничивает один tunnel до 2 МБ исходящего запроса / 8 МБ ответа. HTML ограничен 2 млн символов на страницу. Дополнительные домены должны быть доверенными и задаваться оператором в `.env`.

Linux seccomp-профиль Chromium и его upstream provenance описаны в [`docker/README.md`](docker/README.md).

CSV-экспорт экранирует значения, похожие на spreadsheet-формулы; при импорте такого CSV в таблицы в начале отдельных ячеек может сохраняться защитный tab.

В исходном сервисе были credentials форума, захардкоженные в `parser_config.py`; они намеренно не перенесены. Если эти данные ещё действуют, замените их в исходной системе.

## Локальная разработка и тесты

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

`Dockerfile` устанавливает Chromium для Playwright. Тесты парсинга используют локальные HTML-фрагменты и не выполняют сетевые запросы.
