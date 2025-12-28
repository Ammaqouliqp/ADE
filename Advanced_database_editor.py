from __future__ import annotations

import sys
import sqlite3
import csv
import json
import traceback
import shutil
from typing import List, Tuple, Optional, Union
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from openpyxl import Workbook

# =========================
# LOG MANAGER
# =========================
class LogManager:
    """
    Manages logging to a QTextEdit widget with colored messages.
    """
    def __init__(self, widget: QTextEdit):
        self.widget = widget

    def log(self, message: str, error: bool = False) -> None:
        """
        Logs a message with optional error coloring.
        
        :param message: The message to log.
        :param error: If True, log as error (red color).
        """
        color = "#ff6b6b" if error else "#6bff95"
        self.widget.append(f'<span style="color:{color}">{message}</span>')

    def log_exception(self, exc: Exception) -> None:
        """
        Logs an exception with traceback.
        
        :param exc: The exception to log.
        """
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.log(tb_str, error=True)

# =========================
# UNDO / REDO MANAGER
# =========================
class UndoRedoManager:
    """
    Manages undo/redo stacks for database operations.
    """
    def __init__(self, logger: LogManager):
        self.undo_stack: List = []
        self.redo_stack: List = []
        self.logger = logger

    def push(self, undo_sql: str, redo_sql: str, undo_params: tuple = (), redo_params: tuple = ()) -> None:
        """
        Pushes an operation to the undo stack.
        
        :param undo_sql: SQL to undo the operation.
        :param redo_sql: SQL to redo the operation.
        :param undo_params: Parameters for undo SQL.
        :param redo_params: Parameters for redo SQL.
        """
        self.undo_stack.append((undo_sql, redo_sql, undo_params, redo_params))
        self.redo_stack.clear()

    def undo(self, db: 'DatabaseManager') -> None:
        """
        Performs the top undo operation.
        
        :param db: The DatabaseManager instance.
        """
        if not self.undo_stack:
            self.logger.log("Nothing to undo", error=True)
            return
        undo_sql, redo_sql, undo_params, redo_params = self.undo_stack.pop()
        db.execute(undo_sql, undo_params)
        self.redo_stack.append((undo_sql, redo_sql, undo_params, redo_params))
        self.logger.log("Undo executed")

    def redo(self, db: 'DatabaseManager') -> None:
        """
        Performs the top redo operation.
        
        :param db: The DatabaseManager instance.
        """
        if not self.redo_stack:
            self.logger.log("Nothing to redo", error=True)
            return
        undo_sql, redo_sql, undo_params, redo_params = self.redo_stack.pop()
        db.execute(redo_sql, redo_params)
        self.undo_stack.append((undo_sql, redo_sql, undo_params, redo_params))
        self.logger.log("Redo executed")

# =========================
# DATABASE MANAGER
# =========================
class DatabaseManager:
    """
    Handles SQLite database connections and operations.
    """
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 5000")  # Handle locked DB

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Executes SQL with parameters and commits.
        
        :param sql: SQL query.
        :param params: Query parameters.
        :return: Cursor object.
        """
        try:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur
        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                raise RuntimeError("Database is locked; try again later.") from e
            raise

    def tables(self) -> List[str]:
        """
        Returns list of table names.
        """
        return [r[0] for r in self.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    def table_schema(self, table: str) -> List:
        """
        Returns schema info for a table.
        
        :param table: Table name.
        """
        return self.execute(f"PRAGMA table_info({table})").fetchall()

    def foreign_keys(self, table: str) -> List:
        """
        Returns foreign key info for a table.
        
        :param table: Table name.
        """
        return self.execute(f"PRAGMA foreign_key_list({table})").fetchall()

    def has_rowid(self, table: str) -> bool:
        """
        Checks if table has rowid.
        
        :param table: Table name.
        """
        try:
            self.execute(f"SELECT rowid FROM {table} LIMIT 1")
            return True
        except sqlite3.OperationalError:
            return False

    def read_table(self, table: str, has_rowid: bool, limit: int = 1000, offset: int = 0) -> Tuple[List, List]:
        """
        Reads table data with pagination.
        
        :param table: Table name.
        :param has_rowid: If table has rowid.
        :param limit: Row limit.
        :param offset: Row offset.
        :return: Headers and rows.
        """
        if has_rowid:
            sql = f"SELECT rowid, * FROM {table} LIMIT ? OFFSET ?"
        else:
            sql = f"SELECT * FROM {table} LIMIT ? OFFSET ?"
        cur = self.execute(sql, (limit, offset))
        rows = cur.fetchall()
        headers = [d[0] for d in cur.description]
        return headers, rows

# =========================
# SQLITE TABLE MODEL
# =========================
class SQLiteTableModel(QAbstractTableModel):
    """
    Table model for displaying and editing SQLite tables.
    """
    def __init__(self, db: DatabaseManager, table: str, logger: LogManager, undo_redo: UndoRedoManager):
        super().__init__()
        self.db = db
        self.table = table
        self.logger = logger
        self.undo_redo = undo_redo
        self.has_rowid = db.has_rowid(table)
        self.schema = {col[1]: col[2] for col in db.table_schema(table)}
        self.pk_columns = [col[1] for col in db.table_schema(table) if col[5]]
        if not self.has_rowid and not self.pk_columns:
            raise ValueError(f"Table '{table}' has no rowid or primary key; cannot edit safely")
        self.refresh()

    def refresh(self) -> None:
        """
        Refreshes model data.
        """
        self.beginResetModel()
        headers, rows = self.db.read_table(self.table, self.has_rowid)
        self.headers = headers
        self.rows = [dict(r) for r in rows]
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int) -> Optional[str]:
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = self.rows[index.row()][self.headers[index.column()]]
            return "<NULL>" if value is None else str(value)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        col = self.headers[index.column()]
        if (self.has_rowid and col == "rowid") or col in self.pk_columns:
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index: QModelIndex, value: str, role: int) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        col = self.headers[index.column()]
        if (self.has_rowid and col == "rowid") or col in self.pk_columns:
            return False
        row = self.rows[index.row()]
        id_columns = ['rowid'] if self.has_rowid else self.pk_columns
        id_values = tuple(row.get(c) for c in id_columns)
        old_value = row.get(col)
        col_type = self.schema.get(col, "").upper()
        if value.upper() == "<NULL>" or value.upper() == "NULL":
            value = None
        else:
            try:
                if "INTEGER" in col_type or "INT" in col_type:
                    value = int(value)
                elif "REAL" in col_type or "FLOAT" in col_type:
                    value = float(value)
                # Add more type validations as needed
            except ValueError:
                self.logger.log(f"Invalid value for {col_type}: {value}", error=True)
                return False
        if value == old_value:
            return False
        where_clause = " AND ".join(f"{c}=?" for c in id_columns)
        redo_sql = f"UPDATE {self.table} SET {col}=? WHERE {where_clause}"
        undo_sql = f"UPDATE {self.table} SET {col}=? WHERE {where_clause}"
        redo_params = (value,) + id_values
        undo_params = (old_value,) + id_values
        try:
            self.db.execute(redo_sql, redo_params)
            self.undo_redo.push(
                undo_sql, redo_sql,
                undo_params=undo_params,
                redo_params=redo_params
            )
            row[col] = value
            self.dataChanged.emit(index, index)
            self.logger.log(f"{self.table}.{col} updated")
            return True
        except Exception as e:
            self.logger.log_exception(e)
            return False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int) -> Optional[Union[str, int]]:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.headers[section] if orientation == Qt.Orientation.Horizontal else section + 1

# =========================
# ER DIAGRAM
# =========================
class ERDiagramWindow(QDialog):
    """
    Dialog for displaying ER diagram as text.
    """
    def __init__(self, db: DatabaseManager):
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
                view.append(f"  ↳ FK: {fk[3]} → {fk[2]}.{fk[4]}")
            view.append("")
        layout = QVBoxLayout(self)
        layout.addWidget(view)

# =========================
# MAIN WINDOW
# =========================
class MainWindow(QMainWindow):
    """
    Main application window for SQLite GUI Manager.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SQLite GUI Manager")
        self.resize(1400, 900)
        self.db: Optional[DatabaseManager] = None
        self.model: Optional[SQLiteTableModel] = None
        self.proxy_model: Optional[QSortFilterProxyModel] = None
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.logger = LogManager(self.log_view)
        self.undo_redo = UndoRedoManager(self.logger)
        self.table_list = QListWidget()
        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.textChanged.connect(self.filter_table)
        self.setup_ui()
        self.setup_menu()
        self.setup_docks()
        self.setup_shortcuts()
        self.setup_context_menus()
        sys.excepthook = self.log_exception

    def log_exception(self, exc_type, exc_value, exc_traceback) -> None:
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.logger.log(tb_str, error=True)

    def safe_run(self, func, *args, **kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception as e:
            self.logger.log_exception(e)

    # ---------------- UI ----------------
    def setup_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.table_list)
        h_layout.addWidget(self.table_view)
        layout.addWidget(self.search_bar)
        layout.addLayout(h_layout)
        self.setCentralWidget(central)
        self.table_list.setFixedWidth(250)
        self.setStyleSheet("""
            QListWidget, QTableView, QLineEdit {
                border-radius: 14px;
                background-color: #1e1e1e;
                color: #eee;
            }
            QTextEdit {
                background-color: #111;
            }
        """)
        self.table_list.itemClicked.connect(lambda item: self.safe_run(self.load_table, item))

    # ---------------- DOCKS ----------------
    def setup_docks(self) -> None:
        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        self.sql_dock = QDockWidget("SQL Console", self)
        self.sql_input = QTextEdit()
        btn = QPushButton("Execute")
        btn.clicked.connect(lambda: self.safe_run(self.exec_sql))
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(self.sql_input)
        l.addWidget(btn)
        self.sql_dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.sql_dock)

    # ---------------- MENU ----------------
    def setup_menu(self) -> None:
        mb = self.menuBar()
        file = mb.addMenu("File")
        file.addAction("Open DB", lambda: self.safe_run(self.open_db))
        export = mb.addMenu("Export")
        export.addAction(QAction("Table → CSV", self, triggered=lambda: self.safe_run(self.export_csv)))
        export.addAction(QAction("Table → Excel", self, triggered=lambda: self.safe_run(self.export_excel)))
        export.addAction(QAction("Table → SQL", self, triggered=lambda: self.safe_run(self.export_sql)))
        export.addAction(QAction("Table → JSON", self, triggered=lambda: self.safe_run(self.export_json)))
        export.addSeparator()
        export.addAction(QAction("Database Copy", self, triggered=lambda: self.safe_run(self.export_db_copy)))
        export.addAction(QAction("Database → SQL Dump", self, triggered=lambda: self.safe_run(self.export_db_sql)))

        edit = mb.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(lambda: self.safe_run(self.safe_undo))
        edit.addAction(undo_action)
        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(lambda: self.safe_run(lambda: self.undo_redo.redo(self.db)))
        edit.addAction(redo_action)

        view = mb.addMenu("View")
        view.addAction("ER Diagram", lambda: self.safe_run(self.show_er))
        tools = mb.addMenu("Tools")
        tools.addAction("Vacuum Database", lambda: self.safe_run(self.vacuum_db))

    # ---------------- SHORTCUTS ----------------
    def setup_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Copy, self, lambda: self.safe_run(self.copy_cells))
        QShortcut(QKeySequence.StandardKey.Paste, self, lambda: self.safe_run(self.paste_cells))

    # ---------------- CONTEXT MENUS ----------------
    def setup_context_menus(self) -> None:
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.table_context_menu)
        self.table_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_list.customContextMenuRequested.connect(self.table_list_context)

    # ---------------- TABLE LIST CONTEXT ----------------
    def table_list_context(self, pos: QPoint) -> None:
        menu = QMenu()
        menu.addAction("Add Table", lambda: self.safe_run(self.add_table))
        menu.addAction("Remove Table", lambda: self.safe_run(self.remove_table))
        menu.addAction("Rename Table", lambda: self.safe_run(self.rename_table))
        menu.exec(self.table_list.mapToGlobal(pos))

    # ---------------- TABLE VIEW CONTEXT ----------------
    def table_context_menu(self, pos: QPoint) -> None:
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
            self.safe_run(self.add_row)
        elif action == del_row:
            self.safe_run(self.delete_rows)
        elif action == add_col:
            self.safe_run(self.add_column)
        elif action == del_col:
            self.safe_run(self.delete_column)

    # ---------------- MAIN ACTIONS ----------------
    def open_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open SQLite DB", "", "*.db *.sqlite")
        if not path:
            return
        self.db = DatabaseManager(path)
        self.table_list.clear()
        self.table_list.addItems(self.db.tables())
        self.logger.log("Database opened")

    def load_table(self, item: QListWidgetItem) -> None:
        self.model = SQLiteTableModel(self.db, item.text(), self.logger, self.undo_redo)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table_view.setModel(self.proxy_model)

    def filter_table(self, text: str) -> None:
        if self.proxy_model:
            self.proxy_model.setFilterWildcard(text)

    def exec_sql(self) -> None:
        sql = self.sql_input.toPlainText()
        if not sql.strip():
            self.logger.log("SQL input is empty", error=True)
            return
        cur = self.db.execute(sql)
        rows = cur.fetchall()
        if rows:
            self.logger.log("\n".join(str(dict(r)) for r in rows))
        else:
            self.logger.log("SQL executed (no results)")
        if self.model:
            self.model.refresh()

    def safe_undo(self) -> None:
        if self.db:
            self.undo_redo.undo(self.db)
            if self.model:
                self.model.refresh()
        else:
            self.logger.log("No database loaded", error=True)

    def add_row(self) -> None:
        if not self.model:
            return
        try:
            self.db.execute(f"INSERT INTO {self.model.table} DEFAULT VALUES")
            # For undo, push delete, but need last_insert_rowid if has_rowid
            if self.model.has_rowid:
                rowid = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
                undo_sql = f"DELETE FROM {self.model.table} WHERE rowid=?"
                redo_sql = f"INSERT INTO {self.model.table} DEFAULT VALUES"  # Simplistic, loses specificity
                self.undo_redo.push(undo_sql, redo_sql, undo_params=(rowid,))
            self.model.refresh()
            self.logger.log("Row added")
        except Exception as e:
            self.logger.log_exception(e)

    def delete_rows(self) -> None:
        if not self.model:
            self.logger.log("No table loaded", error=True)
            return
        has_rowid = self.model.has_rowid
        pk_columns = self.model.pk_columns
        id_columns = ['rowid'] if has_rowid else pk_columns
        selected_rows = self.table_view.selectionModel().selectedRows()
        for idx in selected_rows:
            row = self.model.rows[idx.row()]
            params = tuple(row.get(c) for c in id_columns)
            where_clause = " AND ".join(f"{c}=?" for c in id_columns)
            # For undo, would need to push insert with data, but complex; skip for now
            self.db.execute(f"DELETE FROM {self.model.table} WHERE {where_clause}", params)
        self.model.refresh()
        self.logger.log("Rows deleted")

    def add_column(self) -> None:
        name, ok = QInputDialog.getText(self, "Column Name", "Name:")
        if not ok or not name.strip():
            return
        coltype, ok = QInputDialog.getText(self, "Column Type", "Type (TEXT, INTEGER, ...):")
        if ok and coltype.strip():
            self.db.execute(f"ALTER TABLE {self.model.table} ADD COLUMN {name} {coltype}")
            self.model.refresh()
            self.logger.log("Column added")

    def delete_column(self) -> None:
        # Workaround for DROP COLUMN
        col, ok = QInputDialog.getText(self, "Delete Column", "Column name:")
        if not ok or not col.strip():
            return
        try:
            columns = [c[1] for c in self.db.table_schema(self.model.table) if c[1] != col]
            if not columns:
                raise ValueError("Cannot delete last column")
            temp_table = f"{self.model.table}_temp"
            create_sql = f"CREATE TABLE {temp_table} ({', '.join([f'{c} {self.model.schema[c]}' for c in columns])})"
            self.db.execute(create_sql)
            insert_sql = f"INSERT INTO {temp_table} SELECT {', '.join(columns)} FROM {self.model.table}"
            self.db.execute(insert_sql)
            self.db.execute(f"DROP TABLE {self.model.table}")
            self.db.execute(f"ALTER TABLE {temp_table} RENAME TO {self.model.table}")
            self.model.refresh()
            self.logger.log("Column deleted")
        except Exception as e:
            self.logger.log_exception(e)

    def add_table(self) -> None:
        name, ok = QInputDialog.getText(self, "Table Name", "Name:")
        if ok and name.strip():
            self.db.execute(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY)")
            self.table_list.addItem(name)
            self.logger.log("Table created")

    def remove_table(self) -> None:
        item = self.table_list.currentItem()
        if item:
            self.db.execute(f"DROP TABLE {item.text()}")
            self.table_list.takeItem(self.table_list.currentRow())
            self.logger.log("Table removed")

    def rename_table(self) -> None:
        item = self.table_list.currentItem()
        if item:
            new_name, ok = QInputDialog.getText(self, "Rename Table", "New name:")
            if ok and new_name.strip():
                self.db.execute(f"ALTER TABLE {item.text()} RENAME TO {new_name}")
                item.setText(new_name)
                self.logger.log("Table renamed")

    def copy_cells(self) -> None:
        indexes = self.table_view.selectedIndexes()
        if not indexes:
            return
        rows = {}
        for idx in indexes:
            rows.setdefault(idx.row(), {})[idx.column()] = idx.data()
        text = "\n".join(
            "\t".join(rows[r].get(c, "") for c in sorted(rows[r]))
            for r in sorted(rows)
        )
        QApplication.clipboard().setText(text)

    def paste_cells(self) -> None:
        if not self.model:
            return
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        selection = self.table_view.selectionModel()
        if not selection.hasSelection():
            self.logger.log("Select cells to paste", error=True)
            return
        rows = text.split('\n')
        start_row = min(idx.row() for idx in selection.selectedIndexes())
        start_col = min(idx.column() for idx in selection.selectedIndexes())
        for r, row_text in enumerate(rows):
            cols = row_text.split('\t')
            for c, val in enumerate(cols):
                index = self.model.index(start_row + r, start_col + c)
                if index.isValid():
                    self.model.setData(index, val, Qt.ItemDataRole.EditRole)

    def vacuum_db(self) -> None:
        if self.db:
            self.db.execute("VACUUM")
            self.logger.log("Database vacuumed")
        else:
            self.logger.log("No database loaded", error=True)

    # ---------------- EXPORT FUNCTIONS ----------------
    def export_csv(self) -> None:
        if not self.model:
            self.logger.log("No table loaded", error=True)
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "*.csv")
            if not path:
                return
            headers = [h for h in self.model.headers if h != "rowid"]
            if not headers:
                raise ValueError("Table has no columns to export")
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in self.model.rows:
                    writer.writerow([r[h] if r[h] is not None else "" for h in headers])
            self.logger.log("CSV exported successfully")
        except Exception as e:
            self.logger.log_exception(e)

    def export_excel(self) -> None:
        if not self.model:
            self.logger.log("No table loaded", error=True)
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "*.xlsx")
            if not path:
                return
            wb = Workbook()
            ws = wb.active
            headers = [h for h in self.model.headers if h != "rowid"]
            if not headers:
                raise ValueError("Table has no columns to export")
            ws.append(headers)
            for r in self.model.rows:
                ws.append([r[h] if r[h] is not None else None for h in headers])
            wb.save(path)
            self.logger.log("Excel exported successfully")
        except Exception as e:
            self.logger.log_exception(e)

    def export_sql(self) -> None:
        if not self.model:
            self.logger.log("No table loaded", error=True)
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Export SQL", "", "*.sql")
            if not path:
                return
            table = self.model.table
            columns = [c for c in self.model.headers if c != "rowid"]
            if not columns:
                raise ValueError("Table has no columns to export")
            with open(path, "w", encoding="utf-8") as f:
                for row in self.model.rows:
                    vals = []
                    for c in columns:
                        val = row[c]
                        if val is None:
                            vals.append("NULL")
                        else:
                            vals.append("'" + str(val).replace("'", "''") + "'")
                    f.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(vals)});\n")
            self.logger.log("SQL exported successfully")
        except Exception as e:
            self.logger.log_exception(e)

    def export_json(self) -> None:
        if not self.model:
            self.logger.log("No table loaded", error=True)
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "", "*.json")
            if not path:
                return
            data = [{k: v for k, v in r.items() if k != "rowid"} for r in self.model.rows]
            if not data:
                raise ValueError("No data to export")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            self.logger.log("JSON exported successfully")
        except Exception as e:
            self.logger.log_exception(e)

    def export_db_copy(self) -> None:
        if not self.db:
            self.logger.log("No database loaded", error=True)
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Copy Database", "", "*.db")
            if not path:
                return
            shutil.copy(self.db.path, path)
            self.logger.log("Database copied successfully")
        except Exception as e:
            self.logger.log_exception(e)

    def export_db_sql(self) -> None:
        if not self.db:
            self.logger.log("No database loaded", error=True)
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Export SQL Dump", "", "*.sql")
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                for line in self.db.conn.iterdump():
                    f.write(f"{line}\n")
            self.logger.log("Database SQL dump exported successfully")
        except Exception as e:
            self.logger.log_exception(e)

    def show_er(self) -> None:
        if self.db:
            w = ERDiagramWindow(self.db)
            w.exec()
        else:
            self.logger.log("No database loaded", error=True)

# =========================
# START APP
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())