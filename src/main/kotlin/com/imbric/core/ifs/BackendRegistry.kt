package com.imbric.core.ifs

import com.imbric.core.models.*
import kotlinx.coroutines.flow.Flow

object BackendRegistry {
    private val ioBackends = mutableMapOf<String, IOBackend>()
    private var defaultIo: IOBackend? = null

    fun registerIo(scheme: String, backend: IOBackend) {
        ioBackends[scheme] = backend
    }

    fun setDefaultIo(backend: IOBackend) {
        defaultIo = backend
    }

    fun getDefaultIo(): IOBackend? = defaultIo

    fun getIo(pathOrUri: String): IOBackend? {
        // 1. If it's a raw path (no scheme), prefer defaultIo if it exists
        if (!pathOrUri.contains("://") && defaultIo != null) {
            return defaultIo
        }

        val scheme = pathOrUri.substringBefore("://", "")
        
        // 2. Try exact scheme match
        if (scheme.isNotEmpty()) {
            val exactMatch = ioBackends[scheme]
            if (exactMatch != null && exactMatch.canHandle(pathOrUri)) return exactMatch
        }

        // 3. Try all backends with canHandle (smart routing)
        ioBackends.values.forEach { backend ->
            if (backend.canHandle(pathOrUri)) return backend
        }

        // 4. Fallback to default ONLY if it's a file scheme or raw path
        return if (scheme.isEmpty() || scheme == "file") defaultIo else null
    }

    fun getRegisteredSchemes(): List<String> = ioBackends.keys.toList()

    /**
     * Clears all registered backends. Used for testing.
     */
    fun clear() {
        ioBackends.clear()
        defaultIo = null
    }

    // Convenience
    fun list(uri: String): Flow<FileEntry>? = getIo(uri)?.list(uri)
    suspend fun getMetadata(uri: String): Result<FileInfo>? = getIo(uri)?.getMetadata(uri)
}
