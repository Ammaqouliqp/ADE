# Contributing Guidelines – Advanced Database Editor (ADE)

Thank you for your interest in contributing to ADE.
This project aims to be a **safe, professional-grade SQLite database editor** built with PyQt.

To maintain stability, safety, and long-term maintainability, all contributions must follow the rules below.

---

## Core Principles

1. **Safety First**
   - No data-destructive operation may be added without explicit safeguards.
   - Any delete, drop, or overwrite operation must:
     - Require user confirmation
     - Be reversible where possible
     - Be blocked if the operation is ambiguous or unsafe

2. **No Silent Behavior**
   - Every action must be visible to the user.
   - Errors must be logged or shown — never swallowed.

3. **SQLite Reality Compliance**
   - Do not add features SQLite does not safely support.
   - If SQLite has limitations (e.g. DROP COLUMN), the UI must explain this clearly.

4. **Professional Editor Behavior**
   - ADE should behave like real tools (SQLiteStudio, DBeaver, DB Browser).
   - UI decisions must follow established database editor conventions.

---

## What You MAY Add

- Export formats (CSV, Excel, SQL, JSON, etc.)
- Import tools with preview and validation
- Schema inspectors and visualizers
- Undo/redo systems
- Non-destructive helpers (filters, search, sorting)
- Performance improvements
- UI/UX refinements
- Documentation improvements
- Tests

---

## What You MAY NOT Add (Without Discussion)

- Unsafe deletes (no primary key, no row identifier)
- Automatic schema migrations
- Implicit data type conversions
- Background mutations without UI feedback
- Hard-coded database assumptions
- Breaking changes without version bump

---

## Code Rules

- Python 3.10+
- PyQt6 only (no mixed Qt bindings)
- Use parameterized SQL
- No global state
- No blocking UI calls during long operations
- Follow existing architecture — do not rewrite unless approved

---

## Pull Request Requirements

Every PR must include:
- Clear description of the change
- Reason for the change
- Risk analysis (if data-related)
- Screenshots or logs (if UI-related)

PRs that break safety guarantees will be rejected.

---

## Final Note

ADE prioritizes **data integrity over convenience**.
If in doubt — block the action and explain why.

Thank you for helping improve the project.
