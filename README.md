# StudyMate AI

> Find the right people, build productive study teams, and stay motivated through collaborative learning.

StudyMate AI is an AI-powered collaborative learning platform for university students, built for the **Google Cloud / AI Hackathon**. It matches students with compatible study partners, helps them form small **Study Parties**, organize study sessions, rate teammates, and keep shared **study streaks**.

## Core features (MVP)

- **Student profile:** subjects, knowledge levels (1–5), goals, availability, learning preferences
- **AI matching:** weighted compatibility score (0–100) plus a Gemini-generated explanation
- **Study Parties:** teams of 2–5 students
- **Study sessions:** create, join, complete
- **Teammate ratings:** private 1–5 feedback after each session
- **Progress and streaks:** individual and team

## Tech stack

| Layer          | Technology                                         |
| -------------- | -------------------------------------------------- |
| Frontend       | React, Vite, Tailwind CSS, Axios, React Router     |
| Backend        | Python, FastAPI, Pydantic, SQLAlchemy              |
| Database       | PostgreSQL (Cloud SQL optional)                    |
| AI             | Google Gemini API                                  |
| Infrastructure | Google Cloud Run, Secret Manager, GitHub           |

## Architecture

```
Student -> React Frontend -> FastAPI -> { Matching Algorithm | PostgreSQL | Gemini API }
                                     -> Study Parties -> Sessions -> Ratings -> Progress & Streaks
```

The matching algorithm calculates the scores; Gemini only **explains** them. Details: [docs/architecture.md](docs/architecture.md).

## Repository structure

```
StudyMate-AI/
├── frontend/   # React + Vite app
├── backend/    # FastAPI app (api/, services/, models/, schemas/)
├── docs/       # Specification, architecture, API, database, demo
└── .github/    # Issue and PR templates
```

## Documentation

- [Technical Specification](docs/technical-specification.md): full product and technical spec
- [Architecture](docs/architecture.md)
- [API Specification](docs/api.md)
- [Database Design](docs/database.md)
- [Demo & Presentation](docs/presentation.md)
- [Contributing / Git workflow](CONTRIBUTING.md)

## Getting started

> The backend and frontend skeletons are still to be created. See the *Initialize FastAPI backend* and *Initialize React frontend* issues.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY and DATABASE_URL
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Team

| Role                               | Responsibilities                                       |
| ---------------------------------- | ------------------------------------------------------ |
| Person 1: Backend / Team Lead      | FastAPI, endpoints, DB integration, parties & sessions |
| Person 2: AI / Matching            | Matching algorithm, scores, Gemini integration         |
| Person 3: Frontend                 | React app, UI/UX, profile, matches, dashboards         |
| Person 4: Cloud / Database / QA    | Google Cloud, deployment, testing, docs, presentation  |

## Roadmap

1. **Setup:** repo, environments, skeletons, Gemini key, API contracts
2. **Core:** profiles, DB models, matching, frontend pages, parties
3. **Integration:** frontend ↔ backend, Gemini, matching tests
4. **Additional:** sessions, ratings, progress, streaks
5. **Deployment:** Cloud Run, env vars, production test
6. **Finalization:** bug fixes, demo, README, presentation

**First priority:** a working `Profile → Matching → Results` flow. Everything else builds on it.

## License

[MIT](LICENSE)
