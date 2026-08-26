# Деплой ContractScout на сервер

Репозиторий на GitHub (рекомендуемое имя): **`contractscout`**.

## Локально

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# DEEPSEEK_API_KEY; на сервере ещё PUBLIC_BASE_URL, ЮKassa и OPERATOR_*
python -m contract_scout.web
```

Демо: http://127.0.0.1:8080  
Проверка: http://127.0.0.1:8080/health

MAX-бот (не параллелить с другим процессом на том же токене):

```bash
python -m contract_scout.bot
```

## Docker на VPS

1. Ubuntu 22.04, Docker, A-запись домена на IP сервера.
2. Клонировать репозиторий, скопировать `.env.example` → `.env`.
3. Для публичного сайта:

```
LOCAL_ONLY=0
SECRET_KEY=<длинная случайная строка>
PUBLIC_BASE_URL=https://ваш-домен
TRUST_PROXY=1
ALLOWED_HOSTS=ваш-домен
PAYWALL=1
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_REQUIRE_RECEIPT=1
DEEPSEEK_API_KEY=
OPERATOR_NAME=ИП Иванов И.И.
OPERATOR_INN=
OPERATOR_OGRN=
OPERATOR_EMAIL=privacy@ваш-домен
OPERATOR_ADDRESS=
```

`LOCAL_ONLY=1` оставляет файлы на диске сервера и отключает MAX/SMTP; ЮKassa при этом всё равно работает, если ключи заданы.

4. `docker compose up --build -d`
5. Перед контейнером — Caddy или Nginx с TLS. Пример Caddy: `docs/Caddyfile` (`caddy reverse-proxy` на `127.0.0.1:8080`).
6. Мониторинг: `/health`, логи `docker compose logs -f web`.

Данные (архив, оплаты) — volume `scout-data` → `/app/data`.

Один процесс uvicorn: журнал оплат — JSON-файл, несколько воркеров дадут гонки.

## ЮKassa (данные для кабинета)

1. Кабинет: [yookassa.ru](https://yookassa.ru) → тестовый или боевой магазин.
2. В `.env`: `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`.
3. HTTP-уведомления: `https://ваш-домен/api/billing/webhook`  
   Событие: `payment.succeeded`.
4. URL возврата задаётся приложением: `https://ваш-домен/pay/return`.
5. В магазине включите чеки 54‑ФЗ: на сайте email обязателен (`YOOKASSA_REQUIRE_RECEIPT=1`), в платёж уходит `receipt.customer.email`.
6. `YOOKASSA_VAT_CODE` — код НДС из кабинета (часто `1` = без НДС).
7. Сумма и пакет: `YOOKASSA_AMOUNT`, `YOOKASSA_CREDITS`.

Без ключей ЮKassa сайт работает бесплатно.  
`PAYWALL=1` при ключах: загрузка в архив и локальный сканер бесплатны; **проверка в ИИ** и **черновик** списывают 1 кредит.

Кредиты привязаны к cookie (`SECRET_KEY` должен быть постоянным).

## 152‑ФЗ

1. Заполните `OPERATOR_*` — они подставляются в `/privacy` и `/offer`.
2. При оплате пользователь отмечает согласие и передаёт email только для чека; email в `data/billing` не пишется.
3. Договоры хранятся в `data/` на сервере; в LLM уходит обезличенный текст при `REDACT_REQUISITES=1`.
4. Перед продакшеном: согласовать тексты с юристом; при необходимости — уведомление РКН об обработке ПДн.

Публичные страницы: `/privacy`, `/offer`.

## Реквизиты сторон

В форме черновика у заказчика/исполнителя можно загрузить файл с реквизитами (TXT, DOCX, PDF или JSON).
Сервис разбирает ИНН, КПП, ОГРН, адрес, счета, банк, БИК и ФИО директора локально — без платных API.
Карточка также сохраняется в `data/parties.json` для подсказок по названию.

## Логирование

`LOG_LEVEL=INFO`. Uvicorn пишет в stdout — journald / Docker.
