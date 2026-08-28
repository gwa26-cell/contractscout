# ContractScout — homework (отдельно от основного продукта)

Мини-проект для сдачи ДЗ: **backend + PostgreSQL + nginx + форма заявки**.  
Основной ContractScout (`contract_scout/web`) **не меняется**.

## 3 услуги (сиды в БД)

1. **Проверить договор** — соответствует проверке рисков в ContractScout  
2. **Собрать договор** — черновик и DOCX  
3. **Занести в базу договор** — архив проектов  

## Запуск

```bash
cd homework/frontend
npm run build

cd ..
docker compose up --build -d
```

- Форма заявки: http://localhost:8088  
- Swagger: http://localhost:8088/docs  
- API напрямую: http://localhost:8000/api/services  

## Проверка ДЗ

1. `GET /api/services` — три услуги  
2. Swagger `/docs` — можно создать услугу вручную (`POST /api/services`)  
3. Форма → «Заявка отправлена!»  
4. Логи: `docker logs -f homework-backend-1` (имя контейнера уточните через `docker ps`)  

## Скрины для сдачи

- Swagger со списком услуг  
- Форма с выбранной услугой и успешной отправкой  
- `docker ps` / `docker compose ps`  
- Ссылка на GitHub + скрин **основного** ContractScout (tcm24.store) как продукт  

## Связь с основным проектом

Этот репозиторий — **API-слой для задания**. Реальная работа с договорами — в корне репозитория (`python -m contract_scout.web`).
