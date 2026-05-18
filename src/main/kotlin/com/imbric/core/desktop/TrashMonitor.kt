package com.imbric.core.desktop

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.gnome.gio.*
import org.gnome.glib.GLib

/**
 * A singleton monitor that watches the native trash system for changes.
 * Ported from nautilus-trash-monitor.c.
 *
 * Uses a native [FileMonitor] on trash:/// to provide real-time updates
 * without polling.
 */
class TrashMonitor private constructor(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    private val _isEmpty = MutableStateFlow(true)
    val isEmpty: StateFlow<Boolean> = _isEmpty.asStateFlow()

    private var monitor: FileMonitor? = null
    private var refreshJob: Job? = null

    init {
        Gio.`javagi$ensureInitialized`()
        setupMonitor()
        refresh()
    }

    private fun setupMonitor() {
        try {
            val trashRoot = File.newForUri("trash:///")
            monitor = trashRoot.monitorDirectory(FileMonitorFlags.NONE, null)
            
            monitor?.onChanged { _, _, _ ->
                // Coalesce multiple changes (e.g. batch trashing) with a small debounce
                refreshJob?.cancel()
                refreshJob = scope.launch {
                    delay(500)
                    refresh()
                }
            }
        } catch (e: Exception) {
            org.gnome.glib.GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING, "Failed to setup TrashMonitor: ${e.message}")
        }
    }

    /**
     * Manually triggers a refresh of the trash state.
     * Uses the G_FILE_ATTRIBUTE_TRASH_ITEM_COUNT optimization to avoid full enumeration.
     * Conflates rapid calls — if a refresh is already in-flight, it is cancelled and restarted.
     */
    fun refresh() {
        refreshJob?.cancel()
        refreshJob = scope.launch {
            try {
                val trashRoot = File.newForUri("trash:///")
                val info = trashRoot.queryInfo("trash::item-count", FileQueryInfoFlags.NONE, null)
                val count = info.getAttributeUint32("trash::item-count")
                _isEmpty.value = count == 0
            } catch (e: Exception) {
                // Fallback to manual check if attribute is not supported
                _isEmpty.value = checkManualEmpty()
            }
        }
    }

    private fun checkManualEmpty(): Boolean {
        val enumerator = try {
            val trashRoot = File.newForUri("trash:///")
            trashRoot.enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
        } catch (e: Exception) {
            return true
        }
        return try {
            val hasItems = enumerator.nextFile(null) != null
            !hasItems
        } finally {
            enumerator.close(null)
        }
    }

    companion object {
        @Volatile
        private var instance: TrashMonitor? = null

        fun getInstance(): TrashMonitor {
            return instance ?: synchronized(this) {
                instance ?: TrashMonitor().also { instance = it }
            }
        }
    }
}
