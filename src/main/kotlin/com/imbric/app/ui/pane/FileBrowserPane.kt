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
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.unit.dp
import com.imbric.app.ui.DirectoryView
import com.imbric.app.ui.components.animations.WipeReveal
import com.imbric.app.ui.components.animations.edgePulse
import com.imbric.app.ui.LayoutMode
import com.imbric.app.viewmodel.FileBrowserState
import com.imbric.core.ifs.backends.PipelineTimer
import com.imbric.core.models.FileEntry
import com.imbric.core.models.SortKey

@Composable
fun FileBrowserPane(
    state: FileBrowserState,
    layoutMode: LayoutMode,
    sortKey: SortKey,
    forceShowAnimation: Boolean,
    pipelineTimer: PipelineTimer?,
    onReportDone: () -> Unit,
    onItemClick: (FileEntry) -> Unit,
    onVisibleItemsChanged: ((List<String>) -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val focusManager = LocalFocusManager.current

    // Sort items reactively when either items or sortKey changes
    val sortedItems = remember(state.items, sortKey) {
        val comparator = FileEntry.comparatorFor(sortKey)
        state.items.sortedWith(comparator)
    }

    LaunchedEffect(state.isLoading, sortedItems) {
        if (pipelineTimer != null && !state.isLoading) {
            pipelineTimer.mark("ui_rendered", sortedItems.size)
            pipelineTimer.report()
            onReportDone()
        }
    }

    WipeReveal(
        isLoading = forceShowAnimation || (state.isLoading && sortedItems.isEmpty()),
        delayMillis = if (forceShowAnimation) 0L else 500L,
        modifier = modifier
            .fillMaxSize()
            .pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        val event = awaitPointerEvent(PointerEventPass.Initial)
                        if (event.type == PointerEventType.Press) {
                            focusManager.clearFocus()
                        }
                    }
                }
            }
    ) {
        AnimatedContent(
            targetState = state.uri,
            transitionSpec = {
                // A subtle, professional crossfade with a very slight scale (98%) to register the navigation
                (fadeIn(animationSpec = tween(150)) + scaleIn(initialScale = 0.98f, animationSpec = tween(150))) togetherWith
                (fadeOut(animationSpec = tween(150)) + scaleOut(targetScale = 0.98f, animationSpec = tween(150)))
            },
            label = "DirectoryTransition"
        ) { targetUri ->
            // Directory content
            if (sortedItems.isEmpty() && !state.isLoading) {
                EmptyFolderView(targetUri)
            } else if (sortedItems.isNotEmpty()) {
                // key(targetUri) forces Compose to recreate DirectoryView when directory changes,
                // which resets the scroll position to top
                key(targetUri) {
                    Box(
                        modifier = Modifier.edgePulse(
                            trigger = sortedItems.hashCode(),
                            resetKey = targetUri,
                            color = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        DirectoryView(
                            items = sortedItems,
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