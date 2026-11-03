# StudyMate AI: Technical Specification

**Project Type:** AI-powered collaborative learning platform
**Team Size:** 4 developers
**Backend:** Python + FastAPI
**Frontend:** React + Vite
**Database:** PostgreSQL
**AI:** Google Gemini API
**Deployment:** Google Cloud Run

---

## 1. Project Overview

StudyMate AI is an AI-powered platform that helps university students find compatible study partners, create study teams, organize study sessions, and track their academic progress together.

The platform matches students based on academic subjects, knowledge and skill levels, learning goals, availability, and learning preferences.

Students can create Study Parties, participate in study sessions, rate their teammates, and maintain shared study streaks.

### Main objectives

1. Help students find compatible study partners.
2. Encourage collaborative learning.
3. Improve student engagement and motivation.
4. Track individual and team learning progress.
5. Build consistent study habits through streaks.

## 2. Target Users

University students who:

- Want to prepare for exams together.
- Need help with specific subjects.
- Want to improve their academic performance.
- Prefer collaborative learning.
- Need motivation to study regularly.

## 3. Core Features

### 3.1 Student Profile

Profile fields: name, university, major, year of study, subjects, knowledge levels, learning goals, availability, preferred learning style, preferred study format (online/offline).

**Knowledge levels**

| Level | Description  |
| ----- | ------------ |
| 1     | Beginner     |
| 2     | Basic        |
| 3     | Intermediate |
| 4     | Advanced     |
| 5     | Expert       |

**Learning goals (examples):** prepare for an exam, complete an assignment, improve understanding of a subject, learn a new skill, prepare for an interview.

### 3.2 AI Student Matching

**Matching criteria**

| Criterion               | Weight |
| ----------------------- | ------ |
| Subject compatibility   | 30%    |
| Academic goals          | 25%    |
| Complementary knowledge | 20%    |
| Schedule compatibility  | 15%    |
| Learning preferences    | 10%    |

These weights are initial values and can be adjusted.

**Matching process**

1. User submits their profile.
2. Backend retrieves other available student profiles.
3. Matching algorithm calculates compatibility scores.
4. Students are ranked by compatibility.
5. Gemini generates explanations for the matches.
6. Frontend displays recommended students.

**Matching score:** each criterion produces a score from 0 to 1.

```
Match Score = Σ(weight × criterion_score) × 100   → 0..100
```

**Matching explanation (example):**

> "You and Alex are a strong match because you share similar academic goals, have complementary Python and SQL skills, and are available at similar times."

Gemini must only explain compatibility using information provided by the matching algorithm. It must not invent user characteristics.

### 3.3 Study Partner Selection

Users can view recommended students, their compatibility scores and explanations, send a study invitation, and accept or reject invitations. For the MVP, users can select a recommended student and create a Study Party.

### 3.4 Study Party

A Study Party is a small learning team with: name, members, subjects, learning goals, creation date, study sessions, team progress, and team streak.

**MVP limitation:** each party contains 2–5 members.

### 3.5 Study Sessions

Session information: title, subject, date, duration, participants, learning goals, status.

**Workflow**

1. A party member creates a session.
2. Other members join or confirm participation.
3. The session is completed.
4. Participants submit feedback.
5. Team progress and streaks are updated.

### 3.6 Teammate Ratings

After a completed session, participants rate teammates from 1 to 5 on **participation, helpfulness, collaboration, contribution**.

**Rules**

- Students can only rate participants from their own session.
- One rating per evaluator per participant per session.
- Users cannot rate themselves.
- Ratings are private in the MVP.
- No public leaderboard.

Feedback may be used to improve future recommendations.

### 3.7 Study Progress

- **User:** completed sessions, total study hours, subjects studied, personal goals, weekly progress.
- **Party:** total completed sessions, team study hours, shared goals, team streak.

### 3.8 Study Streaks

A streak is the number of consecutive days on which a student or team completes a study session.

- A completed session counts toward the streak.
- The streak increases when a session is completed on a new consecutive day.
- Missing a day resets the streak.
- Individual and team streaks are tracked separately.
- MVP: calendar days in one defined timezone (configured via `APP_TIMEZONE`).

## 4. MVP Scope

**Must-have:** profile creation, knowledge levels, matching algorithm, compatibility score, AI explanation, recommended students, Study Party creation, session creation & completion, teammate feedback, individual & team progress, streaks.

**Optional (only after the MVP works):** AI onboarding chatbot, AI study session planner, group matching optimization, chat, calendar integration, gamification/achievements, notifications.

## 5. Technology Stack

- **Frontend:** React, Vite, JavaScript or TypeScript, Tailwind CSS, Axios, React Router
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Gemini API SDK
- **Infrastructure:** GitHub, Google Cloud Run, Secret Manager or env vars, Cloud SQL (optional), Google AI Studio / Gemini API

For the hackathon, use the simplest deployment configuration possible.

## 6. System Architecture

See [architecture.md](architecture.md).

## 7. Database Design

See [database.md](database.md).

## 8. API Specification

See [api.md](api.md).

## 9. Frontend Pages

| # | Page             | Content                                                     |
| - | ---------------- | ----------------------------------------------------------- |
| 1 | Landing          | Introduction, main features, Get Started button             |
| 2 | Student Profile  | Profile form, subjects, knowledge levels, goals, availability |
| 3 | Matching Results | Recommended students, scores, explanations, select partner  |
| 4 | Study Parties    | Current parties, members, team progress, create party       |
| 5 | Study Sessions   | Upcoming sessions, details, complete session button         |
| 6 | Feedback         | Teammate rating form, submission                            |
| 7 | Dashboard        | Completed sessions, hours, individual & team streak, charts |

## 10. Repository Structure

```
StudyMate-AI/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/   Navbar, StudentCard, MatchCard, PartyCard, ProgressCard
│   │   ├── pages/        Home, Profile, Matching, Parties, Sessions, Feedback, Dashboard
│   │   ├── services/     api.js
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/          users, matches, parties, sessions, ratings, progress
│   │   ├── services/     matching, gemini_service, streak_service, progress_service
│   │   ├── models/       user, party, session, rating
│   │   ├── schemas/      user, match, party, session
│   │   ├── database.py
│   │   └── config.py
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── docs/
├── .gitignore
├── README.md
└── LICENSE
```

## 11. Team Responsibilities

- **Person 1: Backend Developer / Team Lead:** FastAPI architecture, endpoints, DB integration, party & session logic, frontend–backend integration.
- **Person 2: AI / Matching Developer:** matching algorithm, compatibility score, Gemini integration, explanations, matching tests.
- **Person 3: Frontend Developer:** React app, UI/UX, profile form, matching results, party dashboard, progress & streak UI.
- **Person 4: Cloud / Database / QA:** Google Cloud setup, deployment, DB assistance, testing, bug tracking, documentation & presentation.

## 12. GitHub Workflow

See [CONTRIBUTING.md](../CONTRIBUTING.md).

## 13. Development Roadmap

| Phase | Name            | Scope                                                         |
| ----- | --------------- | ------------------------------------------------------------- |
| 1     | Setup           | Repo, environments, skeletons, Gemini API, API contracts      |
| 2     | Core            | Profiles, DB models, matching, frontend pages, parties        |
| 3     | Integration     | Frontend ↔ backend, Gemini, matching & party tests            |
| 4     | Additional      | Sessions, ratings, progress, streaks                          |
| 5     | Deployment      | Deploy backend & frontend, env vars, production test          |
| 6     | Finalization    | Bug fixes, demo, README, presentation, full user-flow test    |

## 14. Definition of Done

- [ ] A student can create a profile.
- [ ] The system recommends compatible students.
- [ ] Matching scores are calculated.
- [ ] Gemini generates explanations.
- [ ] Students can create Study Parties.
- [ ] Study sessions can be completed.
- [ ] Participants can submit ratings.
- [ ] Progress and streaks are updated.
- [ ] The application is publicly accessible.
- [ ] The entire demo works without critical errors.

## 15. Final Demo Scenario

See [presentation.md](presentation.md).
