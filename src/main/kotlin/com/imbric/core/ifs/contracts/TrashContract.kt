package com.imbric.core.ifs.contracts

import com.imbric.core.models.FileJob
import com.imbric.core.models.TrashItem

interface TrashContract {
    suspend fun trash(job: FileJob, recoverTrashUri: Boolean = true): Result<String>
    suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String>
    suspend fun listTrash(): Result<List<TrashItem>> = Result.failure(UnsupportedOperationException("Trash not supported"))
    suspend fun emptyTrash(): Result<Int> = Result.failure(UnsupportedOperationException("Trash not supported"))
    suspend fun isTrashEmpty(uri: String): Boolean = true
}
