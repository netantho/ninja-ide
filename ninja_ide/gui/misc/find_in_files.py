# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import Queue

from PyQt4.QtCore import Qt
from PyQt4.QtCore import QDir
from PyQt4.QtCore import QFile
from PyQt4.QtCore import QString
from PyQt4.QtCore import QTextStream
from PyQt4.QtCore import QRegExp
from PyQt4.QtCore import QThread
from PyQt4.QtCore import SIGNAL

from PyQt4.QtGui import QVBoxLayout
from PyQt4.QtGui import QRadioButton
from PyQt4.QtGui import QHBoxLayout
from PyQt4.QtGui import QGridLayout
from PyQt4.QtGui import QGroupBox
from PyQt4.QtGui import QAbstractItemView
from PyQt4.QtGui import QHeaderView
from PyQt4.QtGui import QDialog
from PyQt4.QtGui import QWidget
from PyQt4.QtGui import QTreeWidget
from PyQt4.QtGui import QTreeWidgetItem
from PyQt4.QtGui import QLineEdit
from PyQt4.QtGui import QComboBox
from PyQt4.QtGui import QCheckBox
from PyQt4.QtGui import QPushButton
from PyQt4.QtGui import QLabel
from PyQt4.QtGui import QIcon
from PyQt4.QtGui import QFileDialog

from ninja_ide import resources
from ninja_ide.core import file_manager
from ninja_ide.gui.main_panel import main_container
from ninja_ide.gui.explorer import explorer_container


class FindInFilesThread(QThread):
    '''
    Emit the signal
    found_pattern(PyQt_PyObject)
    '''

    def find_in_files(self, dir_name, filters, reg_exp, recursive, by_phrase):
        self._cancel = False
        self.recursive = recursive
        self.search_pattern = reg_exp
        self.by_phrase = by_phrase
        self.filters = filters
        self.queue = Queue.Queue()
        self.queue.put(dir_name)
        self.root_dir = dir_name
        #Start!
        self.start()

    def run(self):
        file_filter = QDir.Files | QDir.NoDotAndDotDot | QDir.Readable
        dir_filter = QDir.Dirs | QDir.NoDotAndDotDot | QDir.Readable
        while not self._cancel and not self.queue.empty():
            current_dir = QDir(self.queue.get())
            #Skip not readable dirs!
            if not current_dir.isReadable():
                continue

            #Collect all sub dirs!
            if self.recursive:
                current_sub_dirs = current_dir.entryInfoList(dir_filter)
                for one_dir in current_sub_dirs:
                    self.queue.put(one_dir.absoluteFilePath())

            #all files in sub_dir first apply the filters
            current_files = current_dir.entryInfoList(
                self.filters, file_filter)
            #process all files in current dir!
            for one_file in current_files:
                self._grep_file(one_file.absoluteFilePath(),
                    one_file.fileName())

    def _grep_file(self, file_path, file_name):
        if not self.by_phrase:
            with open(file_path, 'r') as f:
                content = f.read()
            words = [word for word in \
                unicode(self.search_pattern.pattern()).split('|')]
            words.insert(0, True)

            def check_whole_words(result, word):
                return result and content.find(word) != -1
            if not reduce(check_whole_words, words):
                return
        file_object = QFile(file_path)
        if not file_object.open(QFile.ReadOnly):
            return

        stream = QTextStream(file_object)
        lines = []
        line_index = 0
        line = stream.readLine()
        while not self._cancel:
            column = self.search_pattern.indexIn(line)
            if column != -1:
                lines.append((line_index, line))
            #take the next line!
            line = stream.readLine()
            if line.isNull():
                break
            line_index += 1
        #emit a signal!
        relative_file_name = file_manager.convert_to_relative(
            unicode(self.root_dir), unicode(file_path))
        self.emit(SIGNAL("found_pattern(PyQt_PyObject)"),
            (relative_file_name, lines))

    def cancel(self):
        self._cancel = True


class FindInFilesResult(QTreeWidget):

    def __init__(self):
        QTreeWidget.__init__(self)
        self.setHeaderLabels((self.tr('File'), self.tr('Line')))
        self.header().setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.header().setResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setResizeMode(1, QHeaderView.ResizeToContents)
        self.header().setStretchLastSection(False)
        self.sortByColumn(0, Qt.AscendingOrder)

    def update_result(self, dir_name_root, file_name, items):
        if items:
            root_item = FindInFilesRootItem(self, (file_name, ''),
                dir_name_root)
            root_item.setExpanded(True)
            for line, content in items:
                QTreeWidgetItem(root_item, (content, QString.number(line + 1)))


class FindInFilesRootItem(QTreeWidgetItem):

    def __init__(self, parent, names, dir_name_root):
        QTreeWidgetItem.__init__(self, parent, names)
        self.dir_name_root = dir_name_root


class FindInFilesDialog(QDialog):

    def __init__(self, result_widget):
        QDialog.__init__(self)
        self._find_thread = FindInFilesThread()
        self.setWindowTitle("Find in files")
        self.resize(400, 300)
        #MAIN LAYOUT
        main_vbox = QVBoxLayout(self)

        self.pattern_line_edit = QLineEdit()
        self.dir_name_root = None
        self.user_home = os.path.expanduser('~')
        self.dir_combo = QComboBox()
        self.dir_combo.addItem(self.user_home)
        self.dir_combo.setEditable(True)
        self.open_button = QPushButton(QIcon(resources.IMAGES['find']),
            self.tr("Open"))
        self.filters_line_edit = QLineEdit("*.py")
        self.case_checkbox = QCheckBox(self.tr("C&ase sensitive"))
        self.type_checkbox = QCheckBox(self.tr("R&egular Expression"))
        self.recursive_checkbox = QCheckBox(self.tr("Rec&ursive"))
        self.recursive_checkbox.setCheckState(Qt.Checked)
        self.phrase_radio = QRadioButton(
            self.tr("Search by Phrase (Exact Match)."))
        self.phrase_radio.setChecked(True)
        self.words_radio = QRadioButton(
            self.tr("Search for all the words "
                    "(anywhere in the document, not together)."))
        self.find_button = QPushButton(self.tr("Find!"))
        self.find_button.setMaximumWidth(150)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.cancel_button.setMaximumWidth(150)
        self.result_widget = result_widget

        hbox = QHBoxLayout()
        hbox.addWidget(self.find_button)
        hbox.addWidget(self.cancel_button)

        #main section
        find_group_box = QGroupBox(self.tr("Main"))
        grid = QGridLayout()
        grid.addWidget(QLabel(self.tr("Text: ")), 0, 0)
        grid.addWidget(self.pattern_line_edit, 0, 1)
        grid.addWidget(QLabel(self.tr("Directory: ")), 1, 0)
        grid.addWidget(self.dir_combo, 1, 1)
        grid.addWidget(self.open_button, 1, 2)
        grid.addWidget(QLabel(self.tr("Filter: ")), 2, 0)
        grid.addWidget(self.filters_line_edit, 2, 1)

        find_group_box.setLayout(grid)
        #add main section to MAIN LAYOUT
        main_vbox.addWidget(find_group_box)

        #options sections
        options_group_box = QGroupBox(self.tr("Options"))
        gridOptions = QGridLayout()
        gridOptions.addWidget(self.case_checkbox, 0, 0)
        gridOptions.addWidget(self.type_checkbox, 1, 0)
        gridOptions.addWidget(self.recursive_checkbox, 2, 0)
        gridOptions.addWidget(self.phrase_radio, 0, 1)
        gridOptions.addWidget(self.words_radio, 1, 1)

        options_group_box.setLayout(gridOptions)
        #add options sections to MAIN LAYOUT
        main_vbox.addWidget(options_group_box)

        #add buttons to MAIN LAYOUT
        main_vbox.addLayout(hbox)

        #Focus
        self.pattern_line_edit.setFocus()
        self.open_button.setFocusPolicy(Qt.NoFocus)

        #signal
        self.connect(self.open_button, SIGNAL("clicked()"), self._select_dir)
        self.connect(self.find_button, SIGNAL("clicked()"),
            self._find_in_files)
        self.connect(self.cancel_button, SIGNAL("clicked()"),
            self._kill_thread)
        self.connect(self._find_thread, SIGNAL("found_pattern(PyQt_PyObject)"),
            self._found_match)
        self.connect(self._find_thread, SIGNAL("finished()"),
            self._find_thread_finished)
        self.connect(self.type_checkbox, SIGNAL("stateChanged(int)"),
            self._change_radio_enabled)

    def _change_radio_enabled(self, val):
        enabled = not self.type_checkbox.isChecked()
        self.phrase_radio.setEnabled(enabled)
        self.words_radio.setEnabled(enabled)

    def show(self, actual_project=None, actual=None):
        self.dir_combo.clear()
        self.dir_name_root = actual_project if \
            actual_project else [self.user_home]
        self.dir_combo.addItems(self.dir_name_root)
        if actual:
            index = self.dir_combo.findText(actual)
            self.dir_combo.setCurrentIndex(index)
        super(FindInFilesDialog, self).show()
        self.pattern_line_edit.setFocus()

    def reject(self):
        self._kill_thread()
        self.result_widget.parent().parent().parent().hide()
        super(FindInFilesDialog, self).reject()

    def _find_thread_finished(self):
        self.emit(SIGNAL("finished()"))

    def _select_dir(self):
        dir_name = QFileDialog.getExistingDirectory(self,
            self.tr("Open Directory"),
            self.dir_combo.currentText(),
            QFileDialog.ShowDirsOnly)
        index = self.dir_combo.findText(dir_name)
        if index >= 0:
            self.dir_combo.setCurrentIndex(index)
        else:
            self.dir_combo.insertItem(0, dir_name)
            self.dir_combo.setCurrentIndex(0)

    def _found_match(self, result):
        file_name = result[0]
        items = result[1]
        self.result_widget.update_result(
            self.dir_combo.currentText(), file_name, items)

    def _kill_thread(self):
        if self._find_thread.isRunning():
            self._find_thread.cancel()
        self.accept()

    def _find_in_files(self):
        self._kill_thread()
        self.result_widget.clear()
        pattern = self.pattern_line_edit.text()
        dir_name = self.dir_combo.currentText()
        filters = self.filters_line_edit.text().split(QRegExp("[,;]"),
            QString.SkipEmptyParts)
        #remove the spaces in the words Ex. (" *.foo"--> "*.foo")
        filters = [f.simplified() for f in filters]
        case_sensitive = self.case_checkbox.isChecked()
        type_ = QRegExp.RegExp if \
            self.type_checkbox.isChecked() else QRegExp.FixedString
        recursive = self.recursive_checkbox.isChecked()
        by_phrase = True
        if self.phrase_radio.isChecked() or self.type_checkbox.isChecked():
            regExp = QRegExp(pattern, case_sensitive, type_)
        elif self.words_radio.isChecked():
            by_phrase = False
            type_ = QRegExp.RegExp
            pattern = '|'.join(
                [word.strip() for word in unicode(pattern).split()])
            regExp = QRegExp(pattern, case_sensitive, type_)
        #save a reference to the root directory where we find
        self.dir_name_root = dir_name
        self._find_thread.find_in_files(dir_name, filters, regExp, recursive,
            by_phrase)


class FindInFilesWidget(QWidget):

    def __init__(self, parent):
        QWidget.__init__(self, parent)
        self._main_container = main_container.MainContainer()
        self._explorer_container = explorer_container.ExplorerContainer()
        self._result_widget = FindInFilesResult()
        self._open_find_button = QPushButton(self.tr("Find!"))
        self._stop_button = QPushButton(self.tr("Stop"))
        self._clear_button = QPushButton(self.tr("Clear!"))
        self._find_widget = FindInFilesDialog(self._result_widget)
        self._error_label = QLabel(self.tr("No Results"))
        self._error_label.setVisible(False)
        #Main Layout
        main_hbox = QHBoxLayout(self)
        #Result Layout
        tree_vbox = QVBoxLayout()
        tree_vbox.addWidget(self._result_widget)
        tree_vbox.addWidget(self._error_label)

        main_hbox.addLayout(tree_vbox)
        #Buttons Layout
        vbox = QVBoxLayout()
        vbox.addWidget(self._open_find_button)
        vbox.addWidget(self._stop_button)
        vbox.addWidget(self._clear_button)
        main_hbox.addLayout(vbox)

        self._open_find_button.setFocus()
        #signals
        self.connect(self._open_find_button, SIGNAL("clicked()"),
            self.open)
        self.connect(self._stop_button, SIGNAL("clicked()"), self._find_stop)
        self.connect(self._clear_button, SIGNAL("clicked()"),
            self._clear_results)
        self.connect(self._result_widget, SIGNAL(
            "itemClicked(QTreeWidgetItem *, int)"), self._go_to)
        self.connect(self._find_widget, SIGNAL("finished()"),
            self._find_finished)

    def _find_finished(self):
        self._error_label.setVisible(False)
        if not self._result_widget.topLevelItemCount():
            self._error_label.setVisible(True)

    def _find_stop(self):
        self._find_widget._kill_thread()

    def _clear_results(self):
        self._result_widget.clear()

    def _go_to(self, item, val):
        if item.text(1):
            parent = item.parent()
            file_name = str(parent.text(0))
            lineno = item.text(1)
            root_dir_name = str(parent.dir_name_root)
            file_path = file_manager.create_path(root_dir_name, file_name)
            #open the file and jump_to_line
            self._main_container.open_file(str(file_path))
            self._main_container.editor_jump_to_line(lineno=int(lineno) - 1)

    def open(self):
        if not self._find_widget.isVisible():
            actual_projects_obj = self._explorer_container.get_opened_projects()
            actual_projects = [p.path for p in actual_projects_obj]
            actual = self._explorer_container.get_actual_project()
            self._find_widget.show(actual_project=actual_projects,
                actual=actual)

    def find_occurrences(self, word):
        self._find_widget.pattern_line_edit.setText(word)
        editorWidget = main_container.MainContainer().get_actual_editor()
        explorerContainer = explorer_container.ExplorerContainer()
        projects_obj = explorerContainer.get_opened_projects()
        projects = [p.path for p in projects_obj]
        project = explorerContainer.get_actual_project()
        for p in projects:
            if file_manager.belongs_to_folder(p, editorWidget.ID):
                project = p
                break
        self._find_widget.dir_combo.clear()
        self._find_widget.dir_combo.addItem(project)
        self._find_widget._find_in_files()
