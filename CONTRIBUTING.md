# Contributing to Convolvger

Thank you for contributing to Convolvger.

## Development

Convolvger is developed as a local-first Python project.

Set up the development environment:

uv sync

Run tests:

uv run pytest

Run linting:

uv run ruff check .

Run type checking:

uv run mypy src tests

## Architecture

Provider-specific extraction logic belongs inside the corresponding provider adapter.

Provider implementations must not leak provider-specific data structures into the core model.

The intended flow is:

Source
  ↓
Provider Detection
  ↓
Provider Adapter
  ↓
Canonical Conversation Model
  ↓
Validation
  ↓
Renderer

Changes should preserve this separation.

## Pull Requests

Keep pull requests focused on one logical change.

Include tests for new behavior and update documentation when public behavior or interfaces change.

## Provider Adapters

New providers should include:

- Provider detection
- Source fetching
- Conversation extraction
- Fixtures representing real public share formats
- Tests covering extraction behavior
- Handling for unsupported or missing content

The extraction pipeline must not depend on an LLM.

## License

By contributing to Convolvger, you agree that your contributions will be licensed under the MIT License.
