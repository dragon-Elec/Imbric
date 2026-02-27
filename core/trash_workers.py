"""
[NEW] Trash Workers
Contains Trash-specific operations (Send, Restore, List, Empty).
"""

from dataclasses import dataclass
from typing import List

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from core.file_workers import FileOperationRunnable, FileJob, FileOperationSignals, build_conflict_payload, _make_gfile, _gfile_path
from core.metadata_utils import get_file_info

@dataclass
class TrashItem:
    """Represents an item in the trash."""
    trash_name: str          # Internal name in trash (e.g., "file.2.txt")
    display_name: str        # Original filename (e.g., "file.txt")
    original_path: str       # Where it came from (e.g., "/home/user/file.txt")
    deletion_date: str       # ISO format date string
    trash_uri: str           # Full URI (e.g., "trash:///file.2.txt")
    size: int = 0
    is_dir: bool = False

class SendToTrashRunnable(FileOperationRunnable):
    """Moves a file to the trash."""
    
    def run(self):
        self.emit_started()
        path = self.job.source
        gfile = _make_gfile(path)
        
        try:
            gfile.trash(self.job.cancellable)
            self.emit_finished(True, path)
            
        except GLib.Error as e:
            if e.code in (Gio.IOErrorEnum.NOT_SUPPORTED, Gio.IOErrorEnum.PERMISSION_DENIED):
                self.signals.trashNotSupported.emit(path, str(e))
            self._handle_gio_error(e, "trash", path)

class RestoreFromTrashRunnable(FileOperationRunnable):
    """Restores a file from trash to its original location."""
    
    def run(self):
        self.emit_started()
        original_path = self.job.source
        
        try:
            # _do_restore returns cached metadata for conflict enrichment
            self._cached_trash_meta = {}
            self._do_restore(original_path)
            
            # Determine final path (might be renamed)
            final_path = original_path
            if self.job.rename_to:
                parent_gfile = _make_gfile(original_path).get_parent()
                final_path = _gfile_path(parent_gfile.get_child(self.job.rename_to))
                
            self.emit_finished(True, final_path)
            
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.EXISTS:
                # Use cached metadata from the enumeration we already did
                extra_src_data = self._cached_trash_meta
                
                final_dest_path = original_path
                if self.job.rename_to:
                    parent_gfile = _make_gfile(original_path).get_parent()
                    final_dest_path = _gfile_path(parent_gfile.get_child(self.job.rename_to))
                    
                conflict_data = build_conflict_payload(
                    src_path=self.job.source,
                    dest_path=final_dest_path,
                    extra_src_data=extra_src_data
                )
                self._handle_gio_error(e, "restore", original_path, conflict_data)
            else:
                self._handle_gio_error(e, "restore", original_path)
                
        except Exception as e:
            msg = str(e)
            self.signals.operationError.emit(self.job.transaction_id, self.job.id, "restore", original_path, msg, None)
            self.emit_finished(False, msg)
    
    def _do_restore(self, original_path: str):
        trash_root = Gio.File.new_for_uri("trash:///")
        enumerator = trash_root.enumerate_children(
            "standard::name,trash::orig-path,trash::deletion-date",
            Gio.FileQueryInfoFlags.NONE,
            self.job.cancellable
        )
        
        candidate = None
        candidate_date = ""
        
        try:
            while True:
                try:
                    info = enumerator.next_file(self.job.cancellable)
                except GLib.Error as e:
                    print(f"[TrashWorker] Warning: Error reading trash entry, skipping: {e}")
                    continue
                if not info:
                    break
                
                orig_path = info.get_attribute_byte_string("trash::orig-path")
                if orig_path:
                    if isinstance(orig_path, bytes):
                        orig_path = orig_path.decode('utf-8', errors='ignore')
                    
                    if orig_path == original_path:
                        date = info.get_attribute_string("trash::deletion-date") or ""
                        if candidate is None or date > candidate_date:
                            candidate = info
                            candidate_date = date
        finally:
            enumerator.close(self.job.cancellable)
        
        # Cache metadata for conflict enrichment (avoids double enumeration)
        if candidate_date:
            self._cached_trash_meta = {"deletion_date": candidate_date}
        
        if candidate:
            trash_name = candidate.get_name()
            trash_file = trash_root.get_child(trash_name)
            
            dest_file = Gio.File.new_for_path(original_path)
            
            if self.job.rename_to:
                parent = dest_file.get_parent()
                dest_file = parent.get_child(self.job.rename_to)
            
            parent = dest_file.get_parent()
            if parent:
                try:
                    parent.make_directory_with_parents(self.job.cancellable)
                except GLib.Error as e:
                    if e.code != Gio.IOErrorEnum.EXISTS:
                        raise e
            
            flags = Gio.FileCopyFlags.NONE
            if self.job.overwrite:
                flags |= Gio.FileCopyFlags.OVERWRITE

            trash_file.move(dest_file, flags, self.job.cancellable, None, None)
        else:
            raise Exception(f"File not found in trash: {original_path}")


class ListTrashRunnable(FileOperationRunnable):
    """Lists all items in the trash."""
    
    def run(self):
        self.emit_started()
        try:
            items = self._list_trash()
            for item in items:
                self.signals.itemListed.emit(item)
            self.emit_finished(True, str(len(items)))
        except Exception as e:
            self.emit_finished(False, str(e))
    
    def _list_trash(self) -> List[TrashItem]:
        trash_root = Gio.File.new_for_uri("trash:///")
        items = []
        
        enumerator = trash_root.enumerate_children(
            "standard::name,standard::display-name,standard::size,standard::type,"
            "trash::orig-path,trash::deletion-date",
            Gio.FileQueryInfoFlags.NONE,
            self.job.cancellable
        )
        
        while True:
            try:
                info = enumerator.next_file(self.job.cancellable)
            except GLib.Error as e:
                print(f"[TrashWorker] Warning: Error reading trash entry, skipping: {e}")
                continue
            if not info:
                break
            
            trash_name = info.get_name()
            display_name = info.get_display_name()
            size = info.get_size()
            is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
            
            orig_path = info.get_attribute_byte_string("trash::orig-path") or ""
            if isinstance(orig_path, bytes):
                orig_path = orig_path.decode('utf-8', errors='ignore')
            
            date = info.get_attribute_string("trash::deletion-date") or ""
            
            items.append(TrashItem(
                trash_name=trash_name,
                display_name=display_name,
                original_path=orig_path,
                deletion_date=date,
                trash_uri=f"trash:///{trash_name}",
                size=size,
                is_dir=is_dir
            ))
        
        enumerator.close(self.job.cancellable)
        items.sort(key=lambda x: x.deletion_date, reverse=True)
        return items

class EmptyTrashRunnable(FileOperationRunnable):
    """Permanently deletes all items in the trash."""
    
    def run(self):
        self.emit_started()
        try:
            deleted_count = self._empty_trash()
            self.emit_finished(True, str(deleted_count))
        except GLib.Error as e:
            if e.code != Gio.IOErrorEnum.CANCELLED:
                self.signals.operationError.emit(self.job.transaction_id, self.job.id, "empty", "Trash", str(e), None)
            self.emit_finished(False, str(e))
        except Exception as e:
            msg = str(e)
            self.signals.operationError.emit(self.job.transaction_id, self.job.id, "empty", "Trash", msg, None)
            self.emit_finished(False, msg)
    
    def _empty_trash(self) -> int:
        trash_root = Gio.File.new_for_uri("trash:///")
        deleted = 0
        
        enumerator = trash_root.enumerate_children(
            "standard::name",
            Gio.FileQueryInfoFlags.NONE,
            self.job.cancellable
        )
        
        while True:
            if self.job.cancellable.is_cancelled():
                break
            info = enumerator.next_file(self.job.cancellable)
            if not info:
                break
            
            trash_name = info.get_name()
            trash_file = trash_root.get_child(trash_name)
            
            try:
                trash_file.delete(self.job.cancellable)
                deleted += 1
                self.signals.progress.emit(self.job.id, deleted, -1)
            except GLib.Error as e:
                if e.code == Gio.IOErrorEnum.NOT_EMPTY:
                    self._delete_recursive(trash_file)
                    deleted += 1
        
        enumerator.close(self.job.cancellable)
        return deleted
    
    def _delete_recursive(self, gfile: Gio.File):
        enumerator = gfile.enumerate_children(
            "standard::name,standard::type",
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            self.job.cancellable
        )
        while True:
            info = enumerator.next_file(self.job.cancellable)
            if not info:
                break
            child = gfile.get_child(info.get_name())
            if info.get_file_type() == Gio.FileType.DIRECTORY:
                self._delete_recursive(child)
            else:
                try:
                    child.delete(self.job.cancellable)
                except GLib.Error as e:
                    print(f"[TrashWorker] Warning: Could not delete {child.get_path()}: {e}")
        enumerator.close(self.job.cancellable)
        gfile.delete(self.job.cancellable)
