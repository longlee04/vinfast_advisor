"""Authentication module.

Organized as a Clean Architecture boundary per `AGENTS.md`. `config` and
`composition` sit at the module root because they form the composition root
that wires concrete adapters; the inner `domain/`, `application/`,
`infrastructure/` and `presentation/` packages are added by later todos.
"""
