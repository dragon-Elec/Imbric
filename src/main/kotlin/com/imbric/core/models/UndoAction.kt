@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Describes how to reverse a completed file operation.
 * Stored on the undo stack. Each variant knows its reversal logic and UI label.
 *
 * Variants are based on HOW the action is reversed, not WHAT button the user clicked:
 * - TransferUndo: undo = delete destination OR move back to source
 * - CreateUndo: undo = delete the created file/folder
 * - RenameUndo: undo = rename back to original name
 */
sealed interface UndoAction {
    /** Human-readable description for UI labels: "Undo Copy", "Redo Rename" */
    val undoLabel: String
    /** Item description: "file.txt" or "3 items" */
    val itemDescription: String

    /**
     * Reverses copy, move, link operations.
     * Undo action: delete destination, or move destination back to source.
     */
    data class TransferUndo(
        override val undoLabel: String,       // "Copy", "Move", "Link"
        override val itemDescription: String,  // "file.txt" or "3 items"
        val destinations: List<String>,        // URIs to delete/move-back
        val sources: List<String>? = null,     // Original URIs (for move-back undo)
        val srcDir: String? = null,            // Original parent dir (for move-back)
        val backendId: String? = null
    ) : UndoAction

    /**
     * Reverses trash operations.
     * Undo action: restore from trash to original location.
     */
    data class TrashUndo(
        override val itemDescription: String,  // "file.txt" or "3 items"
        val trashedUris: List<String>,         // URIs in trash (trash:///...)
        val originalUris: List<String>,        // Original URIs before trashing
        val backendId: String? = null
    ) : UndoAction {
        override val undoLabel: String get() = "Trash"
    }

    /**
     * Reverses createFile, createFolder operations.
     * Undo action: delete the created file/folder.
     */
    data class CreateUndo(
        override val itemDescription: String,  // "file.txt" or "New Folder"
        val createdUri: String,                // URI of the created file/folder
        val backendId: String? = null
    ) : UndoAction {
        override val undoLabel: String get() = "Create"
    }

    /**
     * Reverses rename operations.
     * Undo action: rename back to original name.
     */
    data class RenameUndo(
        override val itemDescription: String,  // "file.txt"
        val currentUri: String,                // URI after rename
        val originalUri: String,               // URI before rename
        val currentName: String,               // Name after rename
        val originalName: String,              // Name before rename
        val backendId: String? = null
    ) : UndoAction {
        override val undoLabel: String get() = "Rename"
    }
}
