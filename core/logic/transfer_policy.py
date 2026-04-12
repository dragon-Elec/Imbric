"""
TransferPolicy — Logic for deciding actions on file conflicts and syncs.
"""

from enum import StrEnum, auto
from typing import TypedDict, NotRequired
from core.interfaces.io_backend import FileMetadata


class ConflictResolution(StrEnum):
    """Actions to take when a file exists at the destination."""

    PROMPT = "prompt"  # Ask the user (JIT)
    OVERWRITE = "overwrite"
    SKIP = "skip"
    RENAME = "rename"
    UPDATE = "update"  # Only overwrite if source is newer


class SyncPolicy(TypedDict):
    """Configuration for a transfer operation."""

    collision_mode: ConflictResolution
    always_copy: bool  # If True, bypass all comparison logic (Standard Copy)
    compare_size: bool
    compare_mtime: bool
    mtime_window_ms: int  # Tolerance for MTP/Network time drift


class TransferPolicy:
    """
    Stateless engine that decides the action for a specific file pair.
    """

    DEFAULT_POLICY: SyncPolicy = {
        "collision_mode": ConflictResolution.PROMPT,
        "always_copy": True,
        "compare_size": True,
        "compare_mtime": True,
        "mtime_window_ms": 2000,  # 2s window for FAT/MTP drift
    }

    BACKUP_POLICY: SyncPolicy = {
        "collision_mode": ConflictResolution.UPDATE,
        "always_copy": False,
        "compare_size": True,
        "compare_mtime": True,
        "mtime_window_ms": 2000,
    }

    @staticmethod
    def decide(
        src_meta: FileMetadata, dest_meta: FileMetadata | None, policy: SyncPolicy
    ) -> ConflictResolution:
        """
        Decide the action for a source file given the destination's state.
        """
        # 1. New file (No conflict)
        if dest_meta is None:
            return (
                ConflictResolution.OVERWRITE
            )  # 'Overwrite' is the default 'Go' signal

        # 2. Standard "Always Copy" mode
        if policy["always_copy"]:
            return policy["collision_mode"]

        # 3. Smart Comparison (Rsync-lite)
        is_identical = True

        if policy["compare_size"]:
            if src_meta["size"] != dest_meta["size"]:
                is_identical = False

        if is_identical and policy["compare_mtime"]:
            diff = abs(src_meta["mtime"] - dest_meta["mtime"])
            if diff > (policy["mtime_window_ms"] / 1000.0):
                is_identical = False

        if is_identical:
            return ConflictResolution.SKIP

        # 4. Handle non-identical conflict based on mode
        mode = policy["collision_mode"]

        if mode == ConflictResolution.UPDATE:
            # Overwrite only if source is strictly newer
            if src_meta["mtime"] > dest_meta["mtime"]:
                return ConflictResolution.OVERWRITE
            return ConflictResolution.SKIP

        return mode
