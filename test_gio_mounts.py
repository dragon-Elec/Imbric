from gi.repository import Gio
import sys

# User-provided example path
path = "/run/user/1000/gvfs/mtp:host=Xiaomi_Xiaomi_11i_ginb9tfub65d6lbe"
gfile = Gio.File.new_for_path(path)

print(f"Path: {path}")
print(f"URI: {gfile.get_uri()}")

try:
    info = gfile.query_info("*", Gio.FileQueryInfoFlags.NONE, None)
    print(f"Display Name: {info.get_display_name()}")
    print(f"Target URI: {info.get_attribute_string('standard::target-uri')}")
    
    # Check for mount
    try:
        mount = gfile.find_enclosing_mount(None)
        if mount:
            print(f"Mount Name: {mount.get_name()}")
            print(f"Mount Root: {mount.get_root().get_uri()}")
    except:
        print("Mount not found or error finding it")
except Exception as e:
    print(f"Error querying info: {e}")
