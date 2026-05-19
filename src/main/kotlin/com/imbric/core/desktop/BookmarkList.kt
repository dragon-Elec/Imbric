package com.imbric.core.desktop

import com.imbric.core.models.Bookmark
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.gnome.gio.*
import org.gnome.glib.GLib
import java.nio.file.Path

/**
 * System-wide bookmark manager.
 * Persists bookmarks to JSON (~/.config/imbric/bookmarks.json) and
 * bidirectionally syncs with the GTK bookmarks file (~/.config/gtk-3.0/bookmarks)
 * for compatibility with Nautilus, Nemo, GTK file picker, etc.
 *
 * Follows the StarredManager singleton pattern — global state without a specific URI.
 *
 * Ported from nautilus-bookmark-list.c / NautilusBookmarkList.
 */
class BookmarkList internal constructor(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob()),
    private val jsonPath: Path = Path.of(
        System.getProperty("user.home") ?: "/",
        ".config", "imbric", "bookmarks.json"
    ),
    private val gtkPath: Path = Path.of(
        System.getProperty("user.home") ?: "/",
        ".config", "gtk-3.0", "bookmarks"
    ),
    /** Whether to set up GIO file monitors. Disable for testing. */
    private val enableMonitoring: Boolean = true,
    /** Custom URI validator. Defaults to GIO-based validation. */
    private val uriValidator: (String) -> Boolean = { uri ->
        try {
            val gfile = org.gnome.gio.File.newForUri(uri)
            gfile.uri != null
        } catch (e: Exception) {
            false
        }
    }
) {
    private val _bookmarks = MutableStateFlow<List<Bookmark>>(emptyList())

    /** Observable ordered list of all bookmarks. */
    val bookmarks: StateFlow<List<Bookmark>> = _bookmarks.asStateFlow()

    private val json = Json { prettyPrint = true; ignoreUnknownKeys = true }

    private var gtkMonitor: FileMonitor? = null

    /** Flag to prevent feedback loops during sync. */
    @Volatile
    internal var syncing = false

    init {
        if (enableMonitoring) {
            Gio.`javagi$ensureInitialized`()
        }
        load()
        if (enableMonitoring) {
            setupGtkMonitor()
            setupReactiveSave()
        }
    }

    // ── Persistence ──────────────────────────────────────────────────────

    /** Load bookmarks from JSON, falling back to GTK import on first run. */
    private fun load() {
        val jsonFile = jsonPath.toFile()
        if (jsonFile.exists()) {
            try {
                val text = jsonFile.readText()
                val parsed = json.decodeFromString<List<Bookmark>>(text)
                _bookmarks.value = parsed
                return
            } catch (e: Exception) {
                if (enableMonitoring) {
                    GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                        "Failed to load bookmarks from JSON: ${e.message}")
                }
            }
        }

        // First run: import from GTK bookmarks file
        val gtkFile = gtkPath.toFile()
        if (gtkFile.exists()) {
            try {
                val imported = parseGtkBookmarks(gtkFile.readText())
                _bookmarks.value = imported
                saveJson() // Persist the import
            } catch (e: Exception) {
                if (enableMonitoring) {
                    GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                        "Failed to import GTK bookmarks: ${e.message}")
                }
            }
        }
    }

    /** Save bookmarks to JSON (called by reactive collector). */
    internal fun saveJson() {
        try {
            val file = jsonPath.toFile()
            file.parentFile?.mkdirs()
            file.writeText(json.encodeToString(_bookmarks.value))
        } catch (e: Exception) {
            if (enableMonitoring) {
                GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                    "Failed to save bookmarks to JSON: ${e.message}")
            }
        }
    }

    /** Write current bookmarks to the GTK bookmarks file. */
    internal fun writeGtkBookmarks() {
        try {
            val file = gtkPath.toFile()
            file.parentFile?.mkdirs()
            val lines = _bookmarks.value.map { b ->
                if (b.label != null && b.label != b.name) "${b.uri} ${b.label}"
                else b.uri
            }
            file.writeText(lines.joinToString("\n") + "\n")
        } catch (e: Exception) {
            if (enableMonitoring) {
                GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                    "Failed to write GTK bookmarks: ${e.message}")
            }
        }
    }

    // ── Reactive Save ────────────────────────────────────────────────────

    /** Debounced auto-save: persists JSON + GTK on any bookmark change. */
    private fun setupReactiveSave() {
        scope.launch {
            _bookmarks
                .drop(1) // Skip initial load
                .debounce(500)
                .collect {
                    if (!syncing) {
                        saveJson()
                        writeGtkBookmarks()
                    }
                }
        }
    }

    // ── GTK Sync ─────────────────────────────────────────────────────────

    /** Monitor the GTK bookmarks file for external changes. */
    private fun setupGtkMonitor() {
        try {
            val gtkFile = org.gnome.gio.File.newForPath(gtkPath.toString())
            gtkMonitor = gtkFile.monitorFile(FileMonitorFlags.NONE, null)

            gtkMonitor?.onChanged { _, _, eventType ->
                if (eventType == FileMonitorEvent.CHANGES_DONE_HINT) {
                    scope.launch {
                        delay(200) // debounce
                        importFromGtk()
                    }
                }
            }
        } catch (e: Exception) {
            GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                "Failed to monitor GTK bookmarks file: ${e.message}")
        }
    }

    /** Import bookmarks from the GTK file, merging with existing Imbric metadata. */
    internal fun importFromGtk() {
        val gtkFile = gtkPath.toFile()
        if (!gtkFile.exists()) return

        syncing = true
        try {
            val gtkBookmarks = parseGtkBookmarks(gtkFile.readText())
            val existing = _bookmarks.value.associateBy { it.uri }

            // Merge: GTK bookmarks + any Imbric-only bookmarks (with metadata)
            val merged = gtkBookmarks.map { gtk ->
                existing[gtk.uri]?.copy(name = gtk.name, label = gtk.label)
                    ?: gtk
            }

            _bookmarks.value = merged
            saveJson() // Update JSON with merged state
        } catch (e: Exception) {
            if (enableMonitoring) {
                GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                    "Failed to import GTK bookmarks: ${e.message}")
            }
        } finally {
            syncing = false
        }
    }

    // ── GTK File Parsing ─────────────────────────────────────────────────

    /**
     * Parse the GTK bookmarks file format: `URI [label]\n`
     * Each line is a bookmark. The label is optional (separated by space).
     */
    internal fun parseGtkBookmarks(text: String): List<Bookmark> {
        return text.lines()
            .filter { it.isNotBlank() }
            .map { line ->
                val parts = line.split(" ", limit = 2)
                val uri = parts[0].trim()
                val label = parts.getOrNull(1)?.trim()
                val name = label ?: uri.substringAfterLast("/").ifBlank { uri }
                Bookmark(name = name, uri = uri, label = label)
            }
    }

    // ── Public API ───────────────────────────────────────────────────────

    fun contains(uri: String): Boolean = _bookmarks.value.any { it.uri == uri }

    fun canBookmark(uri: String): Boolean = uri.isNotBlank() && !contains(uri)

    fun getBookmark(uri: String): Bookmark? = _bookmarks.value.find { it.uri == uri }

    fun getAll(): List<Bookmark> = _bookmarks.value

    /**
     * Add a bookmark. Validates the URI before insertion.
     * @param bookmark The bookmark to add
     * @param index Position to insert at (-1 = append)
     * @return true if added, false if already exists or invalid URI
     */
    fun add(bookmark: Bookmark, index: Int = -1): Boolean {
        if (!canBookmark(bookmark.uri)) return false
        if (!isValidUri(bookmark.uri)) return false

        _bookmarks.update { current ->
            if (index < 0) {
                current + bookmark
            } else {
                current.toMutableList().apply {
                    add(index.coerceAtMost(size), bookmark)
                }
            }
        }
        return true
    }

    fun remove(uri: String) {
        _bookmarks.update { it.filterNot { b -> b.uri == uri } }
    }

    fun moveItem(fromIndex: Int, toIndex: Int) {
        _bookmarks.update { current ->
            if (fromIndex !in current.indices || toIndex !in 0..current.size) return@update current
            val mutable = current.toMutableList()
            val item = mutable.removeAt(fromIndex)
            mutable.add(toIndex.coerceAtMost(mutable.size), item)
            mutable
        }
    }

    // ── URI Validation ───────────────────────────────────────────────────

    private fun isValidUri(uri: String): Boolean = uriValidator(uri)

    // ── Cleanup ──────────────────────────────────────────────────────────

    fun dispose() {
        gtkMonitor?.cancel()
        scope.cancel()
    }

    companion object {
        @Volatile
        private var instance: BookmarkList? = null

        fun getInstance(): BookmarkList {
            return instance ?: synchronized(this) {
                instance ?: BookmarkList().also { instance = it }
            }
        }

        /** For testing — reset the singleton. */
        internal fun resetInstance() {
            instance?.dispose()
            instance = null
        }
    }
}
