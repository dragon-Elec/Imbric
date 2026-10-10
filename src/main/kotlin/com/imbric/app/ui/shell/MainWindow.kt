package com.imbric.app.ui.shell

import androidx.compose.animation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
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
import com.imbric.app.ui.header.TopHeader
import com.imbric.app.ui.LayoutMode
import com.imbric.app.ui.home.HomePageView
import com.imbric.app.ui.pane.FileBrowserPane
import com.imbric.app.ui.theme.ThemeController
import com.imbric.app.ui.theme.ThemeSettingsPanel
import com.imbric.app.viewmodel.ShellViewModel
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid
import com.imbric.core.ifs.backends.gio.support.PipelineTimer
import com.imbric.app.aggregators.HomeUiState
import kotlinx.coroutines.flow.StateFlow

@OptIn(ExperimentalMaterial3Api::class, ExperimentalUuidApi::class)
@Composable
fun MainWindow(
    shellViewModel: ShellViewModel,
    sidebarSections: List<SidebarSection>,
    homeState: StateFlow<HomeUiState>,
) {
    val tabs by shellViewModel.tabs.collectAsState()
    val activePaneId by shellViewModel.activePaneId.collectAsState()

    val stateHolder = rememberSaveableStateHolder()

    // SaveableStateHolderImpl only ever drops a registry through removeState(key) —
    // nothing prunes it when a pane goes away. Without this, every tab UUID ever
    // routed through SaveableStateProvider below retains its SaveableStateRegistry
    // (scroll position, lazy-list keys, …) for the lifetime of the window.
    // We track which pane ids have been routed so a closed pane's key can be removed.
    val seenPaneIds = remember { mutableSetOf<Uuid>() }
    LaunchedEffect(tabs, activePaneId) {
        val live = tabs.map { it.id }.toSet()
        val stale = seenPaneIds - live
        seenPaneIds.clear()
        seenPaneIds.addAll(live)
        stale.forEach { id ->
            if (id != activePaneId) stateHolder.removeState(id)
        }
    }

    val activePane = tabs.find { it.id == activePaneId } ?: return
    val focusManager = LocalFocusManager.current

    CompositionLocalProvider(LocalActivePane provides activePane) {
        val isHome = activePane.isHome
        val viewModel = activePane.viewModel

        // Folder-pane state is only collected when this pane actually is a folder.
        val state = if (isHome) null else viewModel!!.state.collectAsState()
        val layoutMode = if (isHome) null else viewModel!!.layoutMode.collectAsState()

        var forceShowAnimation by remember { mutableStateOf(false) }
        var addressBarBounds by remember { mutableStateOf<Rect?>(null) }

        // The pointerInput block below is keyed on Unit, so it captures whatever is in
        // scope when it is created and never restarts. Reading addressBarBounds directly
        // there would freeze the Rect at creation time. rememberUpdatedState gives the
        // block a stable State handle whose .value always yields the current bounds, so
        // click-outside-to-clear-focus works on every event instead of only the first.
        val currentAddressBarBounds = rememberUpdatedState(addressBarBounds)

        GlobalShortcutHandler(
            shellViewModel = shellViewModel,
            tabs = tabs,
            activePaneId = activePaneId
        ) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(Unit) {
                        awaitPointerEventScope {
                            while (true) {
                                val event = awaitPointerEvent(PointerEventPass.Initial)
                                if (event.type == PointerEventType.Press) {
                                    val pressPosition = event.changes.first().position
                                    val bounds = currentAddressBarBounds.value
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
                    activeUri = state?.value?.uri ?: "",
                    onItemClick = { uri ->
                        if (isHome) shellViewModel.openFolder(uri) else viewModel!!.navigateTo(uri)
                    }
                )

                Scaffold(
                    modifier = Modifier.weight(1f),
                    topBar = {
                        TopHeader(
                            isHome = isHome,
                            canGoUp = !isHome && state!!.value.canGoUp,
                            onGoUp = { viewModel!!.goUp() },
                            uri = state?.value?.uri ?: "",
                            virtualUri = state?.value?.virtualUri ?: "",
                            onNavigate = { uri -> viewModel!!.navigateTo(uri) },
                            // Guard the write: onGloballyPositioned fires on every layout
                            // pass, and assigning an equal Rect still schedules recomposition.
                            onAddressBarPositioned = { bounds ->
                                if (addressBarBounds != bounds) addressBarBounds = bounds
                            },
                            layoutMode = layoutMode?.value ?: LayoutMode.GRID,
                            onToggleLayout = { viewModel!!.toggleLayoutMode() },
                            onGoHome = { shellViewModel.openHome() },
                            forceShowAnimation = forceShowAnimation,
                            onToggleAnimation = { forceShowAnimation = !forceShowAnimation }
                        )
                    }
                ) { innerPadding ->
                    stateHolder.SaveableStateProvider(activePane.id) {
                        if (isHome) {
                            HomePageView(
                                stateFlow = homeState,
                                onItemClick = { uri -> shellViewModel.openFolder(uri) },
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(innerPadding)
                            )
                        } else {
                            val activeVm = viewModel!!
                            val activeState = state!!.value
                            FileBrowserPane(
                                state = activeState,
                                layoutMode = layoutMode!!.value,
                                forceShowAnimation = forceShowAnimation,
                                pipelineTimer = activeVm.pipelineTimer,
                                onReportDone = { activeVm.pipelineTimer = null },
                                onItemClick = { item ->
                                    if (item.isDirectory) {
                                        val timer = PipelineTimer("navigateTo")
                                        timer.mark("ui_click", detail = item.uri)
                                        activeVm.pipelineTimer = timer
                                        activeVm.navigateTo(item.uri)
                                    }
                                },
                                onVisibleItemsChanged = { visibleUris ->
                                    activeVm.enrichVisibleItems(visibleUris)
                                },
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(innerPadding)
                            )
                        }
                    }
                }

                // Right-Side Inspector Drawer for Live Theme Tweaking
                val isThemePanelOpen by ThemeController.isPanelOpen.collectAsState()
                AnimatedVisibility(
                    visible = isThemePanelOpen,
                    enter = slideInHorizontally(initialOffsetX = { it }) + fadeIn(),
                    exit = slideOutHorizontally(targetOffsetX = { it }) + fadeOut()
                ) {
                    Row(modifier = Modifier.fillMaxHeight()) {
                        VerticalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f))
                        ThemeSettingsPanel(
                            onClose = { ThemeController.setPanelOpen(false) }
                        )
                    }
                }
            }
        }
    }
}
