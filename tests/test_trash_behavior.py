
import os
import sys
import time
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

def test_trash_behavior():
    print("--- Starting Trash Behavior Test ---")
    
    # 1. Setup Test Files
    cwd = os.getcwd()
    test_file_path = os.path.join(cwd, "test_trash_file.txt")
    
    # Create file
    with open(test_file_path, "w") as f:
        f.write("Content 1")
    print(f"Created: {test_file_path}")
    
    # 2. Trash It (First Time)
    gfile = Gio.File.new_for_path(test_file_path)
    try:
        gfile.trash(None)
        print("Trashed: Content 1")
    except Exception as e:
        print(f"FAIL: Could not trash file: {e}")
        return

    time.sleep(1.1) # Wait to ensure different deletion date

    # 3. Create Same File Again (Content 2) and Trash It
    with open(test_file_path, "w") as f:
        f.write("Content 2")
    gfile = Gio.File.new_for_path(test_file_path)
    try:
        gfile.trash(None)
        print("Trashed: Content 2 (Duplicate Path)")
    except Exception as e:
        print(f"FAIL: Could not trash second file: {e}")
        return

    # 4. Enumerate Trash and Inspect Attributes
    print("\n--- Enumerating trash:/// ---")
    trash_root = Gio.File.new_for_uri("trash:///")
    enumerator = trash_root.enumerate_children(
        "standard::name,standard::display-name,trash::orig-path,trash::deletion-date",
        Gio.FileQueryInfoFlags.NONE,
        None
    )
    
    candidates = []
    
    while True:
        info = enumerator.next_file(None)
        if not info:
            break
        
        name = info.get_name()
        display = info.get_display_name()
        orig_path_bytes = info.get_attribute_byte_string("trash::orig-path")
        orig_path = orig_path_bytes if orig_path_bytes else None
        date = info.get_attribute_string("trash::deletion-date")
        
        if orig_path == test_file_path:
            print(f"MATCH FOUND: {name}")
            print(f"  Display: {display}")
            print(f"  Orig Path: {orig_path}")
            print(f"  Date: {date}")
            candidates.append((date, info))
        
    enumerator.close(None)
    
    if not candidates:
        print("FAIL: No matching files found in trash!")
        return

    # 5. Logic Verification: Select Newest
    dest_path = test_file_path
    
    # Sort by date descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_candidate_date, best_candidate_info = candidates[0]
    
    print(f"\nTarget to Restore: {best_candidate_info.get_name()} (Date: {best_candidate_date})")
    
    # 6. Attempt Restore
    trash_file = trash_root.get_child(best_candidate_info.get_name())
    dest_file = Gio.File.new_for_path(dest_path)
    
    try:
        trash_file.move(
            dest_file,
            Gio.FileCopyFlags.NO_FALLBACK_FOR_MOVE,
            None, None, None
        )
        print("Restore SUCCESS")
    except Exception as e:
        print(f"Restore FAILED: {e}")
        
    # 7. Verify Content
    if os.path.exists(dest_path):
        with open(dest_path, "r") as f:
            content = f.read()
        print(f"Restored Content: '{content}'")
        if content == "Content 2":
            print("PASS: Correctly restored the newest version.")
        else:
            print("FAIL: Restored the WRONG version.")
            
    # Cleanup
    if os.path.exists(dest_path):
        os.remove(dest_path)
        
    print("--- Test Complete ---")

if __name__ == "__main__":
    test_trash_behavior()
