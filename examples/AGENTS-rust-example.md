# Example only — adapt to your project

## Application
Experimental web application comparing Rust architecture with a similar application in another language.

## Stack
- Backend: Rust
- Framework: choose based on the actual project (do not assume Axum)
- Templates and database: read Cargo.toml and architecture documentation
- Deployment: determined by repository configuration

## Engineering expectations
- Follow established crate/module boundaries.
- Prefer explicit error handling and tests for boundary conditions.
- Keep async work non-blocking as appropriate for the chosen runtime.
- Run documented Cargo fmt, Clippy, and test commands.
- Do not introduce libraries solely because they are popular.

## Delegation
The same backend, database, integration-tester, security, and auditor-advisor agents apply; agents must inspect project dependencies before recommending patterns.
