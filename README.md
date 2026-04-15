# SokoMjinga API

Backend service for **SokoMjinga**, built with [FastAPI](https://fastapi.tiangolo.com/), [SQLAlchemy](https://www.sqlalchemy.org/), and [Alembic](https://alembic.sqlalchemy.org/).

This repo handles the **core business logic and persistence** — exposing REST APIs consumed by the [SokoMjinga Frontend](https://github.com/waynemwandi/sokomjinga-frontend.git).

---

## Getting Started

### Prerequisites

- Python 3.11+
- MySQL 8.0+
- pip / virtualenv

### Installation

```sh
python -m venv .venv

source .venv\Scripts\activate # (on Windows)

source .venv\bin\activate # (on Unix)

pip install -r requirements.txt
```

### Database Setup

#### Edit .env with your DB connection string

```sh
DATABASE_URL=mysql+pymysql://app:apppass@localhost:3306/sokomjinga
```

#### Run migrations

```sh

alembic revision --autogenerate -m "your-message-here"

alembic upgrade head
```

### Development

```sh
uvicorn app.main:app --reload

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 # specify port

python -m app.main

python -m scripts.test_email

```

## Initial Endpoints

- GET /health
- GET /markets
- GET /markets/{id}

## Project Structure

- app/
  - main.py -> FastAPI entrypoint
- api/ -> route handlers
- db/ -> models, session, migrations
- schemas/ -> Pydantic DTOs
- services/ -> business logic
- alembic/ -> migration files

## Next Steps

- Add seeding script for markets/outcomes
- Implement auth (register, login)
- Add wallet and order models
- Dockerize and include in sokomjinga-iac

## Alembic

```sh
alembic init alembic

alembic revision --autogenerate -m "create markets table"

alembic upgrade head

```

## MySQL Database Backup - Manual Command

```sh
scp -i /c/Users/Wayne/Desktop/Desktop/sslKeys/kejasmartPublic.pem \
ubuntu@13.50.156.247:/home/ubuntu/apps/sokomjinga/backups/prod_backup_20260213_090631.sql \
/c/Users/Wayne/Desktop/

```

## Restore Database Backup - Manual Command

```sh
docker exec -i sokomjinga-iac-db-1 \
mysql -uroot -p<MYSQL_PASSWORD> sokomjinga \
< /home/ubuntu/apps/sokomjinga/backups/prod_backup_20260213_090631.sql
```

## Email Notifications

### Overview

Notifications are triggered **after successful DB transactions** and are **non-blocking**.

Flow:

1. Business logic completes (e.g. bet placement)
2. `db.commit()` is executed
3. Notification function is called (e.g. `send_bet_confirmation`)
4. Email is rendered via template
5. Email is sent via SES (SMTP) and logged in DB

---

### Trigger Point (Important)

Emails are sent **after commit** to ensure:

- no emails are sent for failed transactions
- DB state and user communication stay consistent

```python
db.commit()

try:
    send_bet_confirmation(...)
except Exception:
    pass
```

---

### notifications.py (Trigger Layer)

Responsible for:

- deciding when to send emails
- calling the correct template
- calling `send_email`

No HTML should exist here.

```python
body = render_bet_confirmation_email(...)
send_email(to_email=user.email, subject=subject, body=body)
```

---

### email_templates/ (Rendering Layer)

Structure:

```sh
email_templates/
  base.py
  bet_confirmation.py
```

- `base.py` → shared layout (theme)
- `bet_confirmation.py` → dynamic content

All templates return a final HTML string.

---

### email.py (Delivery Layer)

Handles:

- SMTP (AWS SES)
- sending email
- logging to DB (`EmailLog`)

States:

- `pending`
- `sent`
- `failed`

---

### Key Rules

- Email must never block core flows
- Always send after `db.commit()`
- Templates handle UI, not notifications
- All emails are logged in `email_logs`
