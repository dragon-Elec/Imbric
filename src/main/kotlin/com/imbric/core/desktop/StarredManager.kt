package com.imbric.core.desktop

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.gnome.gio.*
import org.gnome.glib.GLib
import org.javagi.gobject.SignalConnection

/**
 * System-wide manager for starred/tagged files.
 * Queries Tracker3 via GIO's `recent::modified` and metadata attributes.
 *
 * Follows the TrashMonitor singleton pattern — system-wide state without a specific URI.
 * Populates `FileInfo.isStarred` via late enrichment in the app-layer aggregator.
 *
 * Ported from nautilus-starred.c / NautilusTagManager.
 */
class StarredManager private constructor(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) : StarredStateProvider {
    private val _starredUris = MutableStateFlow<Set<String>>(emptySet())
    override val starredUris: StateFlow<Set<String>> = _starredUris.asStateFlow()

    private var monitor: FileMonitor? = null
    private var monitorConnection: SignalConnection<FileMonitor.ChangedCallback>? = null
    private var metadataMonitor: FileMonitor? = null
    private var metadataMonitorConnection: SignalConnection<FileMonitor.ChangedCallback>? = null
    private var refreshJob: Job? = null

    init {
        Gio.`javagi$ensureInitialized`()
        setupMonitor()
        refresh()
    }

    /**
     * Sets up a file monitor on the metadata store for starred files.
     * Falls back to periodic refresh if monitoring is not supported.
     */
        private fun setupMonitor() {
        try {
            val homePath = System.getProperty("user.home") ?: "/"
            val homeDir = File.forPath(homePath)
            val gvfsMetadataDir = File.forPath("$homePath/.local/share/gvfs-metadata")

            val onChanged: (Any?, Any?, Any?) -> Unit = { _, _, _ ->
                refreshJob?.cancel()
                refreshJob = scope.launch {
                    delay(2000) // debounce rapid changes
                    refresh()
                }
            }

            monitor = homeDir.monitorDirectory(FileMonitorFlags.NONE, null)
            monitorConnection = monitor?.onChanged(onChanged)

            // Also monitor GNOME's gvfs-metadata directory for Tracker3 changes
            if (gvfsMetadataDir.queryExists(null)) {
                metadataMonitor = gvfsMetadataDir.monitorDirectory(FileMonitorFlags.NONE, null)
                metadataMonitorConnection = metadataMonitor?.onChanged(onChanged)
            }
        } catch (e: Exception) {
            GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                "Failed to setup StarredManager monitor: ${e.message}")
        }
    }

    /**
     * Refreshes the set of starred URIs by querying GIO attributes.
     * Uses the `metadata::nautilus-tags-starred` attribute set by GNOME's tag system.
     */
    fun refresh() {
        refreshJob?.cancel()
        refreshJob = scope.launch {
            try {
                val starred = mutableSetOf<String>()
                
                // Query recently used files for starred status
                val recentRoot = File.forUri("recent:///")
                val enumerator = recentRoot.enumerateChildren(
                    "standard::uri,metadata::nautilus-tags-starred",
                    FileQueryInfoFlags.NONE,
                    null
                )
                try {
                    var info = enumerator.nextFile(null)
                    while (info != null) {
                        val uri = info.getAttributeAsString("standard::uri")
                        val starredFlag = info.getAttributeBoolean("metadata::nautilus-tags-starred")
                        if (uri != null && starredFlag) {
                            starred.add(uri)
                        }
                        info = enumerator.nextFile(null)
                        yield()
                    }
                } finally {
                    enumerator.close(null)
                }
                
                _starredUris.value = starred
            } catch (e: Exception) {
                GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                    "Failed to refresh starred files: ${e.message}")
            }
        }
    }

    /**
     * Checks if a specific URI is starred.
     */
    override fun isStarred(uri: String): Boolean = uri in _starredUris.value

    /**
     * Toggle starred status for a file.
     * Note: This is a stub — actual Tracker3 write integration requires
     * direct SPARQL updates which will be implemented in a future phase.
     */
    override suspend fun toggleStarred(uri: String): Result<Boolean> {
        return try {
            if (isStarred(uri)) {
                _starredUris.update { it - uri }
            } else {
                _starredUris.update { it + uri }
            }
            Result.success(!isStarred(uri))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Releases the GIO monitors and cancels the refresh scope.
     *
     * Without this the two signal handlers stay attached to the user's home directory and
     * metadata store for the lifetime of the JVM, re-arming a debounced [refresh] on every
     * unrelated change. Behaviour is unchanged while the manager is active — this only
     * matters once the instance is being discarded.
     */
    private fun teardown() {
        refreshJob?.cancel()
        refreshJob = null
        monitorConnection?.disconnect()
        monitorConnection = null
        metadataMonitorConnection?.disconnect()
        metadataMonitorConnection = null
        monitor?.cancel()
        monitor = null
        metadataMonitor?.cancel()
        metadataMonitor = null
        scope.cancel()
    }

    companion object {
        @Volatile
        private var instance: StarredManager? = null

        fun getInstance(): StarredManager {
            return instance ?: synchronized(this) {
                instance ?: StarredManager().also { instance = it }
            }
        }

        /**
         * Destroys the singleton instance. Used for cleanup and testing.
         * Next call to [getInstance] will create a fresh instance.
         */
        fun clear() {
            synchronized(this) {
                instance?.teardown()
                instance = null
            }
        }
    }
}
