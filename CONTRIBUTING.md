# Contributing

1. Create a focused branch from `main`.
2. Keep Vertex AI credentials and `.env` files out of commits.
3. Run backend tests, the React production build, and Playwright tests before opening a pull request.
4. Mock Gemini in automated tests. Pull-request workflows must not consume live model quota.
5. Document changes to prompts, tools, models, pricing, or budget policy.

```bash
pytest
cd frontend && npm run build
cd .. && npm run test:e2e
```