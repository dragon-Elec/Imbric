package com.imbric.app.ui.shell

import androidx.compose.animation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.ViewList
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerEventType
import com.imbric.app.orchestrators.GlobalShortcutHandler
import com.imbric.app.aggregators.SidebarSection
import com.imbric.app.ui.AddressBar
import com.imbric.app.ui.LayoutMode
import com.imbric.app.ui.pane.FileBrowserPane
import com.imbric.app.viewmodel.ShellViewModel
import kotlin.uuid.ExperimentalUuidApi
import com.imbric.core.ifs.backends.PipelineTimer

@OptIn(ExperimentalMaterial3Api::class, ExperimentalUuidApi::class)
@Composable
fun MainWindow(
    shellViewModel: ShellViewModel,
    sidebarSections: List<SidebarSection>
) {
    val tabs by shellViewModel.tabs.collectAsState()
    val activePaneId by shellViewModel.activePaneId.collectAsState()
    val activePane = tabs.find { it.id == activePaneId } ?: return

    val stateHolder = rememberSaveableStateHolder()
    val focusManager = LocalFocusManager.current

    CompositionLocalProvider(LocalActivePane provides activePane) {
        val viewModel = activePane.viewModel
        val state = viewModel.state.collectAsState()
        val layoutMode by viewModel.layoutMode.collectAsState()
        val sortKey by viewModel.sortKey.collectAsState()
        var forceShowAnimation by remember { mutableStateOf(false) }
        var addressBarBounds by remember { mutableStateOf<Rect?>(null) }

        GlobalShortcutHandler(shellViewModel = shellViewModel) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(Unit) {
                        awaitPointerEventScope {
                            while (true) {
                                val event = awaitPointerEvent(PointerEventPass.Initial)
                                if (event.type == PointerEventType.Press) {
                                    val pressPosition = event.changes.first().position
                                    val bounds = addressBarBounds
                                    if (bounds != null && !bounds.contains(pressPosition)) {
                                        focusManager.clearFocus()
                                    }
                                }
                            }
                        }
                    }
            ) {
                SidebarView(
                    sections = sidebarSections,
                    activeUri = state.value.uri,
                    onItemClick = { uri -> viewModel.navigateTo(uri) }
                )
                
                Scaffold(
                    modifier = Modifier.weight(1f),
                    topBar = {
                        Column {
                            TabBarView(
                                tabs = tabs,
                                activePaneId = activePaneId,
                                onTabSelected = { shellViewModel.setActiveTab(it) },
                                onTabClosed = { shellViewModel.closeTab(it) },
                                onNewTab = { shellViewModel.addTab("file:///") }
                            )
                            TopAppBar(
                                title = {
                                    AddressBar(
                                        uri = state.value.uri,
                                        virtualUri = state.value.virtualUri,
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .onGloballyPositioned { coordinates ->
                                                addressBarBounds = coordinates.boundsInWindow()
                                            },
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
                                actions = {
                                    IconButton(onClick = { forceShowAnimation = !forceShowAnimation }) {
                                        Text(
                                            text = "🪄",
                                            style = MaterialTheme.typography.bodyLarge,
                                            color = if (forceShowAnimation) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                    IconButton(onClick = { viewModel.toggleLayoutMode() }) {
                                        Icon(
                                            imageVector = if (layoutMode == LayoutMode.GRID) Icons.Default.ViewList else Icons.Default.GridView,
                                            contentDescription = "Toggle Layout",
                                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                },
                                colors = TopAppBarDefaults.topAppBarColors(
                                    containerColor = MaterialTheme.colorScheme.surface,
                                    titleContentColor = MaterialTheme.colorScheme.onSurface,
                                )
                            )
                        }
                    }
                ) { innerPadding ->
                    stateHolder.SaveableStateProvider(activePane.id) {
                        FileBrowserPane(
                            state = state.value,
                            layoutMode = layoutMode,
                            sortKey = sortKey,
                            forceShowAnimation = forceShowAnimation,
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
            }
        }
    }
}