package com.imbric.app.bootstrap

import androidx.compose.animation.*
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.ui.unit.IntOffset
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.imbric.app.NavTimer
import com.imbric.app.ui.AddressBar
import com.imbric.app.ui.DirectoryView
import com.imbric.app.ui.LayoutMode
import com.imbric.app.viewmodel.FileBrowserViewModel
import com.imbric.app.viewmodel.FileBrowserState
import com.imbric.core.ifs.provider.DirStateRegistry
import com.imbric.core.models.FileInfo

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

    val state by viewModel.state.collectAsState()
    val layoutMode by viewModel.layoutMode.collectAsState()

    // Navigation timing: track click-to-render latency
    val navTimer = remember { mutableStateOf<NavTimer?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    AddressBar(
                        uri = state.uri,
                        layoutMode = layoutMode,
                        onToggleLayoutMode = { viewModel.toggleLayoutMode() },
                        modifier = Modifier.fillMaxWidth().padding(end = 16.dp),
                        onSegmentClick = { uri -> viewModel.navigateTo(uri) }
                    )
                },
                navigationIcon = {
                    IconButton(
                        onClick = { viewModel.goUp() },
                        enabled = state.canGoUp
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
            state = state,
            layoutMode = layoutMode,
            navTimer = navTimer,
            onItemClick = { item ->
                if (item.isDirectory) {
                    // Start navigation timer for performance tracing
                    NavTimer.setRef()  // Global reference for composable render timing
                    navTimer.value = NavTimer("navigateTo").also { it.mark("click", uri = item.uri) }
                    viewModel.navigateTo(item.uri)
                }
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
    navTimer: MutableState<NavTimer?>,
    onItemClick: (FileInfo) -> Unit,
    modifier: Modifier = Modifier
) {
    // Navigation timing: log when data arrives in UI
    LaunchedEffect(state.isLoading, state.items) {
        val t = navTimer.value
        if (t != null && !state.isLoading && state.items.isNotEmpty()) {
            t.mark("data_ready", state.items.size)
            t.log("ui_rendered")
            navTimer.value = null
        }
    }
    Box(modifier = modifier) {
        AnimatedContent(
            targetState = state.uri,
            transitionSpec = {
                // M3 motion: enter = decelerate (fast start, gentle settle)
                //            exit = accelerate (slow start, quick departure)
                // Enter = 300ms, Exit = 200ms (exit is always faster)
                val enterEasing = CubicBezierEasing(0.05f, 0.7f, 0.1f, 1.0f)   // EmphasizedDecelerate
                val exitEasing = CubicBezierEasing(0.3f, 0.0f, 0.8f, 0.15f)    // EmphasizedAccelerate
                (slideInVertically(animationSpec = tween(300, easing = enterEasing)) { it / 4 } +
                    fadeIn(animationSpec = tween(300, easing = enterEasing))
                ) togetherWith
                (slideOutVertically(animationSpec = tween(200, easing = exitEasing)) { -it / 4 } +
                    fadeOut(animationSpec = tween(200, easing = exitEasing))
                )
            }
        ) { targetUri ->
            if (state.isLoading && state.items.isEmpty()) {
                LoadingView()
            } else if (state.items.isEmpty()) {
                EmptyFolderView(targetUri)
            } else {
                DirectoryView(
                    items = state.items,
                    layoutMode = layoutMode,
                    onItemClick = onItemClick
                )
            }
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
