# ContractScout

Веб-сервис (и опциональный бот MAX) для **проверки договоров** на типичные узкие места и **сборки черновика** нужного типа: услуги, подряд, поставка, аренда, NDA, заём, лицензия, IT и др.

Сервис **не является юридической консультацией** и не заменяет юриста. Результат — материал для переговоров и список вопросов специалисту.

Репозиторий: https://github.com/gwa26-cell/contractscout

---

## Что делает продукт

1. **Проверка договора**  
   Загрузка PDF/DOCX/TXT или вставка текста → локальный архив → отчёт по рискам (индекс 0–100, цитаты, «как чинить», скрипт для контрагента).  
   Проверка в ИИ — отдельной кнопкой и только по **обезличенному** тексту (без ИНН, счетов, адресов, ФИО сторон).

2. **Исправление по рискам**  
   Кнопка «Исправить с учётом найденных рисков» → текст в редакторе → правка вручную / через ИИ → скачивание DOCX.

3. **Проект договора**  
   Форма брифа, реквизиты сторон (ввод или файл), опционально приложения ТЗ и акт, генерация черновика, выгрузка DOCX.

4. **Оплата (опционально)**  
   ЮKassa, пакеты кредитов на ИИ/черновик, страницы `/privacy` и `/offer`.

---

## Стек

| Слой | Технология |
|------|------------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Парсинг | Docling / pypdf / python-docx |
| ИИ | DeepSeek (OpenAI-совместимый API), опционально |
| Эмбеддинги | локальный MiniLM или hash (LOCAL_ONLY) |
| Документы | python-docx |
| Оплата | ЮKassa |
| Бот | MAX long polling (опционально) |
| Деплой | Docker / Nixpacks, Caddy/Nginx + HTTPS |

---

## Требования

- Python **3.11+** (рекомендуется 3.12)
- Windows / Linux / macOS
- Для ИИ-разбора: ключ `DEEPSEEK_API_KEY` (или OpenAI)
- Для бота: `MAX_BOT_TOKEN`
- Для оплаты на сервере: домен с HTTPS, ключи ЮKassa, `PUBLIC_BASE_URL`

---

## Быстрый старт (локально)

### Windows (PowerShell)

```powershell
cd ContractScout
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Откройте `.env` и при необходимости укажите:

```env
DEEPSEEK_API_KEY=ваш_ключ
SECRET_KEY=любая-длинная-строка
LOCAL_ONLY=1
EMBEDDING_PROVIDER=hash
REDACT_REQUISITES=1
WEB_PORT=8080
```

Для локального MiniLM/Pinecone (тяжело, не для VPS): `pip install -r requirements-ml.txt`.

Запуск веб-сервиса:

```powershell
python -m contract_scout.web
```

Откройте в браузере: http://127.0.0.1:8080  

Проверка здоровья: http://127.0.0.1:8080/health

### Linux / macOS

```bash
cd ContractScout
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# отредактируйте .env
python -m contract_scout.web
```

---

## Основные сценарии в интерфейсе

### 1. Проверить договор

1. Раздел «Проверить договор».
2. Вставьте текст или загрузите файл.
3. Нажмите «Проверить договор» — файл попадёт в архив, сработает локальный сканер.
4. При необходимости нажмите «Проверить в ИИ».
5. При наличии рисков — «Исправить с учётом найденных рисков», правьте текст, скачайте DOCX.

### 2. Собрать свой договор

1. Раздел «Собрать проект договора».
2. Заполните бриф (тип, предмет, цена, срок…).
3. Загрузите файлы реквизитов заказчика/исполнителя **или** введите вручную.  
   После автозаполнения **обязательно сверьте данные с оригиналом**.
4. При необходимости отметьте «Приложить ТЗ» / «Акт».
5. «Сгенерировать черновик» → правки → «Скачать DOCX».
6. «Очистить форму» сбрасывает поля и черновик.

Пример файла реквизитов: [`samples/requisites_ooo.txt`](samples/requisites_ooo.txt)  
Пример рискованного договора: [`samples/risky_it_contract.txt`](samples/risky_it_contract.txt)

---

## Переменные окружения (.env)

| Переменная | Назначение |
|------------|------------|
| `DEEPSEEK_API_KEY` | Ключ LLM (DeepSeek) |
| `LOCAL_ONLY` | `1` — без MAX/SMTP/облачных эмбеддингов; файлы на диске |
| `REDACT_REQUISITES` | `1` — вырезать реквизиты перед ИИ |
| `SECRET_KEY` | Подпись cookie (кредиты); на проде — постоянная случайная строка |
| `WEB_HOST` / `WEB_PORT` / `PORT` | Хост и порт (на хостинге часто задаётся `PORT`) |
| `PUBLIC_BASE_URL` | Публичный HTTPS-адрес (нужен для ЮKassa) |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Оплата |
| `PAYWALL` | `1` — ИИ/черновик за кредиты |
| `OPERATOR_*` | Реквизиты оператора для `/privacy` и `/offer` |
| `MAX_BOT_TOKEN` | Токен бота MAX |
| `PINECONE_API_KEY` | Опциональный облачный индекс (нужен `requirements-ml.txt`) |
| `EMBEDDING_PROVIDER` | `hash` на VPS; `local` только с MiniLM из `requirements-ml.txt` |

Полный шаблон: [`.env.example`](.env.example).  
Деплой и ЮKassa: [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## MAX-бот (опционально)

В `.env`:

```env
LOCAL_ONLY=0
MAX_BOT_TOKEN=ваш_токен
```

Запуск (не параллелить два процесса на одном токене):

```powershell
python -m contract_scout.bot
```

---

## Тесты

```powershell
pytest -q
```

---

## Docker

```bash
docker compose up --build -d
```

Перед продом задайте `.env` (`PUBLIC_BASE_URL`, `SECRET_KEY`, ключи LLM/ЮKassa).  
Перед контейнером — reverse proxy с TLS (пример: `docs/Caddyfile`).

---

## Структура репозитория

```
contract_scout/     # код сервиса (web, bot, review, draft, payments…)
knowledge/          # каталог рисков
samples/            # примеры файлов
tests/              # pytest
docs/DEPLOY.md      # деплой и ЮKassa
Dockerfile
docker-compose.yml
Procfile            # старт для Nixpacks
.env.example
```

Данные выполнения пишутся в каталог `data/` (в git не входит): архив, загрузки, оплаты, сохранённые стороны.

---

## Лицензия и ответственность

Проект для переговоров и обучения работе со стеком.  
Автор не несёт ответственности за юридические последствия использования сгенерированных текстов. Перед подписанием договора консультируйтесь с юристом.
