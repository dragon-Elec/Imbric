from PySide6.QtCore import QObject, Signal, Slot, Property
from core.services.search.worker import SearchWorker


class SearchBridge(QObject):
    searchResultsFound = Signal(list)
    searchFinished = Signal(int)
    searchError = Signal(str)

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        self._search_worker = SearchWorker(self)
        self._search_worker.setRegistry(main_window.registry)
        self._search_worker.resultsFound.connect(self.searchResultsFound)
        self._search_worker.searchFinished.connect(self.searchFinished)
        self._search_worker.searchError.connect(self.searchError)

    @Slot(str, str, bool)
    def startSearch(self, directory: str, pattern: str, recursive: bool = True):
        self._search_worker.start_search(directory, pattern, recursive)

    @Slot()
    def cancelSearch(self):
        self._search_worker.cancel()

    @Property(str, constant=True)
    def searchEngineName(self) -> str:
        return self._search_worker.engine_name
