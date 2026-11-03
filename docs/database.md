# Database Design

PostgreSQL, accessed via SQLAlchemy. All primary keys are UUIDs.

## users

| Field         | Type      | Notes |
| ------------- | --------- | ----- |
| id            | UUID      | PK |
| name          | VARCHAR   | |
| university    | VARCHAR   | |
| major         | VARCHAR   | |
| year_of_study | INTEGER   | |
| learning_style | VARCHAR  | optional (visual, discussion, practice…) |
| study_format  | VARCHAR   | `online` / `offline` / `both` |
| created_at    | TIMESTAMP | |

## subjects

| Field | Type    | Notes |
| ----- | ------- | ----- |
| id    | UUID    | PK |
| name  | VARCHAR | unique |

## user_subjects

| Field           | Type    | Notes |
| --------------- | ------- | ----- |
| user_id         | UUID    | FK → users, PK part |
| subject_id      | UUID    | FK → subjects, PK part |
| knowledge_level | INTEGER | 1–5 |

## user_goals

| Field   | Type    | Notes |
| ------- | ------- | ----- |
| id      | UUID    | PK |
| user_id | UUID    | FK → users |
| goal    | VARCHAR | |

## availability

| Field       | Type    | Notes |
| ----------- | ------- | ----- |
| id          | UUID    | PK |
| user_id     | UUID    | FK → users |
| day_of_week | INTEGER | 0 = Monday … 6 = Sunday |
| start_time  | TIME    | |
| end_time    | TIME    | |

## study_parties

| Field      | Type      | Notes |
| ---------- | --------- | ----- |
| id         | UUID      | PK |
| name       | VARCHAR   | |
| created_by | UUID      | FK → users |
| created_at | TIMESTAMP | |

## party_members

| Field     | Type      | Notes |
| --------- | --------- | ----- |
| party_id  | UUID      | FK → study_parties, PK part |
| user_id   | UUID      | FK → users, PK part |
| joined_at | TIMESTAMP | |

Constraint: 2–5 members per party (enforced in the service layer).

## study_sessions

| Field            | Type      | Notes |
| ---------------- | --------- | ----- |
| id               | UUID      | PK |
| party_id         | UUID      | FK → study_parties |
| title            | VARCHAR   | |
| subject          | VARCHAR   | |
| scheduled_at     | TIMESTAMP | |
| duration_minutes | INTEGER   | |
| status           | VARCHAR   | `scheduled` / `completed` / `cancelled` |
| completed_at     | TIMESTAMP | nullable, used for streaks |

## session_participants

| Field      | Type    | Notes |
| ---------- | ------- | ----- |
| session_id | UUID    | FK → study_sessions, PK part |
| user_id    | UUID    | FK → users, PK part |
| attended   | BOOLEAN | |

## ratings

| Field             | Type    | Notes |
| ----------------- | ------- | ----- |
| id                | UUID    | PK |
| session_id        | UUID    | FK → study_sessions |
| evaluator_id      | UUID    | FK → users |
| evaluated_user_id | UUID    | FK → users |
| participation     | INTEGER | 1–5 |
| helpfulness       | INTEGER | 1–5 |
| collaboration     | INTEGER | 1–5 |
| contribution      | INTEGER | 1–5 |

Constraints: `UNIQUE(session_id, evaluator_id, evaluated_user_id)`, `CHECK(evaluator_id <> evaluated_user_id)`; both users must be participants of the session.

## progress

| Field               | Type    | Notes |
| ------------------- | ------- | ----- |
| id                  | UUID    | PK |
| user_id             | UUID    | FK → users, unique |
| completed_sessions  | INTEGER | |
| total_study_minutes | INTEGER | |
| current_streak      | INTEGER | |
| longest_streak      | INTEGER | |
| last_study_date     | DATE    | needed to compute streak continuation |

Team progress can be computed on the fly from `study_sessions` of the party, or stored in a similar `party_progress` table.
