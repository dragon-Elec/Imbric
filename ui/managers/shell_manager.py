from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QUrl, Slot, Signal, Property, QTimer, QObject
from PySide6.QtQuick import QQuickView
from pathlib import Path


from ui.models.tab_model import TabListModel
from ui.models.tab_controller import TabController
from ui.models.sidebar_model import SidebarModel
from core.gio_bridge.desktop import QuickAccessBridge
from core.gio_bridge.volumes import VolumesBridge

class ShellManager(QWidget):
    """
    Manages the unified QML Shell (Sidebar + Tabs).
    Replaces TabManager and SidebarWidget.
    """
    
    # Signals for Main Window integration
    currentPathChanged = Signal(str)
    currentIndexChanged = Signal(int)
    
    # Shell Actions signals
    navigationRequested = Signal(str)
    
    @Property(QObject, constant=True)
    def quickAccess(self):
        return self.quick_access

    @Property(QObject, constant=True)
    def volumes(self):
        return self.volumes_bridge # Renaming self.volumes to self.volumes_bridge to avoid name clash with property

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        
        # 1. Initialize Bridges
        self.quick_access = QuickAccessBridge(self)
        self.volumes_bridge = VolumesBridge(self)
        
        # Internal State for UI persistence
        self._section_states = {
            "Quick Access": False,
            "Devices": False,
            "Network": True
        }
        
        # 2. Data Model (Tabs)
        self._model = TabListModel(main_window, self)
        self._current_index = -1
        
        # 3. QML Engine Setup
        self.qml_view = QQuickView()
        self.qml_view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        self.qml_view.setColor(Qt.GlobalColor.transparent)
        
        # 4. Context Properties
        ctx = self.qml_view.engine().rootContext()
        ctx.setContextProperty("shellManager", self) # Self-reference
        ctx.setContextProperty("tabManager", self)   # Alias for compatibility
        ctx.setContextProperty("tabModel", self._model)
        
        # Instantiate and bind SidebarModel
        self.sidebar_model = SidebarModel(self)
        ctx.setContextProperty("sidebarModel", self.sidebar_model)
        
        # 5. Image Providers
        from core.image_providers.thumbnail_provider import ThumbnailProvider
        from core.image_providers.theme_provider import ThemeImageProvider
        
        self._thumbnail_provider = ThumbnailProvider()
        self._theme_provider = ThemeImageProvider()
        
        self.qml_view.engine().addImageProvider("thumbnail", self._thumbnail_provider)
        self.qml_view.engine().addImageProvider("theme", self._theme_provider)
        
        # 6. Import Paths
        qml_dir = Path(__file__).parent.parent / "qml"
        self.qml_view.engine().addImportPath(str(qml_dir))
        
        # 7. Load Source (The Unified Layout)
        qml_path = qml_dir / "views" / "MainLayout.qml"
        self.qml_view.setSource(QUrl.fromLocalFile(str(qml_path)))
        
        # 8. Connect Shell Logic (Bridges -> QML)
        self.quick_access.itemsChanged.connect(self._rebuild_sidebar_model)
        self.volumes_bridge.volumesChanged.connect(self._rebuild_sidebar_model)
        
        if self.qml_view.rootObject():
            root = self.qml_view.rootObject()
            
            # Connect QML Signals -> Python Slots
            root.navigationRequested.connect(self._on_navigation_requested)
            root.mountRequested.connect(self.volumes_bridge.mount_volume)
            root.unmountRequested.connect(self.volumes_bridge.unmount_volume)
            # Handle section collapse toggles if you add a signal for it, 
            # or we can rely on local state if we don't need persistence across restarts.
            # For now, we rebuild model using self._section_states.
            
            # If MainLayout emits a signal for section toggling (optional improvement):
            if hasattr(root, "sectionToggled"):
                root.sectionToggled.connect(self._on_section_toggled)
        
        # Initial Load
        self._rebuild_sidebar_model()
        
        # 9. Layout (Widget Wrapper)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.container = QWidget.createWindowContainer(self.qml_view, self)
        self.container.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        layout.addWidget(self.container)
        
        # 10. Signal Connections
        self.currentIndexChanged.connect(self._on_current_changed)

    # --- QML Data Sync ---
    
    def _rebuild_sidebar_model(self):
        """Updates the inner models of the SidebarModel."""
        # 1. Quick Access Section
        qa_items = self.quick_access.get_items()
        self.sidebar_model.update_section_items("Quick Access", qa_items)
        
        # 2. Volumes Section
        vol_items = self.volumes_bridge.get_volumes()
        self.sidebar_model.update_section_items("Devices", vol_items)

    @Slot(str, bool)
    def _on_section_toggled(self, title, is_collapsed):
        """Update internal state when user toggles a section."""
        self._section_states[title] = is_collapsed
        self.sidebar_model.set_section_collapsed(title, is_collapsed)

    @Slot(str)
    def _on_navigation_requested(self, path):
        # Forward to main window handler or handle directly?
        # Let's handle it by navigating the CURRENT tab
        if self.current_tab:
            self.navigate_to(path)
        else:
            # If no tabs, open one?
            self.add_tab(path)

    # --- TabManager Logic (Copied/Adapted) ---

    @Property(int, notify=currentIndexChanged)
    def currentIndex(self):
        return self._current_index

    @currentIndex.setter
    def currentIndex(self, val):
        if self._current_index != val:
            self._current_index = val
            self.currentIndexChanged.emit(val)

    @Slot(str, result=QObject)
    def add_tab(self, path: str | None = None) -> TabController:
        tab = self._model.add_tab(path)
        new_index = self._model.rowCount() - 1
        self.currentIndex = new_index
        return tab

    @Slot(int)
    def close_tab(self, index: int):
        if self._model.rowCount() <= 1: return
        self._model.remove_tab(index)
        if self._current_index >= self._model.rowCount():
            self.currentIndex = self._model.rowCount() - 1

    @Slot()
    def next_tab(self):
        count = self._model.rowCount()
        if count > 1: self.currentIndex = (self.currentIndex + 1) % count

    @Slot()
    def prev_tab(self):
        count = self._model.rowCount()
        if count > 1: self.currentIndex = (self.currentIndex - 1) % count
        
    @Slot()
    def close_current_tab(self):
        self.close_tab(self.currentIndex)

    def navigate_to(self, path: str):
        if tab := self.current_tab:
            tab.navigate_to(path)

    @property
    def current_tab(self) -> TabController | None:
        return self._model.get_tab(self.currentIndex)
    
    @Slot()
    def go_back(self):
        if tab := self.current_tab: tab.go_back()
    
    @Slot()
    def go_forward(self):
        if tab := self.current_tab: tab.go_forward()
            
    @Slot()
    def go_home(self):
        if tab := self.current_tab: tab.go_home()

    def _on_current_changed(self, index):
        # 0. Disconnect previous connection if any
        if hasattr(self, '_connected_tab') and self._connected_tab:
            try: self._connected_tab.pathChanged.disconnect(self.currentPathChanged)
            except: pass
            self._connected_tab = None

        if tab := self.current_tab:
            # 1. Emit current path immediately
            self.currentPathChanged.emit(tab.current_path)
            
            # 2. Connect new tab
            tab.pathChanged.connect(self.currentPathChanged)
            self._connected_tab = tab
            
            # Also sync sidebar selection to this tab
            # (Handled in QML via Connections { target: tabManager ... })
