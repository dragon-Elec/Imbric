package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.BackendCapabilities
import com.imbric.core.ifs.Locality
import com.imbric.core.ifs.LatencyProfile
import com.imbric.core.ifs.FileAction
import com.imbric.core.models.*
import com.imbric.core.models.FileJob
import com.imbric.core.models.TransferProgress
import com.imbric.core.models.TrashItem
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import org.junit.jupiter.api.Test
import kotlin.system.measureTimeMillis

class DummyBackend : IOBackend {
    override val scheme = "slow"
    override val displayName = "Slow Backend"

    override fun list(uri: String, sortKey: SortKey): Flow<FileEntry> = emptyFlow()
    override suspend fun getMetadata(uri: String): Result<FileInfo> = Result.failure(Exception())
    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = Result.failure(Exception())

    override fun exists(uri: String): Boolean {
        Thread.sleep(10) // Simulate slow I/O
        return true
    }
    override fun getCapabilities(uri: String) = BackendCapabilities(
        locality = Locality.LOCAL,
        latencyProfile = LatencyProfile.HIGH,
        supportsTrash = false, // Short circuit test
        supportsSymlinks = false
    )
    override suspend fun canPerform(action: FileAction, uri: String): Boolean = true

    override suspend fun trash(job: FileJob, recoverTrashUri: Boolean): Result<String> = Result.success("")
    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = Result.success("")
    override suspend fun emptyTrash(): Result<Int> = Result.success(0)
    override suspend fun listTrash(): Result<List<TrashItem>> = Result.success(emptyList())
    override suspend fun delete(job: FileJob): Result<Unit> = Result.success(Unit)
    override suspend fun copy(job: FileJob): Flow<TransferProgress> = emptyFlow()
    override suspend fun move(job: FileJob): Flow<TransferProgress> = emptyFlow()
    override suspend fun rename(uri: String, newName: String): Result<String> = Result.success("")
    override suspend fun createFolder(parentUri: String, name: String): Result<String> = Result.success("")
    override suspend fun createFile(parentUri: String, name: String): Result<String> = Result.success("")
    override suspend fun getTrashBackend(registry: BackendRegistry): IOBackend? = null
}

class CanTrashBenchmarkTest {
    @Test
    fun benchmarkCanTrash() {
        BackendRegistry.registerIo("slow", DummyBackend())

        val trashManager = TrashManager(BackendRegistry)

        val time = measureTimeMillis {
            for (i in 1..100) {
                trashManager.canTrash("slow:///file" + i + ".txt")
            }
        }

        println("BENCHMARK_RESULT (supportsTrash=false): " + time + " ms")
    }
}
