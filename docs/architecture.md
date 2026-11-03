# Architecture

```
                    STUDENT
                       |
                       v
                REACT FRONTEND
                       |
                       v
                    FASTAPI
                       |
          +------------+------------+
          |            |            |
          v            v            v
      Matching      Database      Gemini API
      Algorithm    PostgreSQL   AI Explanations
          |
          v
     Recommended
      Students

Frontend -> Study Parties -> Sessions -> Ratings
                                |
                                v
                       Progress & Streaks
```

## Responsibilities

| Component | Responsibilities |
| --------- | ---------------- |
| **Frontend** | Displays the UI, collects student information, sends API requests, displays matches and progress. |
| **Backend** | Validates requests, manages profiles and parties, calculates matching scores, handles sessions and ratings, updates progress and streaks. |
| **Database** | Stores profiles, parties & memberships, sessions & feedback, progress. |
| **Gemini** | Generates matching explanations; optionally generates study session plans. |

> Gemini is **not** responsible for database operations or for computing raw matching scores. It receives the already computed score breakdown and only turns it into human-readable text.

## Matching flow

1. `POST /api/matches` with `user_id`
2. `services/matching.py` loads candidate profiles and computes per-criterion scores (0–1)
3. Weighted sum × 100 gives the final score; candidates are sorted and the top `limit` kept
4. `services/gemini_service.py` receives the structured breakdown (shared subjects, complementary skills, overlapping time slots…) and returns a short explanation
5. If Gemini fails or times out, fall back to a template explanation so the demo never breaks

## Deployment (hackathon setup)

- **Backend:** container on **Cloud Run**; `GEMINI_API_KEY` and `DATABASE_URL` from Secret Manager or env vars
- **Frontend:** static Vite build (Cloud Run with nginx, Firebase Hosting, or Cloud Storage)
- **Database:** Cloud SQL for PostgreSQL (or a managed Postgres for speed); SQLite locally is acceptable for development
