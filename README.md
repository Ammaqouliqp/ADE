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

---

▶️ Usage
1.	Run the ADE application:
```bash
python main.py
```
2.	Use File → Open DB to open an existing SQLite database file.
3.	Select a table from the left panel to view its contents.
4.	Double click any editable cell to modify its value. Press Enter to save.
5.	Use the menus or right click options to:
  o	Add / Delete rows
  o	Add columns
  o	Undo / Redo changes
  o	Export to CSV / Excel
  o	View ER diagram
  o	Execute custom SQL queries

```bash
ADE/
├── main.py                # Core application
├── LICENSE                # Open source license
├── README.md              # This documentation
└── requirements.txt       # Dependency list
```
🙌 Contribution

Contributions, bug reports, feature requests, and pull requests are welcome!
Feel free to open issues or submit changes.
---
❤️ Acknowledgements

Thanks to the open source community for PyQt6 and SQLite — enabling powerful GUIs with minimal setup.
