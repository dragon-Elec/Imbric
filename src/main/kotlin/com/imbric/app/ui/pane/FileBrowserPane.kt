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
import com.imbric.core.ifs.directories.IdleCpuSampler
import com.imbric.core.models.FileEntry
import kotlinx.coroutines.delay

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

    // Telemetry tail: DirState's idle-CPU sampler appends its first marks ~2.5s and ~7.5s
    // after the load finishes — long after the report above already fired (and onReportDone
    // nulled the VM's timer). Second report so idle CPU actually prints instead of only
    // existing on the detached timer object. Keyed on content, not on the timer param:
    // the param is already null by the second recomposition.
    LaunchedEffect(state.uri, state.itemsRevision) {
        val timer = pipelineTimer ?: return@LaunchedEffect
        if (state.isLoading) return@LaunchedEffect
        delay(IdleCpuSampler.IDLE_SETTLE_MS + IdleCpuSampler.SAMPLE_INTERVAL_MS + 1_000L)
        if (!state.isLoading) timer.report()
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
                if (initialState.uri == targetState.uri) {
                    // Same folder — an enrichment flush, a re-sort, or a
                    // load completing: the items changed but the folder did
                    // not. Swap instantly; a crossfade here would flash the
                    // whole pane on every emission.
                    ContentTransform(EnterTransition.None, ExitTransition.None, sizeTransform = null)
                } else {
                    // Navigation: a subtle, professional crossfade with a
                    // very slight scale (98%) to register the folder switch.
                    (fadeIn(animationSpec = tween(150)) + scaleIn(initialScale = 0.98f, animationSpec = tween(150))) togetherWith
                    (fadeOut(animationSpec = tween(150)) + scaleOut(targetScale = 0.98f, animationSpec = tween(150)))
                }
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
 *
 * Identity has two jobs, and they must not be conflated:
 * - [equals] MUST return false on every emission (hence `revision` is part of it).
 *   AnimatedContent's Transition only adopts a new targetState when equals is
 *   false — a narrower equals freezes the Transition on the first snapshot and
 *   enrichment/re-sorts never re-render (the bug fa82334 introduced).
 * - The crossfade itself is gated in [transitionSpec] on `initialState.uri ==
 *   targetState.uri`, NOT on equals: same-folder changes swap instantly via a
 *   no-op ContentTransform, so only navigation plays the 150ms crossfade.
 * [revision] rides along so the edgePulse trigger stays snapshot-scoped — the
 * outgoing pane pulses on ITS OWN folder's emissions, not the incoming ones.
 */
private class PaneContent(
    val uri: String,
    val items: List<FileEntry>,
    val isLoading: Boolean,
    /** Content-revision counter captured with this snapshot; drives [edgePulse]. */
    val revision: Int
) {
    /** True when this snapshot carries list content (the spinner/empty↔filled flip). */
    private val hasContent: Boolean get() = items.isNotEmpty()

    override fun equals(other: Any?): Boolean = other is PaneContent &&
        uri == other.uri &&
        isLoading == other.isLoading &&
        hasContent == other.hasContent &&
        // revision MUST be part of identity: AnimatedContent only learns
        // about a new targetState when equals returns false. Excluding it
        // (the old behaviour) froze the Transition on the first snapshot,
        // so enrichment flushes and re-sorts never re-rendered.
        revision == other.revision

    override fun hashCode(): Int =
        ((uri.hashCode() * 31 + isLoading.hashCode()) * 31 + hasContent.hashCode()) * 31 + revision
}

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
