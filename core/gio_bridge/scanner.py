import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from PySide6.QtCore import QObject, Signal, Slot

class FileScanner(QObject):
    """
    Scans a directory using Gio (Async) and emits found files.
    """
    filesFound = Signal(list) # Emits list[dict]
    scanFinished = Signal()
    scanError = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancellable = None

    @Slot(str)
    def scan_directory(self, path):
        """
        Starts an async scan of the given path.
        """
        # Cancel previous scan if running
        if self._cancellable:
            self._cancellable.cancel()
        
        self._cancellable = Gio.Cancellable()
        
        file = Gio.File.new_for_path(path)
        
        # Attributes we need: Name, Type (Directory/File), Hidden status, Mime Type
        attributes = "standard::name,standard::type,standard::is-hidden,standard::content-type"
        
        file.enumerate_children_async(
            attributes,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            self._cancellable,
            self._on_enumerate_finished
        )

    def _on_enumerate_finished(self, source_object, result):
        try:
            enumerator = source_object.enumerate_children_finish(result)
            # Store the parent directory path for reconstruction
            parent_path = source_object.get_path()
            self._fetch_next_batch(enumerator, parent_path)
        except Exception as e:
            self.scanError.emit(str(e))

    def _fetch_next_batch(self, enumerator, parent_path):
        """
        Recursively fetches batches of files from the enumerator.
        """
        enumerator.next_files_async(
            50, # Batch size
            GLib.PRIORITY_DEFAULT,
            self._cancellable,
            self._on_files_retrieved,
            (enumerator, parent_path) # Pass context tuple
        )

    def _on_files_retrieved(self, source_enumerator, result, context):
        enumerator, parent_path = context
        try:
            file_infos = source_enumerator.next_files_finish(result)
            
            if not file_infos:
                # No more files
                self.scanFinished.emit()
                source_enumerator.close(None)
                return

            batch = []
            for info in file_infos:
                # Filter for visible files only (basic check)
                if info.get_is_hidden():
                    continue
                
                # In future: Filter for Images/Videos based on mime-type
                # mime = info.get_content_type()
                
                name = info.get_name()
                
                # Construct FULL PATH using string concat (non-blocking)
                # Gio paths are clean strings; avoid os.path.join in async
                if parent_path.endswith('/'):
                    full_path = parent_path + name
                else:
                    full_path = parent_path + '/' + name
                
                is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
                
                # NOTE: We deliberately do NOT read image dimensions here.
                # QImageReader is synchronous and blocks the main thread.
                # For folders with 1000s of files, this causes multi-second UI freezes.
                # 
                # Instead, width/height are set to 0 and the QML delegate uses:
                # 1. A placeholder aspect ratio (1:1) initially
                # 2. The actual dimensions from the loaded thumbnail later
                #
                # This makes the scan near-instant at the cost of initial layout jumps.
                width = 0
                height = 0
                
                batch.append({
                    "name": name,
                    "path": full_path,
                    "isDir": is_dir,
                    "width": width,
                    "height": height
                    # "mime": mime
                })

            if batch:
                self.filesFound.emit(batch)
            
            # Continue fetching
            self._fetch_next_batch(enumerator, parent_path)

        except Exception as e:
            self.scanError.emit(str(e))
