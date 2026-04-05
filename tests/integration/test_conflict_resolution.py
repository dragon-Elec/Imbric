"""
Integration tests for conflict resolution.

Tests the full conflict detection → user resolution → retry cycle.
"""

import pytest
import time
import os
from pathlib import Path


class TestConflictResolution:
    """Test conflict detection and resolution workflow."""

    def test_overwrite_conflict_resolution(self, file_ops_system, temp_dir, qapp):
        """
        Test detecting a conflict and resolving with overwrite.

        Scenario:
        1. Create source file with "SOURCE_CONTENT"
        2. Create destination file with "DEST_CONTENT"
        3. Copy source to destination (conflict detected)
        4. Resolve with "overwrite"
        5. Verify destination now has "SOURCE_CONTENT"
        """
        file_ops = file_ops_system["file_ops"]
        tm = file_ops_system["tm"]

        # Setup files
        src = temp_dir / "src.txt"
        src.write_text("SOURCE_CONTENT")
        dest = temp_dir / "dest.txt"
        dest.write_text("DEST_CONTENT")

        # Track events
        conflict_job_id = []
        conflict_data = []

        def on_conflict(job_id, data):
            conflict_job_id.append(job_id)
            conflict_data.append(data)

        tm.conflictDetected.connect(on_conflict)

        # Start copy (should conflict)
        tid = tm.startTransaction("Conflict Test")
        job_id = file_ops.copy(str(src), str(dest), tid)

        # Wait for conflict detection
        from tests.helpers.waiters import wait_for_with_events

        timeout = 50  # 500ms
        while len(conflict_job_id) == 0 and timeout > 0:
            qapp.processEvents()
            time.sleep(0.01)
            timeout -= 1

        assert len(conflict_job_id) > 0, "Conflict should be detected"
        assert conflict_data[0]["error"] == "exists", "Error should be 'exists'"

        # Verify file was NOT overwritten yet
        assert dest.read_text() == "DEST_CONTENT", "File should NOT be overwritten yet"

        # Resolve with overwrite
        tm.resolveConflict(conflict_job_id[0], "overwrite")

        # Wait for completion
        timeout = 50
        while timeout > 0:
            qapp.processEvents()
            if not dest.exists() or dest.read_text() == "SOURCE_CONTENT":
                break
            time.sleep(0.01)
            timeout -= 1

        # Verify file WAS overwritten
        assert dest.read_text() == "SOURCE_CONTENT", (
            "File SHOULD be overwritten after resolution"
        )

    def test_skip_conflict_resolution(self, file_ops_system, temp_dir, qapp):
        """
        Test resolving conflict by skipping.

        Destination file should remain unchanged.
        """
        file_ops = file_ops_system["file_ops"]
        tm = file_ops_system["tm"]

        src = temp_dir / "skip_src.txt"
        src.write_text("SOURCE")
        dest = temp_dir / "skip_dest.txt"
        dest.write_text("DEST")

        conflict_job_id = []

        def on_conflict(job_id, data):
            conflict_job_id.append(job_id)

        tm.conflictDetected.connect(on_conflict)

        tid = tm.startTransaction("Skip Test")
        file_ops.copy(str(src), str(dest), tid)

        # Wait for conflict
        timeout = 50
        while len(conflict_job_id) == 0 and timeout > 0:
            qapp.processEvents()
            time.sleep(0.01)
            timeout -= 1

        assert len(conflict_job_id) > 0, "Conflict should be detected"

        # Resolve with skip
        tm.resolveConflict(conflict_job_id[0], "skip")

        # Wait
        time.sleep(0.2)
        qapp.processEvents()

        # Destination should still have original content
        assert dest.read_text() == "DEST", "File should remain unchanged"

    def test_rename_conflict_resolution(self, file_ops_system, temp_dir, qapp):
        """
        Test resolving conflict by renaming.

        Original destination stays, source is copied with new name.
        """
        file_ops = file_ops_system["file_ops"]
        tm = file_ops_system["tm"]

        src = temp_dir / "rename_src.txt"
        src.write_text("SOURCE")
        dest = temp_dir / "rename_dest.txt"
        dest.write_text("DEST")

        conflict_job_id = []

        def on_conflict(job_id, data):
            conflict_job_id.append(job_id)

        tm.conflictDetected.connect(on_conflict)

        tid = tm.startTransaction("Rename Conflict Test")
        file_ops.copy(str(src), str(dest), tid)

        # Wait for conflict
        timeout = 50
        while len(conflict_job_id) == 0 and timeout > 0:
            qapp.processEvents()
            time.sleep(0.01)
            timeout -= 1

        assert len(conflict_job_id) > 0, "Conflict should be detected"

        # Resolve with rename
        tm.resolveConflict(conflict_job_id[0], "rename", new_name="renamed.txt")

        # Wait
        time.sleep(0.3)
        qapp.processEvents()

        # Both files should exist
        assert dest.exists(), "Original destination should exist"
        assert dest.read_text() == "DEST", "Original should be unchanged"

        renamed = temp_dir / "renamed.txt"
        assert renamed.exists(), "Renamed file should exist"
        assert renamed.read_text() == "SOURCE", (
            "Renamed file should have source content"
        )
