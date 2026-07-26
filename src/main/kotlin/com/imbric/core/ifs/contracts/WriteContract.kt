package com.imbric.core.ifs.contracts

import com.imbric.core.models.FileJob
import com.imbric.core.models.TransferProgress
import kotlinx.coroutines.flow.Flow

interface WriteContract {
    suspend fun copy(job: FileJob): Flow<TransferProgress>
    suspend fun move(job: FileJob): Flow<TransferProgress>
    suspend fun delete(job: FileJob): Result<Unit>
    suspend fun createFolder(parentUri: String, name: String): Result<String>
    suspend fun createFile(parentUri: String, name: String): Result<String>
    suspend fun rename(uri: String, newName: String): Result<String>

    /**
     * Creates a symbolic link at [linkUri] pointing to [targetUri].
     * Default returns UnsupportedOperationException — backends with native symlink support override this.
     */
    suspend fun createLink(targetUri: String, linkUri: String): Result<String> = Result.failure(UnsupportedOperationException("Symlink creation not supported"))
}
