package com.imbric.core.ifs

import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.models.*
import kotlinx.coroutines.flow.Flow

object BackendRegistry {
    private val backends = mutableMapOf<String, BackendContract>()
    private var defaultBackend: BackendContract? = null

    fun register(scheme: String, backend: BackendContract) {
        backends[scheme] = backend
    }

    fun setDefault(backend: BackendContract) {
        defaultBackend = backend
    }

    fun getDefault(): BackendContract? = defaultBackend

    fun get(pathOrUri: String): BackendContract? {
        // 1. If it's a raw path (no scheme), prefer defaultBackend if it exists
        if (!pathOrUri.contains("://") && defaultBackend != null) {
            return defaultBackend
        }

        val scheme = pathOrUri.substringBefore("://", "")
        
        // 2. Try exact scheme match
        if (scheme.isNotEmpty()) {
            val exactMatch = backends[scheme]
            if (exactMatch != null && exactMatch.canHandle(pathOrUri)) return exactMatch
        }

        // 3. Try all backends with canHandle (smart routing)
        backends.values.forEach { backend ->
            if (backend.canHandle(pathOrUri)) return backend
        }

        // 4. Fallback to default ONLY if it's a file scheme or raw path
        return if (scheme.isEmpty() || scheme == "file") defaultBackend else null
    }

    fun getRegisteredSchemes(): List<String> = backends.keys.toList()

    /**
     * Clears all registered backends. Used for testing.
     */
    fun clear() {
        backends.clear()
        defaultBackend = null
    }

    // Convenience
    suspend fun list(uri: String): List<FileEntry>? = get(uri)?.list(uri)
    suspend fun getMetadata(uri: String): Result<FileInfo>? = get(uri)?.getMetadata(uri)
}
