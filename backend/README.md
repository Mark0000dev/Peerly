# Backend (FastAPI)

Planned layout (see issue *Initialize FastAPI backend*):

```
backend/
├── app/
│   ├── main.py
│   ├── api/        users, matches, parties, sessions, ratings, progress
│   ├── services/   matching, gemini_service, streak_service, progress_service
│   ├── models/     SQLAlchemy models
│   ├── schemas/    Pydantic schemas
│   ├── database.py
│   └── config.py
├── tests/
├── requirements.txt
└── .env.example
```

API contract: [docs/api.md](../docs/api.md)
