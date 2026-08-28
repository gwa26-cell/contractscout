# ContractScout Services API

Сервис заявок на услуги ContractScout: **backend + PostgreSQL + nginx + форма на сайте**.

Основной продукт (проверка и сборка договоров): [contractscout](https://github.com/gwa26-cell/contractscout) · [tcm24.store](https://tcm24.store/)

## Услуги (сиды в БД)

1. **Проверить договор** — проверка рисков в ContractScout  
2. **Собрать договор** — черновик и DOCX  
3. **Занести в базу договор** — архив проектов  

## Запуск

```bash
cd frontend
npm run build

cd ..
docker compose up --build -d
```

- Форма заявки: http://localhost:8088  
- Swagger: http://localhost:8088/docs  
- API: http://localhost:8000/api/services  

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/services` | Список услуг |
| POST | `/api/services` | Создать услугу |
| POST | `/api/orders` | Отправить заявку |
| GET | `/health` | Проверка и число услуг в БД |

Логи backend: `docker compose logs -f backend`

## Стек

- FastAPI, SQLAlchemy, PostgreSQL  
- nginx (статика + прокси `/api`)  
- Статический фронт (`npm run build`)
