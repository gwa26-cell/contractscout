# API (backend)

Базовый URL через nginx: `/api/...`

## Auth

- `POST /api/auth/register` `{ email, password }`
- `POST /api/auth/login` `{ email, password }` → `{ access_token }`
- `GET /api/auth/me` — Bearer token

## Services (CRUD)

- `GET /api/services` — публично
- `POST /api/services` — auth
- `PUT /api/services/{id}` — auth
- `DELETE /api/services/{id}` — auth

## Orders

- `POST /api/orders` — публично, `{ service_id, priority, client_name, client_email, ... }`
- `GET /api/orders` — auth, сортировка по priority
- `GET /api/orders/{id}` — auth

## Behavior metrics

- `POST /api/behavior-metrics/` — публично, append-only (application_id не валидируется)
- `GET /api/behavior-metrics?skip=0&limit=100` — auth
- `GET /api/behavior-metrics/stats` — auth, агрегация + heatmap

## Consultation (stub)

- `POST /api/consultation` — публично, `{ name, email, phone?, topic?, message }`
- Сохраняется в таблицу `consultations`

## Админ по умолчанию

- `gwa26@bk.ru` / `admin123` (env: `ADMIN_EMAIL`, `ADMIN_PASSWORD`)
