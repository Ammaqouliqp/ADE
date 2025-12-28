import sys
import sqlite3
import csv
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from openpyxl import Workbook
import json
import traceback

# =========================
# LOG MANAGER
# =========================
class LogManager:
    def __init__(self, widget):
        self.widget = widget

    def log(self, message: str, error=False):
        color = "#ff6b6b" if error else "#6bff95"
        self.widget.append(f'<span style="color:{color}">{message}</span>')

    def log_exception(self, exc: Exception):
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.log(tb_str, error=True)


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
# TABLE MODEL
# =========================
class SQLiteTableModel(QAbstractTableModel):
    def __init__(self, db, table, logger):
        super().__init__()
        self.db = db
        self.table = table
        self.logger = logger
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
        old_val = row[col]

        if str(value) == str(old_val):
            return False

        sql = f"UPDATE {self.table} SET {col}=? WHERE {self.pk}=?"
        self.db.execute(sql, (value, pk_val))
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

        self.table_list = QListWidget()
        self.table_view = QTableView()

        self.setup_ui()
        self.create_actions()
        self.setup_menus()
        self.setup_context_menus()
        self.setup_docks()

    # ---------- UI ----------
    def setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        self.table_list.setFixedWidth(260)
        layout.addWidget(self.table_list)
        layout.addWidget(self.table_view)
        self.setCentralWidget(central)

        self.table_list.itemClicked.connect(self.load_table)

    # ---------- ACTIONS ----------
    def create_actions(self):
        self.act_add_row = QAction("Add Row", self, triggered=self.add_row)
        self.act_delete_rows = QAction("Delete Selected Rows", self, triggered=self.delete_rows)
        self.act_add_column = QAction("Add Column", self, triggered=self.add_column)
        self.act_delete_column = QAction("Delete Column", self, triggered=self.delete_column)
        self.act_rename_table = QAction("Rename Table", self, triggered=self.rename_table)
        self.act_drop_table = QAction("Drop Table", self, triggered=self.drop_table)
        # Export actions
        self.act_export_csv = QAction("Export Table → CSV", self, triggered=self.export_csv)
        self.act_export_excel = QAction("Export Table → Excel", self, triggered=self.export_excel)
        self.act_export_sql = QAction("Export Table → SQL", self, triggered=self.export_sql)
        self.act_export_json = QAction("Export Table → JSON", self, triggered=self.export_json)

        self.act_export_db_copy = QAction("Export Database Copy", self, triggered=self.export_db_copy)
        self.act_export_db_sql = QAction("Export Database → SQL Dump", self, triggered=self.export_db_sql)

    def update_action_states(self):
        has_model = self.model is not None
        has_pk = has_model and self.model.pk is not None

        sel_model = self.table_view.selectionModel()
        has_selection = sel_model is not None and len(sel_model.selectedRows()) > 0

        self.act_add_row.setEnabled(has_model)
        self.act_delete_rows.setEnabled(has_pk and has_selection)
        self.act_add_column.setEnabled(has_model)
        self.act_delete_column.setEnabled(False)
        self.act_rename_table.setEnabled(has_model)
        self.act_drop_table.setEnabled(has_model)

    # ---------- MENUS ----------
    def setup_menus(self):
        mb = self.menuBar()

        file = mb.addMenu("File")
        file.addAction("Open DB", self.open_db)

        table = mb.addMenu("Table")
        table.addAction(self.act_add_row)
        table.addAction(self.act_delete_rows)
        table.addSeparator()
        table.addAction(self.act_add_column)
        table.addAction(self.act_delete_column)


        export = mb.addMenu("Export")
        export.addAction(self.act_export_csv)
        export.addAction(self.act_export_excel)
        export.addAction(self.act_export_sql)
        export.addAction(self.act_export_json)

        export.addSeparator()

        export.addAction(self.act_export_db_copy)
        export.addAction(self.act_export_db_sql)



    # ---------- CONTEXT MENUS ----------
    def setup_context_menus(self):
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.table_context_menu)

        self.table_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_list.customContextMenuRequested.connect(self.table_list_context_menu)

    def table_context_menu(self, pos):
        if not self.model:
            return
        self.update_action_states()
        menu = QMenu(self)
        menu.addAction(self.act_add_row)
        menu.addAction(self.act_delete_rows)
        menu.addSeparator()
        menu.addAction(self.act_add_column)
        menu.addAction(self.act_delete_column)
        menu.exec(self.table_view.viewport().mapToGlobal(pos))
        self.act_export_csv.setEnabled(has_model)
        self.act_export_excel.setEnabled(has_model)
        self.act_export_sql.setEnabled(has_model)
        self.act_export_json.setEnabled(has_model)

        self.act_export_db_copy.setEnabled(self.db is not None)
        self.act_export_db_sql.setEnabled(self.db is not None)

    def table_list_context_menu(self, pos):
        item = self.table_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.addAction(self.act_rename_table)
        menu.addAction(self.act_drop_table)
        menu.exec(self.table_list.mapToGlobal(pos))

    # ---------- DOCKS ----------
    def setup_docks(self):
        dock = QDockWidget("Log", self)
        dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    # ---------- DB ACTIONS ----------
    def open_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SQLite DB", "", "*.db *.sqlite")
        if not path:
            return
        self.db = DatabaseManager(path)
        self.table_list.clear()
        self.table_list.addItems(self.db.tables())
        self.logger.info("Database opened")

    def load_table(self, item):
        self.model = SQLiteTableModel(self.db, item.text(), self.logger)
        self.table_view.setModel(self.model)
        self.table_view.selectionModel().selectionChanged.connect(
            lambda *_: self.update_action_states()
        )
        self.update_action_states()

    def add_row(self):
        self.db.execute(f"INSERT INTO {self.model.table} DEFAULT VALUES")
        self.model.refresh()
        self.logger.info("Row added")

    def delete_rows(self):
        if not self.model.pk:
            self.logger.error("Deletion blocked: no PRIMARY KEY")
            return

        rows = {i.row() for i in self.table_view.selectionModel().selectedRows()}
        for r in rows:
            pk_val = self.model.rows[r][self.model.pk]
            self.db.execute(
                f"DELETE FROM {self.model.table} WHERE {self.model.pk}=?",
                (pk_val,)
            )

        self.model.refresh()
        self.logger.info("Rows deleted")

    def add_column(self):
        name, ok = QInputDialog.getText(self, "Add Column", "Column name:")
        if not ok or not name:
            return
        ctype, ok = QInputDialog.getText(self, "Add Column", "Column type (TEXT, INTEGER, ...):")
        if not ok or not ctype:
            return
        self.db.execute(f"ALTER TABLE {self.model.table} ADD COLUMN {name} {ctype}")
        self.model.refresh()
        self.logger.info("Column added")

    def delete_column(self):
        QMessageBox.information(
            self,
            "Not Supported",
            "SQLite does not support DROP COLUMN safely.\nThis action is disabled."
        )

    def rename_table(self):
        item = self.table_list.currentItem()
        if not item:
            return
        new, ok = QInputDialog.getText(self, "Rename Table", "New name:")
        if ok and new:
            self.db.execute(f"ALTER TABLE {item.text()} RENAME TO {new}")
            item.setText(new)
            self.logger.info("Table renamed")

    def drop_table(self):
        item = self.table_list.currentItem()
        if not item:
            return
        if QMessageBox.question(
            self,
            "Confirm",
            f"Drop table '{item.text()}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.db.execute(f"DROP TABLE {item.text()}")
            self.table_list.takeItem(self.table_list.row(item))
            self.logger.info("Table dropped")
    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.model.headers)
            writer.writeheader()
            writer.writerows(self.model.rows)

        self.logger.info("Table exported to CSV")

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "Excel (*.xlsx)")
        if not path:
            return

        wb = Workbook()
        ws = wb.active
        ws.append(self.model.headers)

        for row in self.model.rows:
            ws.append([row[h] for h in self.model.headers])

        wb.save(path)
        self.logger.info("Table exported to Excel")

    def export_sql(self):
        if not self.model:
            self.logger.log("No table loaded", error=True)
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export SQL", "", "SQL Files (*.sql)"
        )
        if not path:
            return

        table = self.model.table

        # Exclude rowid
        columns = [c for c in self.model.headers if c != "rowid"]

        def esc_ident(name: str) -> str:
            return f'"{name.replace(chr(34), chr(34)*2)}"'

        with open(path, "w", encoding="utf-8") as f:
            f.write("BEGIN TRANSACTION;\n")

            col_list = ", ".join(esc_ident(c) for c in columns)

            for row in self.model.rows:
                values = []
                for c in columns:
                    val = row.get(c)
                    if val is None:
                        values.append("NULL")
                    elif isinstance(val, (int, float)):
                        values.append(str(val))
                    else:
                        escaped = str(val).replace("'", "''")
                        values.append(f"'{escaped}'")

                values_sql = ", ".join(values)

                f.write(
                    f"INSERT INTO {esc_ident(table)} ({col_list}) "
                    f"VALUES ({values_sql});\n"
                )

            f.write("COMMIT;\n")

        self.logger.log("Table exported to SQL")




    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "", "JSON (*.json)")
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model.rows, f, ensure_ascii=False, indent=2)

        self.logger.info("Table exported to JSON")

    def export_db_copy(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Database Copy", "", "SQLite (*.db)")
        if not path:
            return

        dest = sqlite3.connect(path)
        self.db.conn.backup(dest)
        dest.close()

        self.logger.info("Database copied successfully")

    def export_db_sql(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export SQL Dump", "", "SQL (*.sql)")
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            for line in self.db.conn.iterdump():
                f.write(f"{line}\n")

        self.logger.info("Database exported as SQL dump")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
