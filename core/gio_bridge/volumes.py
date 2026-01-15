import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio

class VolumesBridge:
    """
    Wraps Gio.VolumeMonitor to list connected drives.
    """
    def __init__(self):
        self.monitor = Gio.VolumeMonitor.get()
        
    def get_volumes(self):
        """
        Returns a list of dicts: [{'name': 'Samsung T7', 'path': '/media/user/T7', 'icon': 'drive-harddisk'}]
        """
        items = []
        mounts = self.monitor.get_mounts()
        
        for mount in mounts:
            # We want actual filesystem mounts
            root = mount.get_root()
            path = root.get_path()
            name = mount.get_name()
            icon = mount.get_icon().to_string() if mount.get_icon() else "drive-harddisk"
            
            if path:
                items.append({
                    "name": name, 
                    "path": path, 
                    "icon": icon,
                    "type": "volume"
                })
                
        return items
