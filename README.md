# ADE — SQLite GUI Manager

A desktop database management tool built with **PyQt6** and **SQLite**, designed for easy viewing and editing of SQLite databases. ADE allows you to browse tables, edit cell values directly, manage schema elements, export data, visualize schema relationships, and track change history — all within a single interface.

---

## 🚀 Features

### Table & Data Management
- Load any SQLite database (`.db`, `.sqlite`)
- Browse and select tables
- View table records in a spreadsheet-like grid
- Edit cell values inline with immediate save to database
- Add or delete rows
- Add new columns with type specification
- Rename tables
- Delete tables

### User-Friendly Edit & Logging
- Undo / Redo support (Ctrl+Z / Ctrl+Y)
- Visual log panel for all actions (success and error)
- Keyboard shortcuts for copy/paste (Ctrl+C / Ctrl+V)
- Right‑click context menus for tables and table cells

### Export & Schema Tools
- Export tables to CSV
- Export tables to Excel (`.xlsx`)
- ER Diagram viewer showing table columns and foreign keys
- SQL Console for executing custom SQL queries

---

## 📦 Installation

1. Clone the repository:

```bash
git clone https://github.com/Ammaqouliqp/ADE.git
cd ADE
```
2. Create and activate a Python virtual environment (optional but recommended):
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```
*If you don’t have a requirements.txt yet, install manually:
```bash
pip install PyQt6 openpyxl
```
