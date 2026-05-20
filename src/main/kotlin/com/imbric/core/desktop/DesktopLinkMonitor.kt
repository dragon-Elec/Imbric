package com.imbric.core.desktop

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.gnome.gio.*
import org.gnome.glib.GLib

/**
 * Monitors the desktop directory for link changes (additions, removals).
 * Provides a live list of desktop links for the sidebar/app layer.
 * Ported from nautilus-desktop-link-monitor.c
 */
class DesktopLinkMonitor private constructor(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    private val _links = MutableStateFlow<List<DesktopLink>>(emptyList())
    /** Observable list of all desktop links. */
    val links: StateFlow<List<DesktopLink>> = _links.asStateFlow()

    private var monitor: FileMonitor? = null
    private var refreshJob: Job? = null

    init {
        Gio.`javagi$ensureInitialized`()
        setupMonitor()
        refresh()
    }

    private fun setupMonitor() {
        try {
            val desktopDir = DesktopDirectory.getFile()
            if (desktopDir.queryExists(null)) {
                monitor = desktopDir.monitorDirectory(FileMonitorFlags.NONE, null)
                monitor?.onChanged { _, _, _ ->
                    refreshJob?.cancel()
                    refreshJob = scope.launch {
                        delay(500)
                        refresh()
                    }
                }
            }
        } catch (e: Exception) {
            GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                "Failed to setup DesktopLinkMonitor: ${e.message}")
        }
    }

    /**
     * Refreshes the list of desktop links by scanning the desktop directory.
     */
    fun refresh() {
        refreshJob?.cancel()
        refreshJob = scope.launch {
            try {
                val links = mutableListOf<DesktopLink>()
                
                // Add system links (always present)
                links.add(DesktopLink(
                    id = "computer",
                    name = "Computer",
                    uri = "file:///",
                    icon = "drive-harddisk-symbolic",
                    symbolicIcon = "drive-harddisk-symbolic",
                    linkType = DesktopLinkType.COMPUTER
                ))
                links.add(DesktopLink(
                    id = "home",
                    name = "Home",
                    uri = DesktopDirectory.getUri().removeSuffix("/Desktop"),
                    icon = "user-home-symbolic",
                    symbolicIcon = "user-home-symbolic",
                    linkType = DesktopLinkType.HOME
                ))
                links.add(DesktopLink(
                    id = "trash",
                    name = "Trash",
                    uri = "trash:///",
                    icon = "user-trash-symbolic",
                    symbolicIcon = "user-trash-symbolic",
                    linkType = DesktopLinkType.TRASH
                ))
                links.add(DesktopLink(
                    id = "network",
                    name = "Network",
                    uri = "network:///",
                    icon = "network-workgroup-symbolic",
                    symbolicIcon = "network-workgroup-symbolic",
                    linkType = DesktopLinkType.NETWORK
                ))

                // Scan desktop directory for user shortcuts
                val desktopDir = DesktopDirectory.getFile()
                if (desktopDir.queryExists(null)) {
                    try {
                        val enumerator = desktopDir.enumerateChildren(
                            "standard::name,standard::type,standard::icon",
                            FileQueryInfoFlags.NONE, null
                        )
                        try {
                            var info = enumerator.nextFile(null)
                            while (info != null) {
                                val name = info.name?.toString()
                                if (!name.isNullOrEmpty() && name.endsWith(".desktop")) {
                                    val child = desktopDir.getChild(name)
                                    links.add(DesktopLink(
                                        id = "shortcut-$name",
                                        name = name.removeSuffix(".desktop"),
                                        uri = child.uri ?: "",
                                        icon = "application-x-executable-symbolic",
                                        linkType = DesktopLinkType.SHORTCUT
                                    ))
                                }
                                info = enumerator.nextFile(null)
                                yield()
                            }
                        } finally {
                            enumerator.close(null)
                        }
                    } catch (e: Exception) {
                        // Desktop directory might not be listable
                    }
                }

                _links.value = links
            } catch (e: Exception) {
                GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING,
                    "Failed to refresh desktop links: ${e.message}")
            }
        }
    }

    companion object {
        @Volatile
        private var instance: DesktopLinkMonitor? = null

        fun getInstance(): DesktopLinkMonitor {
            return instance ?: synchronized(this) {
                instance ?: DesktopLinkMonitor().also { instance = it }
            }
        }

        fun clear() {
            synchronized(this) {
                instance?.monitor?.cancel()
                instance?.refreshJob?.cancel()
                instance = null
            }
        }
    }
}
