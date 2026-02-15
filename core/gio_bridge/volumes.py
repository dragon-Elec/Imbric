"""
[DONE] VolumesBridge — Async Volume Management

Wraps Gio.VolumeMonitor to provide a reactive list of drives and volumes.
Supports async mounting and unmounting via Gio.

Features:
- Reactive updates via `volumesChanged` signal (plug/unplug/mount/unmount)
- Unified list of Volumes (physical partitions) and Mounts (network/other)
- Async `mount_volume` and `unmount_volume` with error handling
- Rich metadata (UUID, icons, mount state)
"""

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from PySide6.QtCore import QObject, Signal, Slot

class VolumesBridge(QObject):
    """
    Wraps Gio.VolumeMonitor to list connected drives and volumes.
    Provides reactive signals and async mount/unmount operations.
    """
    
    volumesChanged = Signal()
    mountSuccess = Signal(str) # identifier
    mountError = Signal(str)   # error message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.monitor = Gio.VolumeMonitor.get()
        
        # Connect signals to monitor global state changes
        # We debounce these or just emit directly since UI will refresh the model
        self.monitor.connect("mount-added", self._on_monitor_changed)
        self.monitor.connect("mount-removed", self._on_monitor_changed)
        self.monitor.connect("volume-added", self._on_monitor_changed)
        self.monitor.connect("volume-removed", self._on_monitor_changed)
        self.monitor.connect("drive-connected", self._on_monitor_changed)
        self.monitor.connect("drive-disconnected", self._on_monitor_changed)
        
    def _on_monitor_changed(self, monitor, item):
        """Pass-through signal when anything changes in Gioland."""
        self.volumesChanged.emit()

    def _get_icon_name(self, gicon):
        """Extract the best icon name from a GIcon."""
        if not gicon:
            return "drive-harddisk"
        
        # Check if it's a ThemedIcon (common for drives)
        if isinstance(gicon, Gio.ThemedIcon):
            names = gicon.get_names()
            if names:
                # Return the detailed name (first one)
                return names[0]
                
        # Fallback to string representation
        return gicon.to_string()

    def _get_usage(self, path):
        """Get filesystem usage stats if mounted."""
        if not path:
             return None
        try:
            f = Gio.File.new_for_path(path)
            info = f.query_filesystem_info(
                f"{Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE},{Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE}",
                None
            )
            size = info.get_attribute_uint64(Gio.FILE_ATTRIBUTE_FILESYSTEM_SIZE)
            free = info.get_attribute_uint64(Gio.FILE_ATTRIBUTE_FILESYSTEM_FREE)
            if size > 0:
                 return {"total": size, "free": free, "used": size - free}
        except Exception:
            pass
        return None

    @Slot(result=list)
    def get_volumes(self):
        """
        Returns a list of dicts for all drives/volumes.
        """
        items = []
        seen_uuids = set()
        seen_paths = set()
        
        # 1. Pre-process Mounts into a lookup
        mounts = self.monitor.get_mounts()
        mount_lookup = {}
        for m in mounts:
            muuid = m.get_uuid()
            if muuid:
                mount_lookup[muuid] = m
        
        # 2. Process Volumes (partitions, physical media)
        volumes = self.monitor.get_volumes()
        for volume in volumes:
            # Prefer UUID, fallback to device identifier
            uuid = volume.get_uuid()
            if not uuid:
                uuid = volume.get_identifier("unix-device")
            if not uuid:
                continue  # Skip if no identifier at all
            
            seen_uuids.add(uuid)
            
            # Check intrinsic mount OR lookup fallback
            mount = volume.get_mount()
            if not mount and uuid in mount_lookup:
                mount = mount_lookup[uuid]
                
            is_mounted = (mount is not None)
            path = mount.get_root().get_path() if is_mounted else ""
            
            if is_mounted and path:
                seen_paths.add(path)
                
            name = volume.get_name()
            
            # Custom Icon Logic for Root
            if is_mounted and path == "/":
                icon = "root"
            else:
                icon = self._get_icon_name(volume.get_icon())
            
            usage = self._get_usage(path) if is_mounted else None

            items.append({
                "identifier": uuid,
                "name": name,
                "path": path,
                "icon": icon,
                "isMounted": is_mounted,
                "usage": usage,
                "canMount": volume.can_mount(),
                "canUnmount": mount.can_unmount() if is_mounted else False,
                "type": "volume"
            })
            
        # 3. Process Remaining Mounts (network shares, ISOs, etc)
        for mount in mounts:
            uuid = mount.get_uuid()
            root = mount.get_root()
            path = root.get_path()
            
            # If we already processed this UUID via a Volume, skip
            if uuid and uuid in seen_uuids:
                continue
                
            # If we already processed this Path via a Volume, skip
            if path and path in seen_paths:
                continue
            
            # If no UUID, use URI as unique fallback ID
            if not uuid:
                uuid = root.get_uri()

            name = mount.get_name()
            icon = self._get_icon_name(mount.get_icon())
            usage = self._get_usage(path)

            items.append({
                "identifier": uuid,
                "name": name,
                "path": path,
                "icon": icon,
                "isMounted": True,
                "usage": usage,
                "canMount": False,
                "canUnmount": mount.can_unmount(),
                "type": "mount"
            })
            
        return items

    @Slot(str)
    def mount_volume(self, identifier):
        """
        Async mount a volume by UUID.
        Emits mountSuccess(uuid) or mountError(msg).
        """
        # Find the volume
        found_vol = None
        volumes = self.monitor.get_volumes()
        for volume in volumes:
            if volume.get_uuid() == identifier:
                found_vol = volume
                break
        
        if not found_vol:
            self.mountError.emit(f"Volume {identifier} not found")
            return
            
        if not found_vol.can_mount():
             self.mountError.emit(f"Volume {identifier} cannot be mounted")
             return

        # Mount operation
        op = Gio.MountOperation()
        # Note: We rely on standard GMountOperation behavior here.
        
        found_vol.mount(
            Gio.MountMountFlags.NONE,
            op,
            None, # Cancellable
            self._on_mount_finished,
            identifier
        )

    def _on_mount_finished(self, source_object, res, identifier):
        """Callback for mount completion."""
        try:
            source_object.mount_finish(res)
            self.mountSuccess.emit(identifier)
            # Volume state changed, so update list
            self.volumesChanged.emit()
        except GLib.Error as e:
            self.mountError.emit(str(e.message))

    @Slot(str)
    def unmount_volume(self, identifier):
        """
        Async unmount by UUID.
        Emits mountSuccess(uuid) or mountError(msg).
        """
        # Find the mount object
        found_mount = None
        
        # Check volumes first to get their mount
        volumes = self.monitor.get_volumes()
        for volume in volumes:
            if volume.get_uuid() == identifier:
                found_mount = volume.get_mount()
                break
        
        # If not found via volume, check direct mounts (e.g. network shares)
        if not found_mount:
            mounts = self.monitor.get_mounts()
            for mount in mounts:
                # Check UUID or Name fallback
                if mount.get_uuid() == identifier or mount.get_name() == identifier:
                    found_mount = mount
                    break
        
        if not found_mount:
            self.mountError.emit(f"Mount point for {identifier} not found")
            return
            
        found_mount.unmount_with_operation(
            Gio.MountUnmountFlags.NONE,
            Gio.MountOperation(),
            None,
            self._on_unmount_finished,
            identifier
        )

    def _on_unmount_finished(self, source_object, res, identifier):
        """Callback for unmount completion."""
        try:
            source_object.unmount_with_operation_finish(res)
            self.mountSuccess.emit(identifier)
            self.volumesChanged.emit()
        except GLib.Error as e:
            self.mountError.emit(str(e.message))
