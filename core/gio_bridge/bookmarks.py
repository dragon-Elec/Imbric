from pathlib import Path
from urllib.parse import unquote

class BookmarksBridge:
    """
    Reads GTK 3.0 bookmarks to populate the sidebar.
    """
    def __init__(self):
        self.bookmarks_file = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
    
    def get_bookmarks(self):
        """
        Returns a list of dicts: [{'name': 'Pictures', 'path': '/home/user/Pictures'}, ...]
        """
        items = []
        
        # Add Standard Home Dir items manually similar to Nautilus if needed, 
        # but usually checking the file is enough for custom ones. 
        # For a full sidebar we'd also want XDG user dirs (Documents, Downloads, etc.)
        
        if not self.bookmarks_file.exists():
            return items

        try:
            with open(self.bookmarks_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Format: file:///home/user/Folder Name
                    # OR: file:///home/user/Folder CustomName
                    parts = line.split(" ", 1)
                    uri = parts[0]
                    
                    if not uri.startswith("file://"):
                        continue
                        
                    path = unquote(uri[7:]) # Strip file://
                    
                    if len(parts) > 1:
                        name = parts[1]
                    else:
                        # Use directory name as label
                        name = Path(path).name
                        
                    items.append({"name": name, "path": path, "icon": "folder"})
                    
        except Exception as e:
            print(f"Error reading bookmarks: {e}")
            
        return items
