package com.imbric.app.aggregators

import com.imbric.core.desktop.BookmarkList
import com.imbric.core.desktop.DeviceManager
import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.models.FileEntry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** A single quick-access entry on the homepage (XDG dir, Trash, or user bookmark). */
data class HomeQuickAccessItem(
    val label: String,
    val uri: String,
    val iconName: String? = null,
)

/** A storage volume with usage bars (mounted drive or root/home filesystem). */
data class HomeStorageItem(
    val label: String,
    val uri: String,
    val totalBytes: Long,
    val availableBytes: Long,
    val usedPercent: Double,
)

/** One grouped slice of recent files (Today / Yesterday / This Week / Earlier). */
data class HomeRecentGroup(
    val label: String,
    val items: List<FileEntry>,
)

/** Immutable snapshot of everything the homepage renders. */
data class HomeUiState(
    val recents: List<HomeRecentGroup> = emptyList(),
    val quickAccess: List<HomeQuickAccessItem> = emptyList(),
    val storage: List<HomeStorageItem> = emptyList(),
    val loading: Boolean = true,
)

/**
 * Aggregates raw core signals (recent files, bookmarks, drives, disk usage)
 * into the homepage UI state. Lives in the app layer — core stays untouched.
 *
 * All data sources are injected for testability (fake backends, fake volume provider).
 */
class HomeAggregator(
    private val registry: BackendRegistry,
    private val bookmarks: BookmarkList,
    private val devices: DeviceManager,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    private val homeDir = System.getProperty("user.home")

    init {
        scope.launch(Dispatchers.IO) { refresh() }
        // Re-aggregate when bookmarks or drives change.
        scope.launch(Dispatchers.IO) {
            combine(bookmarks.bookmarks, devices.drives) { b, d -> b.size + d.size }
                .distinctUntilChanged()
                .collect { refresh() }
        }
    }

    /** Reloads all sections. Safe to call repeatedly (idempotent). */
    suspend fun refresh() {
        val recents = loadRecents()
        val quickAccess = buildQuickAccess()
        val storage = loadStorage()
        _state.value = HomeUiState(
            recents = recents,
            quickAccess = quickAccess,
            storage = storage,
            loading = false,
        )
    }

    // --- Recent files -------------------------------------------------------

    private suspend fun loadRecents(): List<HomeRecentGroup> {
        val recentBackend = registry.get("recent:///")
        val all = recentBackend?.list("recent:///") ?: emptyList()
        if (all.isEmpty()) return emptyList()

        val now = LocalDate.now()
        val zone = ZoneId.systemDefault()

        fun dayOf(entry: FileEntry): LocalDate? {
            val inst = entry.modifiedTime ?: return null
            return java.time.Instant.ofEpochMilli(inst.toEpochMilliseconds())
                .atZone(zone).toLocalDate()
        }

        val today = mutableListOf<FileEntry>()
        val yesterday = mutableListOf<FileEntry>()
        val thisWeek = mutableListOf<FileEntry>()
        val earlier = mutableListOf<FileEntry>()

        all.take(50).forEach { entry ->
            val d = dayOf(entry)
            when {
                d == null -> earlier.add(entry)
                d == now -> today.add(entry)
                d == now.minusDays(1) -> yesterday.add(entry)
                d >= now.minusDays(7) -> thisWeek.add(entry)
                else -> earlier.add(entry)
            }
        }

        return buildList {
            if (today.isNotEmpty()) add(HomeRecentGroup("Today", today))
            if (yesterday.isNotEmpty()) add(HomeRecentGroup("Yesterday", yesterday))
            if (thisWeek.isNotEmpty()) add(HomeRecentGroup("This week", thisWeek))
            if (earlier.isNotEmpty()) add(HomeRecentGroup("Earlier", earlier))
        }
    }

    // --- Quick access -------------------------------------------------------

    private fun buildQuickAccess(): List<HomeQuickAccessItem> {
        val items = mutableListOf<HomeQuickAccessItem>()
        items += HomeQuickAccessItem("Home", "file://$homeDir", "user-home")
        items += HomeQuickAccessItem("Downloads", "file://$homeDir/Downloads", "folder-download")
        items += HomeQuickAccessItem("Documents", "file://$homeDir/Documents", "folder-documents")
        items += HomeQuickAccessItem("Trash", "trash:///", "user-trash")
        bookmarks.getAll().forEach { bm ->
            items += HomeQuickAccessItem(bm.displayName, bm.uri, bm.icon)
        }
        return items
    }

    // --- Storage ------------------------------------------------------------

    private suspend fun loadStorage(): List<HomeStorageItem> {
        val items = mutableListOf<HomeStorageItem>()

        // Root + home filesystems via the default backend's getUsage.
        val fileBackend = registry.get("file:///")
        listOf(
            "Root" to "file:///",
            "Home" to "file://$homeDir",
        ).forEach { (label, uri) ->
            val usage = fileBackend?.getUsage(uri)?.getOrNull()
            if (usage != null && usage.totalBytes > 0) {
                items += HomeStorageItem(
                    label = label,
                    uri = uri,
                    totalBytes = usage.totalBytes,
                    availableBytes = usage.availableBytes,
                    usedPercent = usage.percentUsed,
                )
            }
        }

        // Mounted drives.
        devices.drives.value
            .filter { it.isMounted && it.mountUri != null && it.totalBytes > 0 }
            .forEach { drive ->
                items += HomeStorageItem(
                    label = drive.name,
                    uri = drive.mountUri!!,
                    totalBytes = drive.totalBytes,
                    availableBytes = drive.availableBytes,
                    usedPercent = if (drive.totalBytes > 0) {
                        (drive.totalBytes - drive.availableBytes).toDouble() / drive.totalBytes
                    } else 0.0,
                )
            }

        return items
    }
}
