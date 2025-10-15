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
alembic upgrade head
```

### Development

```sh
uvicorn app.main:app --reload

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 # specify port

python -m app.main

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
