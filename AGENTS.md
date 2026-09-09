# Project Instructions

## Project Baseline

- This repository targets Python 3.11 or newer.
- The backend uses FastAPI and Pydantic v2.
- Product source code belongs under `src/`.
- Automated tests belong under `tests/` and use pytest.
- Declare and maintain Python dependencies in `pyproject.toml`.
- Keep secrets, credentials, API keys, and production tokens out of version control.

## Architecture Boundaries

- Preserve the existing top-level project structure unless the user explicitly approves a broader restructuring.
- Do not refactor unrelated agent, API, service, or model code while implementing a scoped feature.
- Authentication functionality may use Clean Architecture inside `src/auth/` without requiring the rest of the repository to adopt the same structure.
- Organize `src/auth/` into these boundaries:
  - `domain/`: authentication entities, value objects, domain policies, and domain errors.
  - `application/`: use cases and ports required by those use cases.
  - `infrastructure/`: adapters for persistence, cryptography, tokens, email delivery, and other external systems.
  - `presentation/`: FastAPI routes, request and response schemas, dependencies, cookie handling, and HTTP error mapping.
- Within the Auth module, dependencies must point inward:
  - Presentation may depend on Application and Domain.
  - Infrastructure may implement ports defined by Application.
  - Application may depend on Domain.
  - Domain must not depend on Application, Infrastructure, or Presentation.
- Auth Domain and Application code must not directly depend on FastAPI, SQLAlchemy, Alembic, SendGrid, or concrete persistence and transport implementations.
- Wire concrete Auth adapters at the application composition boundary rather than constructing infrastructure dependencies inside domain or use-case code.
- Register Auth routes through the existing FastAPI application without changing the behavior of existing chat, agent-status, or health endpoints unless explicitly required.

## Python Conventions

- Add complete parameter and return type annotations to Python functions and methods.
- Use Pydantic models at external input, output, and configuration boundaries.
- Use `snake_case` for modules, files, functions, and variables.
- Use `PascalCase` for classes and Pydantic models.
- Use `UPPER_SNAKE_CASE` for constants.
- Keep imports ordered as standard library, third-party packages, then local imports.
- Add docstrings to public functions, methods, classes, and modules where their purpose is not self-evident.
- Prefer small, focused functions and explicit dependencies.
- Catch specific exceptions and preserve their causal context.
- Do not use a bare `except`.
- Do not expose internal exception messages, credentials, token values, or sensitive account state in HTTP responses or logs.

## Database and Migration Rules

- Manage relational schema changes through Alembic migrations.
- Do not rely on runtime table creation or manually executed production SQL as the primary migration path.
- Keep SQLAlchemy models and repository implementations in infrastructure code.
- Keep transaction boundaries explicit at the application or infrastructure boundary.
- Migrations must provide a deterministic upgrade path and a safe downgrade when the change is reversible.
- Authentication secrets and session credentials must be stored only in hashed or otherwise non-recoverable form when plaintext recovery is not required.

## Testing and Verification

- Use automated tests for every behavior change and bug fix.
- Follow test-driven development for new Auth behavior: add or update a failing test before implementing the behavior, then make the smallest change that passes it.
- Add Auth domain and application tests under `tests/auth/unit/`.
- Add Auth HTTP, database, migration, cookie, and session integration tests under `tests/auth/integration/`.
- Test both successful behavior and relevant failure paths.
- Authentication tests must cover security-sensitive boundaries such as:
  - password policy and password verification;
  - email verification requirements;
  - temporary-password enforcement;
  - access and refresh token validation;
  - refresh-token rotation and replay rejection;
  - current-session and all-session revocation;
  - authorization by role;
  - cookie and CSRF behavior;
  - expiry, invalid-token, and revoked-session paths.
- External email delivery must be replaced by a deterministic test adapter in automated tests.
- Tests must not call real SendGrid, OpenAI, or other paid external services.
- Before claiming a change is complete, run:
  - `ruff check src/ tests/`
  - `pytest tests/ -v --tb=short`
- Run any additional migration, type-checking, or security-focused verification introduced by the affected feature.
- Completion claims must include the commands run and their actual outcomes.

## Scope and Change Safety

- Keep changes limited to the approved task.
- Do not overwrite, revert, reformat, or include unrelated user changes.
- Inspect the working tree before implementation and treat unrelated modified or untracked paths as out of scope.
- Do not modify AI usage logging hooks, grading integrations, generated artifacts, or template documentation unless the task explicitly requires it.
- Do not silently change public HTTP contracts, cookie names, environment-variable names, database schema, or external dependencies; record such decisions in the approved implementation plan first.
- Do not add compatibility layers, duplicate implementations, or speculative abstractions unless required by an existing consumer or an approved migration strategy.

## Planning and Execution

- Implementation plans must identify exact files or directories, dependency order, acceptance criteria, automated QA scenarios, and required migrations.
- Plans for Auth must preserve the module boundaries and dependency direction defined above.
- Plan approval authorizes writing the plan, not implementing it.
- Product-code execution begins only when the user explicitly starts an approved plan in a separate execution workflow.
