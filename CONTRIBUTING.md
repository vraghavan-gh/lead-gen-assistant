# Contributing to Lead Gen Assistant

## Getting Started

1. Fork the repo and create a branch: `git checkout -b feature/my-feature`
2. Install dev dependencies: `pip install -r requirements.txt pytest flake8`
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

## Code Style

- Follow PEP 8, max line length 100
- Docstrings on all public methods
- Type hints on all function signatures
- New agents must inherit from `BaseAgent`

## Adding a New Agent

1. Create `agents/my_agent.py` inheriting from `BaseAgent`
2. Define a `tool_schema` for structured Claude output
3. Implement `process()` method
4. Add tests in `tests/test_pipeline.py`
5. Register in `pipeline.py`
6. Document in `docs/architecture.md`

## Scoring Config Changes

All scoring rule changes go in `config/scoring_config.yaml` — never hardcode thresholds in agent code.

## Security

- Never commit `.env`, `pat_token`, or any credentials
- PII must stay in designated columns with `data_classification` tags
- All agent reasoning logs should be reviewed for PII before enabling in production
