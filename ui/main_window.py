"""Main window for CSV Generator 2.0 (PySide6).

Wires together:
 - the underlying eBayReportUploadGenerator business logic,
 - the SessionManager for save / resume / history,
 - the pandas-backed table model for the editable listings grid,
 - and the HistoryPanel dock widget.
"""

import os
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import eBayReportUploadGenerator
from session_manager import SessionManager
from ui.history_panel import HistoryPanel
from ui.listings_model import ListingsPandasModel


class PhotoUploadWorker(QThread):
    """Runs photo upload off the UI thread so SSH doesn't freeze the window."""

    finished_ok = Signal(str)
    finished_err = Signal(str)

    def __init__(self, generator, parent=None):
        super().__init__(parent)
        self.generator = generator

    def run(self):
        try:
            g = self.generator
            g.photoURLComplete = g.photoURLBeginning + g.card_set_short + ".jpg"
            if g.verify_photo_at_url(g.photoURLComplete):
                self.finished_ok.emit("Photo already exists at " + g.photoURLComplete)
                return
            if not g.verify_local_photo(g.full_local_jpg_location):
                self.finished_err.emit("No local photo found: " + g.full_local_jpg_location)
                return
            ok = g.upload_file(
                g.ssh_host,
                g.ssh_remote_file_path + g.card_set_short + ".jpg",
                g.ssh_username,
                g.ssh_password,
                g.full_local_jpg_location,
            )
            if ok and g.verify_photo_at_url(g.photoURLComplete):
                self.finished_ok.emit("Photo uploaded: " + g.photoURLComplete)
            else:
                self.finished_err.emit("Upload did not verify at " + g.photoURLComplete)
        except Exception as exc:  # noqa: BLE001 - surface any unexpected failure
            self.finished_err.emit(f"Upload error: {exc}")


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("eBay Report Upload Generator")
        self.resize(1200, 780)
        if os.path.isfile("ebay.ico"):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon("ebay.ico"))

        # Core dependencies
        self.generator = eBayReportUploadGenerator.eBayReportUploadGenerator()
        self.session_manager = SessionManager(self.generator.sessions_directory)
        self.current_session: Optional[dict] = None
        self._upload_worker: Optional[PhotoUploadWorker] = None
        self._dirty = False

        self._build_ui()
        self._build_toolbar()
        self._build_dock()

        # Prime the grid with whatever input.csv the generator loaded on startup
        if self.generator.inputDF is not None and not self.generator.inputDF.empty:
            self.listings_model.set_dataframe(self.generator.inputDF)
            self.input_path_label.setText(
                self.generator.working_directory + self.generator.input_filename
            )
            self._sync_metadata_to_form()
            self._set_status(
                f"Loaded {len(self.generator.inputDF.index)} rows from default input."
            )

        # Track edits so we can warn about unsaved changes
        self.listings_model.dataChanged.connect(self._mark_dirty)
        self.set_name_edit.textChanged.connect(self._mark_dirty)
        self.box_edit.textChanged.connect(self._mark_dirty)
        self.sport_combo.currentTextChanged.connect(self._mark_dirty)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # Central layout: splitter between metadata form (top) and grid (bottom)
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(12, 8, 12, 8)
        central_layout.setSpacing(8)

        # --- Metadata form ---
        form_box = QWidget(central)
        form_layout = QFormLayout(form_box)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(6)

        self.set_name_edit = QLineEdit(form_box)
        form_layout.addRow("Set Name:", self.set_name_edit)

        box_row = QWidget(form_box)
        box_row_layout = QHBoxLayout(box_row)
        box_row_layout.setContentsMargins(0, 0, 0, 0)
        box_row_layout.setSpacing(12)
        self.box_edit = QLineEdit(box_row)
        self.box_edit.setMaximumWidth(140)
        box_row_layout.addWidget(self.box_edit)
        box_row_layout.addWidget(QLabel("Sport:"))
        self.sport_combo = QComboBox(box_row)
        self.sport_combo.addItems(list(self.generator.sport_mapping.keys()))
        if self.generator.sport_long in self.generator.sport_mapping:
            self.sport_combo.setCurrentText(self.generator.sport_long)
        box_row_layout.addWidget(self.sport_combo, 1)
        form_layout.addRow("Box #:", box_row)

        image_row = QWidget(form_box)
        image_row_layout = QHBoxLayout(image_row)
        image_row_layout.setContentsMargins(0, 0, 0, 0)
        image_row_layout.setSpacing(8)
        self.image_button = QPushButton("Select Image…", image_row)
        self.image_button.clicked.connect(self.on_select_image)
        image_row_layout.addWidget(self.image_button)
        self.image_path_label = QLabel("(none)", image_row)
        self.image_path_label.setStyleSheet("color: #666;")
        image_row_layout.addWidget(self.image_path_label, 1)
        form_layout.addRow("Image:", image_row)

        input_row = QWidget(form_box)
        input_row_layout = QHBoxLayout(input_row)
        input_row_layout.setContentsMargins(0, 0, 0, 0)
        input_row_layout.setSpacing(8)
        self.input_button = QPushButton("Change…", input_row)
        self.input_button.clicked.connect(self.on_open_input)
        input_row_layout.addWidget(self.input_button)
        self.input_path_label = QLabel("(none)", input_row)
        self.input_path_label.setStyleSheet("color: #666;")
        input_row_layout.addWidget(self.input_path_label, 1)
        form_layout.addRow("Input CSV:", input_row)

        central_layout.addWidget(form_box)

        # --- Listings grid + status log inside a splitter ---
        splitter = QSplitter(Qt.Vertical, central)

        self.table = QTableView(splitter)
        self.listings_model = ListingsPandasModel(pd.DataFrame(), self)
        self.table.setModel(self.listings_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.table)

        self.log = QPlainTextEdit(splitter)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("Status messages will appear here…")
        splitter.addWidget(self.log)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)

        central_layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar(self))

    def _build_toolbar(self):
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(Qt.TopToolBarArea, tb)

        act_new = QAction("New", self)
        act_new.setShortcut(QKeySequence.New)
        act_new.triggered.connect(self.on_new_session)
        tb.addAction(act_new)

        act_open = QAction("Open Input…", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.on_open_input)
        tb.addAction(act_open)

        act_add_row = QAction("+ Row", self)
        act_add_row.triggered.connect(self.on_add_row)
        tb.addAction(act_add_row)

        act_del_row = QAction("− Row", self)
        act_del_row.triggered.connect(self.on_delete_row)
        tb.addAction(act_del_row)

        tb.addSeparator()

        act_save = QAction("Save Session", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self.on_save_session)
        tb.addAction(act_save)

        act_create = QAction("Create Files", self)
        act_create.triggered.connect(self.on_create_files)
        tb.addAction(act_create)

    def _build_dock(self):
        self.history_panel = HistoryPanel(self.session_manager, self)
        self.history_panel.session_activated.connect(self.on_load_session)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.history_panel)

    # ------------------------------------------------------------ helpers

    def _mark_dirty(self, *args):
        self._dirty = True

    def _sync_metadata_to_form(self):
        self.set_name_edit.setText(self.generator.card_set or "")
        self.box_edit.setText(self.generator.box_number or "")
        if self.generator.sport_long in self.generator.sport_mapping:
            self.sport_combo.setCurrentText(self.generator.sport_long)

    def _sync_form_to_generator(self):
        self.generator.card_set = self.set_name_edit.text().strip()
        self.generator.box_number = self.box_edit.text().strip()
        self.generator.sport_long = self.sport_combo.currentText()
        try:
            self.generator.card_year = self.generator.get_set_year(self.generator.card_set)
        except (AttributeError, TypeError):
            pass
        self.generator.sport_short = self.generator.get_sport_short(self.generator.sport_long)

    def _append_log(self, text: str):
        self.log.appendPlainText(text)

    def _set_status(self, text: str):
        self.statusBar().showMessage(text)
        self._append_log(text)

    # ------------------------------------------------------------ actions

    def on_new_session(self):
        if not self._confirm_discard():
            return
        self.current_session = None
        self.listings_model.set_dataframe(pd.DataFrame())
        self.set_name_edit.clear()
        self.box_edit.clear()
        self.image_path_label.setText("(none)")
        self.input_path_label.setText("(none)")
        self._dirty = False
        self._set_status("New session started. Open an input CSV to begin.")

    def on_open_input(self):
        start_dir = self.generator.working_directory
        path, _ = QFileDialog.getOpenFileName(
            self, "Select an input file", start_dir, "CSV Files (*.csv)"
        )
        if not path:
            return
        if not self.generator.initialize_input(path):
            QMessageBox.warning(self, "Load failed", f"Could not load {path}")
            return
        self.listings_model.set_dataframe(self.generator.inputDF)
        self.input_path_label.setText(path)
        self._sync_metadata_to_form()
        self._dirty = True
        self._set_status(f"Loaded {len(self.generator.inputDF.index)} rows from {path}")

    def on_select_image(self):
        start_dir = self.generator.local_jpg_location
        path, _ = QFileDialog.getOpenFileName(
            self, "Select an image", start_dir, "JPG Files (*.jpg)"
        )
        if not path:
            return
        self.generator.set_image(path)
        self.image_path_label.setText(path)
        self._dirty = True

    def on_add_row(self):
        row = self.listings_model.rowCount()
        selected = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if selected:
            row = selected[0].row() + 1
        self.listings_model.insertRows(row, 1)
        self._dirty = True

    def on_delete_row(self):
        if not self.table.selectionModel():
            return
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()}, reverse=True)
        for r in rows:
            self.listings_model.removeRows(r, 1)
        if rows:
            self._dirty = True

    def on_save_session(self):
        self._sync_form_to_generator()
        df = self.listings_model.dataframe()
        if df is None or df.empty:
            QMessageBox.information(self, "Nothing to save", "There are no listings to save.")
            return

        if self.current_session is None:
            self.current_session = self.session_manager.create_session(
                card_set=self.generator.card_set,
                card_set_short=self.generator.card_set_short,
                box=self.generator.box_number,
                sport=self.generator.sport_long,
                image_path=getattr(self.generator, 'full_local_jpg_location', ''),
                input_path=self.input_path_label.text() if self.input_path_label.text() != "(none)" else "",
            )
        else:
            # Refresh metadata fields from the form before saving
            self.current_session.update({
                'card_set': self.generator.card_set,
                'card_set_short': self.generator.card_set_short,
                'box': self.generator.box_number,
                'sport': self.generator.sport_long,
                'image_path': getattr(self.generator, 'full_local_jpg_location', ''),
            })

        self.current_session = self.session_manager.save_session(self.current_session, df)
        self.history_panel.refresh()
        self._dirty = False
        self._set_status(f"Session saved: {self.current_session['id']}")

    def on_load_session(self, session_id: str):
        if not self._confirm_discard():
            return
        meta = self.session_manager.load_session(session_id)
        self.current_session = meta
        listings = meta.get('listings')
        if listings is not None:
            self.listings_model.set_dataframe(listings)
        else:
            self.listings_model.set_dataframe(pd.DataFrame())

        # Restore metadata into the generator + form
        self.generator.card_set = meta.get('card_set', '') or ''
        self.generator.box_number = meta.get('box', '') or ''
        self.generator.sport_long = meta.get('sport', '') or self.generator.sport_long
        if self.generator.card_set:
            try:
                self.generator.card_year = self.generator.get_set_year(self.generator.card_set)
            except (AttributeError, TypeError):
                pass
        self.generator.card_set_short = meta.get('card_set_short', '') or ''
        image_path = meta.get('image_path', '') or ''
        if image_path:
            self.generator.full_local_jpg_location = image_path
            self.image_path_label.setText(image_path)
        else:
            self.image_path_label.setText("(none)")
        input_path = meta.get('input_path', '') or ''
        self.input_path_label.setText(input_path or "(none)")
        self._sync_metadata_to_form()
        self._dirty = False
        self._set_status(f"Loaded session {meta.get('id', '')}")

    def on_create_files(self):
        self._sync_form_to_generator()
        if not self.generator.card_set or not self.generator.box_number:
            QMessageBox.warning(self, "Missing fields", "Set Name and Box # are required.")
            return
        if not getattr(self.generator, 'card_set_short', ''):
            QMessageBox.warning(self, "Missing image", "Select an image first — the short name comes from its filename.")
            return

        # Resolve store category now that sport/year are set
        try:
            self.generator.storeCategory = self.generator.get_store_category(
                self.generator.sport_short, self.generator.card_year
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Category lookup failed", str(exc))
            return

        # Kick off photo upload on a background thread, then generate files on success.
        self._start_photo_upload(after=self._do_create_files)

    def _start_photo_upload(self, after):
        g = self.generator
        g.photoURLComplete = g.photoURLBeginning + g.card_set_short + ".jpg"
        # If already uploaded, skip the SSH dance entirely
        if g.verify_photo_at_url(g.photoURLComplete):
            self._append_log("Photo already exists at " + g.photoURLComplete)
            after()
            return
        if not g.verify_local_photo(getattr(g, 'full_local_jpg_location', '')):
            resp = QMessageBox.question(
                self, "No local photo",
                f"No photo found locally for {g.card_set_short}. Continue without uploading?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp == QMessageBox.Yes:
                after()
            return
        if not g.ssh_password:
            password, ok = QInputDialog.getText(
                self, "SSH Password", "Enter password:", QLineEdit.Password
            )
            if not ok:
                return
            g.ssh_password = password

        self._append_log("Uploading photo…")
        self._upload_worker = PhotoUploadWorker(g, self)

        def on_ok(msg):
            self._append_log(msg)
            after()

        def on_err(msg):
            self._append_log(msg)
            resp = QMessageBox.question(
                self, "Upload failed",
                f"{msg}\n\nProceed with file creation anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp == QMessageBox.Yes:
                after()

        self._upload_worker.finished_ok.connect(on_ok)
        self._upload_worker.finished_err.connect(on_err)
        self._upload_worker.start()

    def _do_create_files(self):
        df = self.listings_model.dataframe()
        if df is None or df.empty:
            QMessageBox.warning(self, "No listings", "The grid is empty.")
            return

        # If we have a current session, write outputs into that session's outputs/ dir.
        if self.current_session is not None:
            output_dir = self.session_manager.outputs_dir(self.current_session)
        else:
            output_dir = self.generator.working_directory

        try:
            ok = self.generator.create_files(input_df=df, output_directory=output_dir)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Create files failed", str(exc))
            return

        if ok:
            self._set_status(f"Output files written to {output_dir}")
            # Mark session as generated if we have one
            if self.current_session is not None:
                self.current_session = self.session_manager.save_session(
                    self.current_session, df, status='generated'
                )
                self.history_panel.refresh()
        else:
            self._set_status("create_files() returned False — see log for details.")

    # ------------------------------------------------------------ unsaved warning

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        resp = QMessageBox.question(
            self, "Unsaved changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.Yes | QMessageBox.No,
        )
        return resp == QMessageBox.Yes

    def closeEvent(self, event):  # noqa: N802 - Qt override
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
