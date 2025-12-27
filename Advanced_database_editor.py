import sys
import sqlite3
import csv
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from openpyxl import Workbook

# =========================
# LOG MANAGER
# =========================
class LogManager:
    def __init__(self, widget: QTextEdit):
        self.widget = widget

    def log(self, message: str, error=False):
        color = "#ff6b6b" if error else "#6bff95"
        self.widget.append(f'<span style="color:{color}">{message}</span>')

# =========================
# UNDO / REDO MANAGER
# =========================
class UndoRedoManager:
    def __init__(self, logger: LogManager):
        self.undo_stack = []
        self.redo_stack = []
        self.logger = logger

    def push(self, undo_sql, redo_sql, params=()):
        self.undo_stack.append((undo_sql, redo_sql, params))
        self.redo_stack.clear()

    def undo(self, db):
        if not self.undo_stack:
            self.logger.log("Nothing to undo", error=True)
            return
        undo_sql, redo_sql, params = self.undo_stack.pop()
        db.execute(undo_sql, params)
        self.redo_stack.append((undo_sql, redo_sql, params))
        self.logger.log("Undo executed")

    def redo(self, db):
        if not self.redo_stack:
            self.logger.log("Nothing to redo", error=True)
            return
        undo_sql, redo_sql, params = self.redo_stack.pop()
        db.execute(redo_sql, params)
        self.undo_stack.append((undo_sql, redo_sql, params))
        self.logger.log("Redo executed")

# =========================
# DATABASE MANAGER
# =========================
class DatabaseManager:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def tables(self):
        return [r[0] for r in self.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

    def table_schema(self, table):
        return self.execute(f"PRAGMA table_info({table})").fetchall()

    def foreign_keys(self, table):
        return self.execute(f"PRAGMA foreign_key_list({table})").fetchall()

    def read_table(self, table):
        cur = self.execute(f"SELECT rowid, * FROM {table}")
        rows = cur.fetchall()
        headers = [d[0] for d in cur.description]
        return headers, rows

# =========================
# SQLITE TABLE MODEL
# =========================
class SQLiteTableModel(QAbstractTableModel):
    def __init__(self, db, table, logger, undo_redo):
        super().__init__()
        self.db = db
        self.table = table
        self.logger = logger
        self.undo_redo = undo_redo
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        headers, rows = self.db.read_table(self.table)
        self.headers = headers
        self.rows = [dict(r) for r in rows]  # <-- convert to mutable dicts
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return str(self.rows[index.row()][self.headers[index.column()]])
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if self.headers[index.column()] == "rowid":
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False

        col = self.headers[index.column()]
        if col == "rowid":
            return False

        row = self.rows[index.row()]
        rowid = row.get("rowid")
        old_value = row.get(col)

        # Ignore empty or unchanged edits
        if value is None or str(value).strip() == "" or str(value) == str(old_value):
            return False

        try:
            redo_sql = f"UPDATE {self.table} SET {col}=? WHERE rowid=?"
            undo_sql = f"UPDATE {self.table} SET {col}=? WHERE rowid=?"
            self.db.execute(redo_sql, (value, rowid))
            self.undo_redo.push(undo_sql, redo_sql, (old_value, rowid))

            row[col] = value
            self.dataChanged.emit(index, index)
            self.logger.log(f"{self.table}.{col} updated (rowid={rowid})")
            return True
        except Exception as e:
            self.logger.log(str(e), error=True)
            return False

    def headerData(self, section, orientation, role):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.headers[section] if orientation == Qt.Orientation.Horizontal else section + 1

# =========================
# ER DIAGRAM
# =========================
class ERDiagramWindow(QDialog):
    def __init__(self, db):
        super().__init__()
        self.setWindowTitle("ER Diagram")
        self.resize(600, 500)

        view = QTextEdit()
        view.setReadOnly(True)

        for table in db.tables():
            view.append(f"<b>{table}</b>")
            for col in db.table_schema(table):
                view.append(f"  • {col[1]} ({col[2]})")
            for fk in db.foreign_keys(table):
                view.append(f"  ↳ FK: {fk[3]} → {fk[2]}")
            view.append("")

        layout = QVBoxLayout(self)
        layout.addWidget(view)

# =========================
# MAIN WINDOW
# =========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SQLite GUI Manager")
        self.resize(1400, 900)

        self.db = None
        self.model = None

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.logger = LogManager(self.log_view)
        self.undo_redo = UndoRedoManager(self.logger)

        self.table_list = QListWidget()
        self.table_view = QTableView()

        self.setup_ui()
        self.setup_menu()
        self.setup_docks()
        self.setup_shortcuts()
        self.setup_context_menus()

    # ---------------- UI ----------------
    def setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)

        self.table_list.setFixedWidth(250)
        layout.addWidget(self.table_list)
        layout.addWidget(self.table_view)

        self.setCentralWidget(central)

        self.setStyleSheet("""
            QListWidget, QTableView {
                border-radius: 14px;
                background-color: #1e1e1e;
                color: #eee;
            }
            QTextEdit {
                background-color: #111;
            }
        """)

        self.table_list.itemClicked.connect(self.load_table)

    # ---------------- DOCKS ----------------
    def setup_docks(self):
        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        self.sql_dock = QDockWidget("SQL Console", self)
        self.sql_input = QTextEdit()
        btn = QPushButton("Execute")
        btn.clicked.connect(self.exec_sql)

        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(self.sql_input)
        l.addWidget(btn)

        self.sql_dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.sql_dock)

    # ---------------- MENU ----------------
    def setup_menu(self):
        mb = self.menuBar()

        file = mb.addMenu("File")
        file.addAction("Open DB", self.open_db)
        file.addAction("Import CSV", self.import_csv)
        file.addAction("Export CSV", self.export_csv)
        file.addAction("Export Excel", self.export_excel)

        edit = mb.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.safe_undo)
        edit.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(lambda: self.undo_redo.redo(self.db))
        edit.addAction(redo_action)

        view = mb.addMenu("View")
        view.addAction("ER Diagram", self.show_er)

    # ---------------- SHORTCUTS ----------------
    def setup_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Copy, self, self.copy_cells)
        QShortcut(QKeySequence.StandardKey.Paste, self, self.paste_cells)

    # ---------------- CONTEXT MENUS ----------------
    def setup_context_menus(self):
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.table_context_menu)

        self.table_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_list.customContextMenuRequested.connect(self.table_list_context)

    def table_list_context(self, pos):
        menu = QMenu()
        menu.addAction("Add Table", self.add_table)
        menu.addAction("Remove Table", self.remove_table)
        menu.addAction("Rename Table", self.rename_table)
        menu.exec(self.table_list.mapToGlobal(pos))

    def table_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        menu = QMenu()

        add_row = menu.addAction("Add Row")
        del_row = menu.addAction("Delete Selected Rows")
        del_row.setEnabled(bool(self.table_view.selectionModel().selectedRows()))

        add_col = menu.addAction("Add Column")
        del_col = menu.addAction("Delete Column")
        del_col.setEnabled(index.isValid())

        action = menu.exec(self.table_view.viewport().mapToGlobal(pos))

        if action == add_row:
            self.add_row()
        elif action == del_row:
            self.delete_rows()
        elif action == add_col:
            self.add_column()
        elif action == del_col:
            self.delete_column(index.column())

    # ---------------- ACTIONS ----------------
    def open_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SQLite DB", "", "*.db *.sqlite")
        if not path:
            return
        self.db = DatabaseManager(path)
        self.table_list.clear()
        self.table_list.addItems(self.db.tables())
        self.logger.log("Database opened")

    def load_table(self, item):
        self.model = SQLiteTableModel(self.db, item.text(), self.logger, self.undo_redo)
        self.table_view.setModel(self.model)

    def exec_sql(self):
        try:
            self.db.execute(self.sql_input.toPlainText())
            self.logger.log("SQL executed")
            if self.model:
                self.model.refresh()
        except Exception as e:
            self.logger.log(str(e), error=True)

    def safe_undo(self):
        if self.db:
            self.undo_redo.undo(self.db)
            if self.model:
                self.model.refresh()
        else:
            self.logger.log("No database loaded", error=True)

    def add_row(self):
        self.db.execute(f"INSERT INTO {self.model.table} DEFAULT VALUES")
        self.model.refresh()
        self.logger.log("Row added")

    def delete_rows(self):
        rows = {i.row() for i in self.table_view.selectionModel().selectedRows()}
        for r in rows:
            rowid = self.model.rows[r]["rowid"]
            self.db.execute(f"DELETE FROM {self.model.table} WHERE rowid=?", (rowid,))
        self.model.refresh()
        self.logger.log("Rows deleted")

    def add_column(self):
        name, ok = QInputDialog.getText(self, "Column Name", "Name:")
        if not ok:
            return
        coltype, ok = QInputDialog.getText(self, "Column Type", "Type (TEXT, INTEGER...):")
        if ok:
            self.db.execute(f"ALTER TABLE {self.model.table} ADD COLUMN {name} {coltype}")
            self.model.refresh()
            self.logger.log("Column added")

    def delete_column(self, col):
        self.logger.log("SQLite does not support DROP COLUMN directly", error=True)

    def add_table(self):
        name, ok = QInputDialog.getText(self, "Table Name", "Name:")
        if ok:
            self.db.execute(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY)")
            self.table_list.addItem(name)
            self.logger.log("Table created")

    def remove_table(self):
        item = self.table_list.currentItem()
        if not item:
            return
        self.db.execute(f"DROP TABLE {item.text()}")
        self.table_list.takeItem(self.table_list.currentRow())
        self.logger.log("Table removed")

    def rename_table(self):
        item = self.table_list.currentItem()
        if not item:
            return
        new, ok = QInputDialog.getText(self, "Rename Table", "New name:")
        if ok:
            self.db.execute(f"ALTER TABLE {item.text()} RENAME TO {new}")
            item.setText(new)
            self.logger.log("Table renamed")

    def copy_cells(self):
        indexes = self.table_view.selectedIndexes()
        if not indexes:
            return
        rows = {}
        for idx in indexes:
            rows.setdefault(idx.row(), {})[idx.column()] = idx.data()
        text = "\n".join(
            "\t".join(row.get(c, "") for c in sorted(row))
            for row in sorted(rows)
            for row in [rows[row]]
        )
        QApplication.clipboard().setText(text)

    def paste_cells(self):
        self.logger.log("Paste requires manual cell editing", error=True)

    def import_csv(self):
        self.logger.log("CSV import requires mapping – explicit feature", error=True)

    def export_csv(self):
        if not self.model:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "*.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            headers = [h for h in self.model.headers if h != "rowid"]
            writer.writerow(headers)
            for r in self.model.rows:
                writer.writerow([r[h] for h in headers])
        self.logger.log("CSV exported")

    def export_excel(self):
        if not self.model:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "*.xlsx")
        if not path:
            return
        wb = Workbook()
        ws = wb.active
        headers = [h for h in self.model.headers if h != "rowid"]
        ws.append(headers)
        for r in self.model.rows:
            ws.append([r[h] for h in headers])
        wb.save(path)
        self.logger.log("Excel exported")

    def show_er(self):
        if self.db:
            ERDiagramWindow(self.db).exec()

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
