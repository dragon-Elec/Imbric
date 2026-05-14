package com.imbric.core.logic

import com.imbric.core.ifs.uriParent
import com.imbric.core.models.FileInfo
import kotlinx.datetime.Instant

/**
 * Conflict resolution decision.
 * Ported from Python transfer_policy.py – the "Rsync-lite" engine.
 */
sealed class ConflictAction {
    object Overwrite : ConflictAction()
    object Merge : ConflictAction() // For directory collisions
    object Skip : ConflictAction()
    data class Rename(val newName: String) : ConflictAction()
    object Prompt : ConflictAction()
    object Cancel : ConflictAction()
}

/**
 * Sync policy strategies.
 * Refactored to interface to allow application-layer extensions.
 */
interface SyncPolicy {
    var applyToAllIdentical: Boolean
    var applyToAllDifferent: Boolean
    var applyToAllFolders: Boolean

    fun decide(src: FileInfo, dest: FileInfo): ConflictAction

    companion object {
        val AlwaysOverwrite get() = AlwaysOverwritePolicy()
        val AlwaysSkip get() = AlwaysSkipPolicy()
        val ModifiedOnly get() = ModifiedOnlyPolicy()
        val AutoRename get() = AutoRenamePolicy()
        val Standard get() = StandardPolicy()

        /** Factory for quick lambda-based policies */
        fun custom(resolver: (FileInfo, FileInfo) -> ConflictAction): SyncPolicy = object : BaseSyncPolicy() {
            override fun decide(src: FileInfo, dest: FileInfo) = resolver(src, dest)
        }
    }
}

abstract class BaseSyncPolicy : SyncPolicy {
    override var applyToAllIdentical: Boolean = false
    override var applyToAllDifferent: Boolean = false
    override var applyToAllFolders: Boolean = false
}

class AlwaysOverwritePolicy : BaseSyncPolicy() {
    override fun decide(src: FileInfo, dest: FileInfo): ConflictAction = ConflictAction.Overwrite
}

class AlwaysSkipPolicy : BaseSyncPolicy() {
    override fun decide(src: FileInfo, dest: FileInfo): ConflictAction = ConflictAction.Skip
}

class ModifiedOnlyPolicy : BaseSyncPolicy() {
    override fun decide(src: FileInfo, dest: FileInfo): ConflictAction {
        return if (XferArbiter.isModified(src, dest)) ConflictAction.Overwrite else ConflictAction.Skip
    }
}

class AutoRenamePolicy : BaseSyncPolicy() {
    override fun decide(src: FileInfo, dest: FileInfo): ConflictAction = ConflictAction.Rename(XferArbiter.generateNewName(dest.name))
}

class StandardPolicy : BaseSyncPolicy() {
    override fun decide(src: FileInfo, dest: FileInfo): ConflictAction {
        return if (XferArbiter.isSameFolder(src, dest)) {
            ConflictAction.Rename(XferArbiter.generateNewName(dest.name))
        } else {
            ConflictAction.Prompt
        }
    }
}

/**
 * Stateless transfer decision engine.
 * Pure math: compares src vs dest and returns a decision.
 */
object XferArbiter {
    private val NAME_COUNTER_REGEX = Regex("""(.+)\s\((\d+)\)$""")

    fun decide(src: FileInfo, dest: FileInfo, policy: SyncPolicy): ConflictAction {
        // Special case: Directory merge - Core rule that applies before any policy
        if (src.isDirectory && dest.isDirectory) {
            return ConflictAction.Merge
        }

        return policy.decide(src, dest)
    }

    internal fun isSameFolder(src: FileInfo, dest: FileInfo): Boolean {
        val srcParent = src.path.uriParent
        val destParent = dest.path.uriParent
        return srcParent == destParent && srcParent.isNotEmpty()
    }

    internal fun isModified(src: FileInfo, dest: FileInfo): Boolean {
        // Size check
        if (src.size != dest.size) return true
        
        // Modification time check (if available)
        val srcTime = src.modifiedTime ?: return true
        val destTime = dest.modifiedTime ?: return true
        
        // If source is newer or times differ significantly
        if (srcTime > destTime) return true
        
        // Tolerance: if within 2 seconds, consider same (filesystem rounding)
        val diff = kotlin.math.abs(srcTime.toEpochMilliseconds() - destTime.toEpochMilliseconds())
        return diff > 2000
    }

    internal fun generateNewName(original: String): String {
        // 1. Find the extension boundary
        val dotIndex = original.lastIndexOf('.')
        val (baseName, extension) = if (dotIndex > 0) {
            original.substring(0, dotIndex) to original.substring(dotIndex)
        } else {
            original to ""
        }

        // 2. Check for existing (n) pattern
        val match = NAME_COUNTER_REGEX.matchEntire(baseName)
        
        return if (match != null) {
            val prefix = match.groupValues[1]
            val count = match.groupValues[2].toIntOrNull() ?: 0
            "$prefix (${count + 1})$extension"
        } else {
            "$baseName (1)$extension"
        }
    }

    // --- Capability checks ---
    fun classifyConflict(src: FileInfo, dest: FileInfo): ConflictType {
        return when {
            src.isDirectory && dest.isDirectory -> ConflictType.DIRECTORY_MERGE
            src.isDirectory && !dest.isDirectory -> ConflictType.FOLDER_REPLACE_FILE
            !src.isDirectory && dest.isDirectory -> ConflictType.FILE_REPLACE_FOLDER
            isSameContent(src, dest) -> ConflictType.IDENTICAL_FILE
            else -> ConflictType.DIFFERENT_FILE
        }
    }

    fun canOverwrite(src: FileInfo, dest: FileInfo): Boolean {
        return dest.isWritable && src.size > 0
    }

    fun isSameContent(src: FileInfo, dest: FileInfo): Boolean {
        return src.size == dest.size && !isModified(src, dest)
    }
}

/**
 * Response from the UI when a conflict occurs.
 */
data class ConflictResponse(
    val action: ConflictAction,
    val applyToAll: Boolean = false
)

/**
 * Types of conflicts for sticky decisions.
 */
enum class ConflictType {
    IDENTICAL_FILE,
    DIFFERENT_FILE,
    DIRECTORY_MERGE,
    FOLDER_REPLACE_FILE,
    FILE_REPLACE_FOLDER
}

/**
 * Context provided to the UI when a conflict requires manual resolution.
 */
data class ConflictContext(
    val src: String,
    val dest: String,
    val srcMeta: FileInfo,
    val destMeta: FileInfo,
    val type: ConflictType
)
