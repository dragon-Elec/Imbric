package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.ifs.BackendCapabilities
import com.imbric.core.ifs.Locality
import com.imbric.core.ifs.LatencyProfile
import com.imbric.core.ifs.FileAction
import com.imbric.core.models.*
import org.junit.jupiter.api.Test
import kotlin.system.measureTimeMillis

class DummyBackend : BackendContract {
    override val scheme = "slow"
    override val displayName = "Slow Backend"

    override suspend fun list(uri: String, sortKey: SortKey): List<FileEntry> = emptyList()
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
    override suspend fun getTrashBackend(registry: BackendRegistry): BackendContract? = null
}

class CanTrashBenchmarkTest {
    @Test
    fun benchmarkCanTrash() {
        BackendRegistry.register("slow", DummyBackend())

        val trashManager = TrashManager(BackendRegistry)

        val time = measureTimeMillis {
            for (i in 1..100) {
                trashManager.canTrash("slow:///file" + i + ".txt")
            }
        }

        println("BENCHMARK_RESULT (supportsTrash=false): " + time + " ms")
    }
}
