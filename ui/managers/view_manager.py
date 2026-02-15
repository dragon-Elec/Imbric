"""
ViewManager — Global View Controller

Handles high-level view actions like Zoom and View Options.
Delegates active logic to the current Tab's RowBuilder.

Note: Layout logic is now handled by ui.managers.row_builder.RowBuilder.
"""

from PySide6.QtCore import QObject, Slot, Signal

class ViewManager(QObject):
    zoomChanged = Signal(int)
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

    @Slot()
    def zoom_in(self):
        if tab := self.mw.tab_manager.current_tab:
            tab.change_zoom(1)
            # Emit new height for status bar or other listeners
            self.zoomChanged.emit(tab.row_builder.getRowHeight())
        
    @Slot()
    def zoom_out(self):
        if tab := self.mw.tab_manager.current_tab:
            tab.change_zoom(-1)
            self.zoomChanged.emit(tab.row_builder.getRowHeight())

    @Slot()
    def reset_zoom(self):
        if tab := self.mw.tab_manager.current_tab:
            tab.row_builder.setRowHeight(tab.row_builder.DEFAULT_ROW_HEIGHT) # Default
            self.zoomChanged.emit(tab.row_builder.DEFAULT_ROW_HEIGHT)
        
    @Slot()
    def select_all(self):
        # Trigger QML selectAll
        if tab := self.mw.tab_manager.current_tab:
             tab.selectAllRequested.emit()

    @Slot()
    def toggle_hidden(self):
        if tab := self.mw.tab_manager.current_tab:
            current = tab.scanner.showHidden()
            tab.scanner.setShowHidden(not current)
            # Refresh to Apply
            tab.scan_current()
