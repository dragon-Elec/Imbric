package com.imbric.app.bootstrap

import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.imbric.app.ui.AddressBar
import com.imbric.app.ui.DirectoryView
import com.imbric.app.ui.LayoutMode
import com.imbric.app.viewmodel.FileBrowserViewModel
import com.imbric.app.viewmodel.FileBrowserState
import com.imbric.core.ifs.backends.PipelineTimer
import com.imbric.core.ifs.provider.DirStateRegistry
import com.imbric.core.models.FileEntry
import com.imbric.core.models.*

/**
 * Root composable for Imbric.
 * Single-column layout: address bar + file list. No sidebar yet.
 *
 * Theme is applied at the [Main] level via [ImbricTheme], so all Material 3
 * components here automatically inherit the correct color scheme, typography,
 * and shapes — no manual decoration needed.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImbricApp(registry: DirStateRegistry) {
    val scope = rememberCoroutineScope()
    val initialUri = "file:///home/ray/Pictures/empty folder"
    val viewModel = remember { FileBrowserViewModel(registry, initialUri, scope) }

    val state = viewModel.state.collectAsState()
    val layoutMode by viewModel.layoutMode.collectAsState()
    val sortKey by viewModel.sortKey.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    AddressBar(
                        uri = state.value.uri,
                        layoutMode = layoutMode,
                        onToggleLayoutMode = { viewModel.toggleLayoutMode() },
                        modifier = Modifier.fillMaxWidth().padding(end = 16.dp),
                        onSegmentClick = { uri -> viewModel.navigateTo(uri) }
                    )
                },
                navigationIcon = {
                    IconButton(
                        onClick = { viewModel.goUp() },
                        enabled = state.value.canGoUp
                    ) {
                        Icon(
                            imageVector = Icons.Default.ArrowUpward,
                            contentDescription = "Go Up"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    titleContentColor = MaterialTheme.colorScheme.onSurface,
                )
            )
        }
    ) { innerPadding ->
        FileBrowserContent(
            state = state.value,
            layoutMode = layoutMode,
            sortKey = sortKey,
            pipelineTimer = viewModel.pipelineTimer,
            onReportDone = { viewModel.pipelineTimer = null },
            onItemClick = { item ->
                if (item.isDirectory) {
                    val timer = PipelineTimer("navigateTo")
                    timer.mark("ui_click", detail = item.uri)
                    viewModel.pipelineTimer = timer
                    viewModel.navigateTo(item.uri)
                }
            },
            onVisibleItemsChanged = { visibleUris ->
                viewModel.enrichVisibleItems(visibleUris)
            },
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        )
    }
}

@Composable
private fun FileBrowserContent(
    state: FileBrowserState,
    layoutMode: LayoutMode,
    sortKey: SortKey,
    pipelineTimer: PipelineTimer?,
    onReportDone: () -> Unit,
    onItemClick: (FileEntry) -> Unit,
    onVisibleItemsChanged: ((List<String>) -> Unit)? = null,
    modifier: Modifier = Modifier
) {
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

    // Smart loading indicator: only shows after 150ms delay (represents a hang, not progress)
    // If items arrive within 150ms, no indicator is shown — items appear instantly
    var showLoading by remember { mutableStateOf(false) }
    LaunchedEffect(state.uri) {
        showLoading = false
        kotlinx.coroutines.delay(150)
        if (sortedItems.isEmpty() && state.isLoading) {
            showLoading = true
        }
    }

    // If items arrive after indicator was shown, hide it
    LaunchedEffect(sortedItems.size) {
        if (sortedItems.isNotEmpty()) {
            showLoading = false
        }
    }

    Box(modifier = modifier) {
        // Directory content — always visible, no animation delay
        if (sortedItems.isEmpty() && !state.isLoading) {
            EmptyFolderView(state.uri)
        } else if (sortedItems.isNotEmpty()) {
            // key(state.uri) forces Compose to recreate DirectoryView when directory changes,
            // which resets the scroll position to top
            key(state.uri) {
                DirectoryView(
                    items = sortedItems,
                    layoutMode = layoutMode,
                    onItemClick = onItemClick,
                    onVisibleItemsChanged = onVisibleItemsChanged
                )
            }
        }

        // Loading indicator — fades in only after 150ms of no data
        AnimatedVisibility(
            visible = showLoading && state.isLoading,
            enter = fadeIn(animationSpec = tween(200)),
            exit = fadeOut(animationSpec = tween(150))
        ) {
            LoadingView()
        }
    }
}

@Composable
private fun LoadingView() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        CircularProgressIndicator()
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
                modifier = Modifier.size(80.dp),
                tint = MaterialTheme.colorScheme.tertiary
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Hot Reload is blazing fast! ⚡ (v4)",
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.tertiary
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Empty Folder: $uri",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
