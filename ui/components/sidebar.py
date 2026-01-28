from PySide6.QtWidgets import QTreeView, QFileSystemModel
from PySide6.QtCore import QDir, Signal, QModelIndex

class Sidebar(QTreeView):
    """
    Sidebar Navigation Tree.
    Wraps QTreeView + QFileSystemModel.
    """
    
    navigationRequested = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarTree")
        self._setup_model()
        self._setup_view()
        
    def _setup_model(self):
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.rootPath())
        self.fs_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs)
        self.setModel(self.fs_model)
        self.setRootIndex(self.fs_model.index(QDir.homePath()))
        
    def _setup_view(self):
        self.setHeaderHidden(True)
        # Hide Size, Type, Date columns (keep only Name)
        for i in range(1, 4):
            self.hideColumn(i)
            
        self.clicked.connect(self._on_clicked)
        
    def sync_to_path(self, path: str):
        """Expand tree to show and select the given path."""
        index = self.fs_model.index(path)
        if index.isValid():
            self.setCurrentIndex(index)
            self.scrollTo(index)
            
    def _on_clicked(self, index: QModelIndex):
        path = self.fs_model.filePath(index)
        self.navigationRequested.emit(path)
