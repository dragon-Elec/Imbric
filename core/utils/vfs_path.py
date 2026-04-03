import urllib.parse
import os

def vfs_basename(path_or_uri: str) -> str:
    """URI-safe basename that handles unquoting and various schemes."""
    if not path_or_uri:
        return ""
    
    path = path_or_uri.rstrip("/")
    if "://" in path:
        scheme, rest = path.split("://", 1)
        if not rest:
            return ""
        name = rest.split("/")[-1]
    else:
        name = os.path.basename(path)
    
    return urllib.parse.unquote(name)

def vfs_dirname(path_or_uri: str) -> str:
    """URI-safe dirname that preserves the scheme/root."""
    if not path_or_uri:
        return ""
        
    path = path_or_uri.rstrip("/")
    if "://" in path:
        scheme, rest = path.split("://", 1)
        if not rest:
            return path_or_uri
        parts = rest.split("/")
        if len(parts) <= 1:
            return f"{scheme}://"
        return f"{scheme}://{'/'.join(parts[:-1])}"
    else:
        return os.path.dirname(path)

def vfs_join(base: str, *parts) -> str:
    """URI-safe join. os.path.join breaks on schemes."""
    if not base:
        return "/".join(p for p in parts if p)
        
    result = base.rstrip("/")
    for part in parts:
        if not part: continue
        result = f"{result}/{part.lstrip('/')}"
    return result
