# Contributing

## Local Setup

```bash
git clone https://github.com/yachika-yashu/MedVault.git
cd MedVault
cp .env.example .env
# Add your OPENAI_API_KEY to .env
docker compose up -d --build
```

Open http://localhost:8501 to verify everything is running.

## Making Changes

1. Create a branch: `git checkout -b feat/your-feature`
2. Make your changes
3. Run the test suite against the live stack: `python test_all_features.py`
4. Open a pull request — describe what the change does and why

## Reporting Bugs

Open a GitHub Issue. Include:
- What you did
- What you expected
- What actually happened
- Output of `docker compose logs api --tail=50`

## Questions

Open an issue or see the [Architecture section in the README](./README.md#architecture).
