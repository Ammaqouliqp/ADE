# Advanced Database Editor (ADE)

ADE is a **safe, professional SQLite database editor** built with **Python and PyQt6**.

It is designed for developers who need **direct database control** while maintaining **data integrity**, **clarity**, and **predictability**.

---

## Key Features

### Database Management
- Open and inspect SQLite databases
- List and manage tables
- Rename and drop tables (with confirmation)

### Data Editing
- Inline cell editing
- Add rows safely
- Delete rows **only when a PRIMARY KEY exists**
- Selection-based row operations

### Schema Operations
- Add columns
- View table schema
- SQLite-safe restrictions enforced

### Export System
- Export table to CSV
- Export table to Excel (.xlsx)
- Export table to SQL INSERT script
- Export table to JSON
- Export full database copy
- Export full SQL dump

### UI & UX
- Context menus (right-click)
- Dynamic action enabling/disabling
- Detailed operation logs
- Professional database-editor behavior

---

## Safety Philosophy

ADE **never lies to the user**.

If an operation:
- Is unsafe
- Is ambiguous
- Is not supported by SQLite

It will be **blocked and explained**.

This is intentional.

---

## Requirements

- Python 3.10+
- SQLite 3
- PyQt6
- openpyxl

---

## Installation

```bash
git clone https://github.com/Ammaqouliqp/ADE.git
cd ADE
pip install -r requirements.txt
python Advanced_database_editor.py
```

## Project Structure
```bash
ADE/
├── Advanced_database_editor.py
├── README.md
├── CONTRIBUTING.md
├── requirements.txt
├── LICENSE
```

