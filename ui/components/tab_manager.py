from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QUrl, Slot, Signal, Property, QTimer, QObject
from PySide6.QtQuick import QQuickView
from pathlib import Path
import os

from ui.models.tab_model import TabListModel, TabController

class TabManager(QWidget):
    """
    Manages the browser tabs using a single QML engine and a model-based approach.
    Replaces the old QTabWidget implementation.
    """
    
    # Signals for Main Window integration
    currentPathChanged = Signal(str)
    currentIndexChanged = Signal(int)
    
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        
        # 1. Data Model
        self._model = TabListModel(main_window, self)
        # Start at -1 so that the transition to 0 (first tab) triggers a change signal
        self._current_index = -1
        
        # 2. QML Engine Setup
        self.qml_view = QQuickView()
        self.qml_view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        self.qml_view.setColor(Qt.GlobalColor.transparent)
        
        # 3. Context Properties
        ctx = self.qml_view.engine().rootContext()
        ctx.setContextProperty("tabManager", self)
        ctx.setContextProperty("tabModel", self._model)
        
        # 4. Image Providers (Registered ONCE for the single engine)
        from core.image_providers.thumbnail_provider import ThumbnailProvider
        from core.image_providers.theme_provider import ThemeImageProvider
        
        self._thumbnail_provider = ThumbnailProvider()
        self._theme_provider = ThemeImageProvider()
        
        self.qml_view.engine().addImageProvider("thumbnail", self._thumbnail_provider)
        self.qml_view.engine().addImageProvider("theme", self._theme_provider)
        
        # 5. Import Paths
        qml_dir = Path(__file__).parent.parent / "qml"
        self.qml_view.engine().addImportPath(str(qml_dir))
        
        # 6. Load Source
        # We load TabContainer.qml which contains the TabBar and StackLayout
        qml_path = qml_dir / "views" / "TabContainer.qml"
        self.qml_view.setSource(QUrl.fromLocalFile(str(qml_path)))
        
        # 7. Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.container = QWidget.createWindowContainer(self.qml_view, self)
        self.container.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        layout.addWidget(self.container)
        
        # 8. Signal Connections
        # When current tab changes, we need to notify MW
        self.currentIndexChanged.connect(self._on_current_changed)

    # --- QML Properties ---

    @Property(int, notify=currentIndexChanged)
    def currentIndex(self):
        return self._current_index

    @currentIndex.setter
    def currentIndex(self, val):
        if self._current_index != val:
            self._current_index = val
            self.currentIndexChanged.emit(val)

    # --- Public API (Compatible with old TabManager) ---

    @Slot(str, result=QObject)
    def add_tab(self, path: str | None = None) -> TabController:
        """Adds a new tab and selects it."""
        tab = self._model.add_tab(path)
        
        # Select the new tab
        new_index = self._model.rowCount() - 1
        self.currentIndex = new_index
        
        return tab

    @Slot(int)
    def close_tab(self, index: int):
        """Closes the tab at index."""
        if self._model.rowCount() <= 1:
            return # Keep one tab
            
        self._model.remove_tab(index)
        
        # Adjust selection if needed
        if self._current_index >= self._model.rowCount():
            self.currentIndex = self._model.rowCount() - 1

    @Slot()
    def next_tab(self):
        count = self._model.rowCount()
        if count > 1:
            self.currentIndex = (self.currentIndex + 1) % count

    @Slot()
    def prev_tab(self):
        count = self._model.rowCount()
        if count > 1:
            self.currentIndex = (self.currentIndex - 1) % count

    @Slot()
    def close_current_tab(self):
        self.close_tab(self.currentIndex)

    def navigate_to(self, path: str):
        if tab := self.current_tab:
            tab.navigate_to(path)

    @property
    def current_tab(self) -> TabController | None:
        """Returns the currently active TabController."""
        return self._model.get_tab(self.currentIndex)
    
    @Slot()
    def go_back(self):
        if tab := self.current_tab:
            tab.go_back()
    
    @Slot()
    def go_forward(self):
        if tab := self.current_tab:
            tab.go_forward()
            
    @Slot()
    def go_home(self):
        if tab := self.current_tab:
            tab.go_home()

    def _on_current_changed(self, index):
        """Handle side effects of tab switching."""
        if tab := self.current_tab:
            self.currentPathChanged.emit(tab.current_path)
            # Re-connect path changed signal from this tab to our signal
            # Actually, TabListModel handles internal updates, we just need to forward the current one
            try:
                tab.pathChanged.disconnect(self.currentPathChanged)
            except: pass
            tab.pathChanged.connect(self.currentPathChanged)

