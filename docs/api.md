# API Specification

Base URL: `/api`. All bodies are JSON. IDs are UUID strings.

> This is the API contract (issue: *Define API contracts*). Change it only via a PR that the whole team reviews.

## Student profiles

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/users` | Create profile |
| GET | `/api/users/{user_id}` | Get profile |
| PUT | `/api/users/{user_id}` | Update profile |

**POST /api/users**

```json
{
  "name": "Alex",
  "university": "APU",
  "major": "Computer Science",
  "year_of_study": 1,
  "study_format": "online",
  "learning_style": "discussion",
  "subjects": [
    { "name": "Python", "knowledge_level": 4 },
    { "name": "SQL", "knowledge_level": 2 }
  ],
  "goals": ["Prepare for an exam"],
  "availability": [
    { "day_of_week": 1, "start_time": "18:00", "end_time": "21:00" }
  ]
}
```

Response `201`: the created profile with `id`.

## Matching

**POST /api/matches**

```json
{ "user_id": "uuid", "limit": 5 }
```

Response `200`:

```json
{
  "matches": [
    {
      "user_id": "uuid",
      "name": "John",
      "score": 87,
      "breakdown": {
        "subjects": 0.9,
        "goals": 1.0,
        "complementary_knowledge": 0.8,
        "schedule": 0.7,
        "preferences": 0.5
      },
      "reason": "Compatible goals and complementary skills"
    }
  ]
}
```

## Study Parties

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/parties` | Create party `{ "name", "created_by", "member_ids": [] }` |
| GET | `/api/parties/{party_id}` | Get party with members |
| POST | `/api/parties/{party_id}/members` | Add member `{ "user_id" }` |
| GET | `/api/users/{user_id}/parties` | List user's parties |

Errors: `400` if the party would have fewer than 2 or more than 5 members.

## Study Sessions

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/sessions` | Create `{ "party_id", "title", "subject", "scheduled_at", "duration_minutes", "participant_ids": [] }` |
| GET | `/api/sessions/{session_id}` | Get session |
| POST | `/api/sessions/{session_id}/complete` | Mark completed; updates progress and streaks |

## Ratings

**POST /api/sessions/{session_id}/ratings**

```json
{
  "evaluator_id": "uuid",
  "evaluated_user_id": "uuid",
  "participation": 5,
  "helpfulness": 4,
  "collaboration": 5,
  "contribution": 4
}
```

Errors: `400` self-rating, `403` not a participant, `409` already rated, `422` value outside 1–5.

## Progress

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/users/{user_id}/progress` | `completed_sessions`, `total_study_minutes`, `current_streak`, `longest_streak` |
| GET | `/api/parties/{party_id}/progress` | Team totals and team streak |

## Health

`GET /api/health` returns `{ "status": "ok" }` (used by Cloud Run).
