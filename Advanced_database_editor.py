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

    def info(self, msg):
        self.widget.append(f"<span style='color:#6bff95'>{msg}</span>")

    def error(self, msg):
        self.widget.append(f"<span style='color:#ff6b6b'>{msg}</span>")


# =========================
# DATABASE MANAGER
# =========================
class DatabaseManager:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        with self.conn:
            return self.conn.execute(sql, params)

    def tables(self):
        return [
            r[0] for r in self.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]

    def table_schema(self, table):
        return self.execute(f"PRAGMA table_info({table})").fetchall()

    def primary_key(self, table):
        for col in self.table_schema(table):
            if col["pk"] == 1:
                return col["name"]
        return None

    def read_table(self, table):
        cur = self.execute(f"SELECT * FROM {table}")
        return [d[0] for d in cur.description], [dict(r) for r in cur.fetchall()]


# =========================
# UNDO / REDO MANAGER
# =========================
class UndoRedoManager:
    def __init__(self, logger: LogManager):
        self.undo = []
        self.redo = []
        self.logger = logger

    def push(self, undo_sql, undo_params, redo_sql, redo_params):
        self.undo.append((undo_sql, undo_params, redo_sql, redo_params))
        self.redo.clear()

    def undo_action(self, db):
        if not self.undo:
            self.logger.error("Nothing to undo")
            return
        u_sql, u_p, r_sql, r_p = self.undo.pop()
        db.execute(u_sql, u_p)
        self.redo.append((u_sql, u_p, r_sql, r_p))
        self.logger.info("Undo executed")

    def redo_action(self, db):
        if not self.redo:
            self.logger.error("Nothing to redo")
            return
        u_sql, u_p, r_sql, r_p = self.redo.pop()
        db.execute(r_sql, r_p)
        self.undo.append((u_sql, u_p, r_sql, r_p))
        self.logger.info("Redo executed")


# =========================
# TABLE MODEL
# =========================
class SQLiteTableModel(QAbstractTableModel):
    def __init__(self, db, table, logger, undo_redo):
        super().__init__()
        self.db = db
        self.table = table
        self.logger = logger
        self.undo_redo = undo_redo
        self.pk = db.primary_key(table)
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self.headers, self.rows = self.db.read_table(self.table)
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
        col = self.headers[index.column()]
        if col == self.pk:
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role):
        if role != Qt.ItemDataRole.EditRole or not self.pk:
            return False

        col = self.headers[index.column()]
        if col == self.pk:
            return False

        row = self.rows[index.row()]
        pk_val = row[self.pk]
        old = row[col]

        if str(value) == str(old):
            return False

        redo_sql = f"UPDATE {self.table} SET {col}=? WHERE {self.pk}=?"
        undo_sql = f"UPDATE {self.table} SET {col}=? WHERE {self.pk}=?"

        self.db.execute(redo_sql, (value, pk_val))
        self.undo_redo.push(
            undo_sql, (old, pk_val),
            redo_sql, (value, pk_val)
        )

        row[col] = value
        self.dataChanged.emit(index, index)
        self.logger.info(f"{self.table}.{col} updated")
        return True

    def headerData(self, section, orientation, role):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.headers[section] if orientation == Qt.Orientation.Horizontal else section + 1


# =========================
# MAIN WINDOW
# =========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced SQLite Database Editor")
        self.resize(1400, 900)

        self.db = None
        self.model = None

        self.log_view = QTextEdit(readOnly=True)
        self.logger = LogManager(self.log_view)
        self.undo_redo = UndoRedoManager(self.logger)

        self.table_list = QListWidget()
        self.table_view = QTableView()

        self.setup_ui()
        self.setup_menu()
        self.setup_docks()

    def setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        self.table_list.setFixedWidth(260)
        layout.addWidget(self.table_list)
        layout.addWidget(self.table_view)
        self.setCentralWidget(central)

        self.table_list.itemClicked.connect(self.load_table)

    def setup_docks(self):
        dock = QDockWidget("Log")
        dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def setup_menu(self):
        mb = self.menuBar()

        file = mb.addMenu("File")
        file.addAction("Open DB", self.open_db)

        edit = mb.addMenu("Edit")
        edit.addAction("Undo", lambda: self.undo_redo.undo_action(self.db))
        edit.addAction("Redo", lambda: self.undo_redo.redo_action(self.db))

        table = mb.addMenu("Table")
        table.addAction("Add Row", self.add_row)
        table.addAction("Delete Row", self.delete_rows)

    def open_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SQLite DB", "", "*.db *.sqlite")
        if not path:
            return
        self.db = DatabaseManager(path)
        self.table_list.clear()
        self.table_list.addItems(self.db.tables())
        self.logger.info("Database opened")

    def load_table(self, item):
        self.model = SQLiteTableModel(self.db, item.text(), self.logger, self.undo_redo)
        self.table_view.setModel(self.model)

    def add_row(self):
        if not self.model:
            return
        self.db.execute(f"INSERT INTO {self.model.table} DEFAULT VALUES")
        self.model.refresh()
        self.logger.info("Row added")

    def delete_rows(self):
        if not self.model or not self.model.pk:
            self.logger.error("Table has no PRIMARY KEY; deletion blocked")
            return

        selected = {i.row() for i in self.table_view.selectionModel().selectedRows()}
        for r in selected:
            pk_val = self.model.rows[r][self.model.pk]
            self.db.execute(
                f"DELETE FROM {self.model.table} WHERE {self.model.pk}=?",
                (pk_val,)
            )

        self.model.refresh()
        self.logger.info("Rows deleted")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
