# Contributing

## Branches

| Branch | Purpose |
| ------ | ------- |
| `main` | Stable, demo-ready application. **No direct commits.** |
| `develop` | Integration branch; all feature PRs target it |
| `feature/backend` | Backend work (Person 1) |
| `feature/matching` | Matching + Gemini (Person 2) |
| `feature/frontend` | Frontend (Person 3) |
| `feature/cloud` | Cloud / deployment / QA (Person 4) |

Smaller task branches are welcome too, e.g. `feature/profile-form`, `fix/streak-reset`.

## Workflow

1. Pull the latest changes.
2. Create or switch to a feature branch.
3. Implement the feature.
4. Commit changes.
5. Push the branch.
6. Open a Pull Request into `develop` and link the issue (`Closes #12`).
7. Get one review, then merge.

`develop` is merged into `main` when a working milestone is reached.

```bash
git clone https://github.com/Mark0000dev/StudyMate-AI.git
cd StudyMate-AI
git checkout develop
git pull
git checkout -b feature/matching
git add .
git commit -m "Implement matching algorithm"
git push origin feature/matching
```

## Commit messages

Short, imperative: `Add profile form`, `Fix streak reset on missed day`.

## Secrets

Never commit `.env`, API keys, or service-account JSON. Use `backend/.env.example` as the template.
