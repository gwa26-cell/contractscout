# ContractScout Services API

Сервис заявок на услуги ContractScout: **backend + PostgreSQL + nginx + форма + админ-панель**.

Основной продукт: [contractscout](https://github.com/gwa26-cell/contractscout) · [tcm24.store](https://tcm24.store/)

Отдельный репозиторий: [homework3](https://github.com/gwa26-cell/homework3)

## Возможности

- Регистрация и вход (JWT), Swagger UI с авторизацией
- CRUD услуг в админ-панели (таблица + редактор)
- Заявки с приоритетом (1–3) и «температурой» лида
- Сбор метрик поведения (время, клики, курсор раз в секунду)
- Модальное окно «Статистика пользователей» (среднее время + heatmap)
- Backend и PostgreSQL **без публичных портов** — только nginx

## Запуск

```bash
cd frontend && npm run build
cd .. && docker compose up --build -d
```

- Форма: http://localhost:8088  
- Админ: http://localhost:8088/admin.html  
- Swagger: http://localhost:8088/docs  

Админ по умолчанию: `gwa26@bk.ru` / `admin123`

## Тестовые заявки

```bash
docker compose exec -T db psql -U scout -d contractscout_hw < scripts/seed_orders.sql
```

## API

См. [docs/API.md](docs/API.md)

## Безопасность (Docker)

- Порты `8000` (backend) и `5432` (PostgreSQL) **не публикуются**
- Доступ только через nginx (`8088` локально, `443` в проде)
- pgAdmin и registry не включены

Логи: `docker compose logs -f backend`

## Стек

FastAPI, SQLAlchemy, PostgreSQL, JWT, nginx, статический фронт
