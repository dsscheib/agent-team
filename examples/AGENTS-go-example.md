# Example only — adapt to your project

## Application
Inventory application for hobbyists and small labs.

## Stack
- Backend: Go
- Templates: Templ
- Interactions: HTMX, Alpine.js
- Styling: Tailwind CSS, DaisyUI
- Data: SQLite
- Hosting: resource-constrained Linux/NAS

## Engineering expectations
- Preserve existing API and HTML contracts.
- Keep authorization checks server-side.
- Use explicit SQLite transactions for multi-step write operations.
- Use isolated databases for tests; do not test against production data.
- Run the repository's documented Go test, format and lint commands.

## Delegation
Delegate server-side work to backend, data consistency to database, UI changes to frontend, and regression coverage to integration-tester. Use auditor-advisor for independent reviews on consequential changes.
