"""
GIO Volumes Bridge - Volume monitoring and management.
Moved from core/gio_bridge/volumes.py
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
from PySide6.QtCore import QObject, Signal, Slot, Property
from core.threading.worker_pool import AsyncWorkerPool


def _fetch_usage_task(path: str) -> dict | None:
    """Synchronous usage query to be run in background."""
    if not path:
        return None
    try:
        f = Gio.File.new_for_commandline_arg(path)
        info = f.query_filesystem_info(
            f"{Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE},{Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE}",
            None,
        )
        size = info.get_attribute_uint64(Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE)
        free = info.get_attribute_uint64(Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
        if size > 0:
            return {"total": size, "free": free, "used": size - free}
    except Exception as e:
        pass
    return None


class VolumesBridge(QObject):
    """Wraps Gio.VolumeMonitor with async usage updates via AsyncWorkerPool."""

    volumesChanged = Signal()
    mountSuccess = Signal(str)
    mountError = Signal(str)
    unmountSuccess = Signal(str)

    @Property(str, constant=True)
    def title(self):
        return "Devices"

    @Property(str, constant=True)
    def icon(self):
        return "hard_drive"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.monitor = Gio.VolumeMonitor.get()
        self._usage_cache = {}
        self._pending_usage = set()
        self._cached_volumes = []
        self._is_rebuilding = False

        self._pool = AsyncWorkerPool(max_concurrent=3, parent=self)
        self._pool.resultReady.connect(self._on_worker_result)

        for sig in [
            "mount-added",
            "mount-removed",
            "volume-added",
            "volume-removed",
            "drive-connected",
            "drive-disconnected",
        ]:
            self.monitor.connect(sig, lambda *a: self._rebuild_cache_async())

        self._rebuild_cache_async()

    def _on_worker_result(self, task_id, result):
        if task_id == "volumes_rebuild":
            self._cached_volumes = result
            self._is_rebuilding = False
            self.volumesChanged.emit()
        else:
            path = task_id
            self._pending_usage.discard(path)
            if result:
                self._usage_cache[path] = result
                self.volumesChanged.emit()

    def _rebuild_cache_async(self):
        if self._is_rebuilding:
            return
        self._is_rebuilding = True
        self._pool.enqueue("volumes_rebuild", self._build_volume_list_task, priority=20)

    @staticmethod
    def _build_volume_list_task():
        items = []
        seen_uuids, seen_paths = set(), set()
        monitor = Gio.VolumeMonitor.get()
        mounts = {m.get_uuid(): m for m in monitor.get_mounts() if m.get_uuid()}

        def get_icon_name(gicon):
            if not gicon:
                return "drive-harddisk"
            if isinstance(gicon, Gio.ThemedIcon):
                names = gicon.get_names()
                return names[0] if names else gicon.to_string()
            return gicon.to_string()

        for vol in monitor.get_volumes():
            uuid = vol.get_uuid() or vol.get_identifier("unix-device")
            if not uuid or uuid in seen_uuids:
                continue
            seen_uuids.add(uuid)

            mount = vol.get_mount() or mounts.get(uuid)
            is_mounted = mount is not None
            path = mount.get_root().get_parse_name() if is_mounted else ""
            if path:
                seen_paths.add(path)

            items.append(
                {
                    "identifier": uuid,
                    "name": vol.get_name(),
                    "path": path,
                    "icon": "root" if path == "/" else get_icon_name(vol.get_icon()),
                    "isMounted": is_mounted,
                    "canMount": vol.can_mount(),
                    "canUnmount": mount.can_unmount() if is_mounted else False,
                    "type": "volume",
                }
            )

        for mount in monitor.get_mounts():
            root = mount.get_root()
            path = root.get_parse_name()
            uuid = mount.get_uuid() or root.get_uri()
            if uuid in seen_uuids or path in seen_paths:
                continue

            items.append(
                {
                    "identifier": uuid,
                    "name": mount.get_name(),
                    "path": path,
                    "icon": get_icon_name(mount.get_icon()),
                    "isMounted": True,
                    "canMount": False,
                    "canUnmount": mount.can_unmount(),
                    "type": "mount",
                }
            )
        return items

    def _get_usage(self, path):
        if not path:
            return None
        if path in self._usage_cache:
            return self._usage_cache[path]

        if path not in self._pending_usage:
            self._pending_usage.add(path)
            self._pool.enqueue(path, _fetch_usage_task, priority=100, path=path)
        return None

    @Slot(result=list)
    def get_volumes(self):
        for item in self._cached_volumes:
            if item["isMounted"]:
                usage = self._get_usage(item["path"])
                if usage:
                    item["usage"] = usage
                elif "usage" not in item:
                    item["usage"] = None
        return self._cached_volumes

    @Slot(str)
    def mount_volume(self, identifier):
        vol = next(
            (v for v in self.monitor.get_volumes() if v.get_uuid() == identifier), None
        )
        if not vol:
            return self.mountError.emit(f"Volume {identifier} not found")
        vol.mount(
            Gio.MountMountFlags.NONE,
            Gio.MountOperation(),
            None,
            self._on_mount_finished,
            identifier,
        )

    def _on_mount_finished(self, obj, res, ident):
        try:
            obj.mount_finish(res)
            self.mountSuccess.emit(ident)
            self.volumesChanged.emit()
        except GLib.Error as e:
            self.mountError.emit(e.message)

    @Slot(str)
    def unmount_volume(self, identifier):
        mount = next(
            (
                v.get_mount()
                for v in self.monitor.get_volumes()
                if v.get_uuid() == identifier
            ),
            None,
        )
        if not mount:
            mount = next(
                (
                    m
                    for m in self.monitor.get_mounts()
                    if m.get_uuid() == identifier or m.get_name() == identifier
                ),
                None,
            )

        if not mount:
            return self.mountError.emit(f"Mount for {identifier} not found")
        mount.unmount_with_operation(
            Gio.MountUnmountFlags.NONE,
            Gio.MountOperation(),
            None,
            self._on_unmount_finished,
            identifier,
        )

    def _on_unmount_finished(self, obj, res, ident):
        try:
            obj.unmount_with_operation_finish(res)
            self.unmountSuccess.emit(ident)
            self.volumesChanged.emit()
        except GLib.Error as e:
            self.mountError.emit(e.message)
