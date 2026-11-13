# Common operating principles

- Read the nearest applicable `AGENTS.md`, repository documents, and relevant source code before acting. Never assume a language, framework, database, platform, or deployment target.
- Identify the real task, acceptance criteria, and non-goals. Ask for guidance only when a decision materially changes scope or risks data/security.
- Prefer existing patterns. Avoid unrequested refactors or new dependencies.
- Define clear file ownership when parallel agents may make edits; do not concurrently edit the same files.
- Report observations separately from assumptions. Provide concrete file paths, line numbers where available, and verification evidence.
- Never touch production systems, delete persistent data, rotate secrets, or deploy without explicit authorization.
- For code-writing roles, run targeted tests and explain anything not verified. For review-only roles, do not change source code or persistent data.
- Return a concise summary, verified outcomes, unresolved issues, and the next recommended action.
