package com.imbric.app.ui.pane

import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.imbric.app.ui.DirectoryView
import com.imbric.app.ui.components.animations.WipeReveal
import com.imbric.app.ui.components.animations.edgePulse
import com.imbric.app.ui.LayoutMode
import com.imbric.app.viewmodel.FileBrowserState
import com.imbric.core.ifs.backends.gio.support.PipelineTimer
import com.imbric.core.models.FileEntry

@Composable
fun FileBrowserPane(
    state: FileBrowserState,
    layoutMode: LayoutMode,
    forceShowAnimation: Boolean,
    pipelineTimer: PipelineTimer?,
    onReportDone: () -> Unit,
    onItemClick: (FileEntry) -> Unit,
    onVisibleItemsChanged: ((List<String>) -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    // DirState emits `items` already sorted for the active SortKey, so the pane
    // consumes them as-is — no main-thread re-sort.
    LaunchedEffect(state.isLoading, state.items) {
        if (pipelineTimer != null && !state.isLoading) {
            pipelineTimer.mark("ui_rendered", state.items.size)
            pipelineTimer.report()
            onReportDone()
        }
    }

    // Snapshot the pane content as a single value. AnimatedContent's outgoing
    // composition must animate out the PREVIOUS snapshot — if the content lambda
    // read live outer state instead, the outgoing pane would re-render the
    // incoming folder's files mid-crossfade. The revision travels with the
    // snapshot for the same reason: reading the live counter here would make the
    // outgoing pane pulse on the INCOMING folder's emissions.
    val content = PaneContent(state.uri, state.items, state.isLoading, state.itemsRevision)

    WipeReveal(
        isLoading = forceShowAnimation || (state.isLoading && state.items.isEmpty()),
        delayMillis = if (forceShowAnimation) 0L else 500L,
        modifier = modifier.fillMaxSize()
    ) {
        AnimatedContent(
            targetState = content,
            transitionSpec = {
                // A subtle, professional crossfade with a very slight scale (98%) to register the navigation
                (fadeIn(animationSpec = tween(150)) + scaleIn(initialScale = 0.98f, animationSpec = tween(150))) togetherWith
                (fadeOut(animationSpec = tween(150)) + scaleOut(targetScale = 0.98f, animationSpec = tween(150)))
            },
            label = "DirectoryTransition"
        ) { snapshot ->
            // Directory content
            if (snapshot.items.isEmpty() && !snapshot.isLoading) {
                EmptyFolderView(snapshot.uri)
            } else if (snapshot.items.isNotEmpty()) {
                // key(uri) forces Compose to recreate DirectoryView when directory changes,
                // which resets the scroll position to top
                key(snapshot.uri) {
                    Box(
                        modifier = Modifier.edgePulse(
                            trigger = snapshot.revision,
                            resetKey = snapshot.uri,
                            color = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        DirectoryView(
                            items = snapshot.items,
                            layoutMode = layoutMode,
                            onItemClick = onItemClick,
                            onVisibleItemsChanged = onVisibleItemsChanged,
                            modifier = Modifier.fillMaxSize()
                        )
                    }
                }
            }
        }
    }
}

/**
 * Immutable snapshot of what a pane displays. Used as [AnimatedContent] targetState
 * so the outgoing crossfade keeps rendering the folder the user navigated away from
 * instead of the incoming one (stale-capture fix).
 */
private data class PaneContent(
    val uri: String,
    val items: List<FileEntry>,
    val isLoading: Boolean,
    /** Content-revision counter captured with this snapshot; drives [edgePulse]. */
    val revision: Int
)

@Composable
private fun EmptyFolderView(uri: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                imageVector = Icons.Default.FolderOpen,
                contentDescription = null,
                modifier = Modifier.size(64.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Folder is empty",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = uri,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}
