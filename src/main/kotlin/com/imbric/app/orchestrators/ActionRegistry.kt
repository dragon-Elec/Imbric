package com.imbric.app.orchestrators

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.*
import com.imbric.app.viewmodel.ShellViewModel
import kotlin.uuid.ExperimentalUuidApi

/**
 * Defines all global actions that can be triggered via keyboard shortcuts or menus.
 */
enum class AppAction {
    NEW_TAB,
    CLOSE_TAB,
    GO_BACK,
    GO_FORWARD,
    GO_UP
}

/**
 * Maps hardware key combinations to [AppAction]s.
 */
object ShortcutConfig {
    fun getAction(event: KeyEvent): AppAction? {
        if (event.type != KeyEventType.KeyDown) return null

        val isCtrl = event.isCtrlPressed
        val isAlt = event.isAltPressed
        val isShift = event.isShiftPressed

        return when {
            isCtrl && event.key == Key.T -> AppAction.NEW_TAB
            isCtrl && event.key == Key.W -> AppAction.CLOSE_TAB
            isAlt && event.key == Key.DirectionLeft -> AppAction.GO_BACK
            isAlt && event.key == Key.DirectionRight -> AppAction.GO_FORWARD
            isAlt && event.key == Key.DirectionUp -> AppAction.GO_UP
            else -> null
        }
    }
}

/**
 * Intercepts keyboard events at the root of the application and routes them
 * to the active [PaneContext] via the [ShellViewModel].
 */
@OptIn(ExperimentalUuidApi::class)
@Composable
fun GlobalShortcutHandler(
    shellViewModel: ShellViewModel,
    content: @Composable () -> Unit
) {
    val tabs by shellViewModel.tabs.collectAsState()
    val activePaneId by shellViewModel.activePaneId.collectAsState()
    val activePane = tabs.find { it.id == activePaneId }

    Box(
        modifier = Modifier.onPreviewKeyEvent { event ->
            val action = ShortcutConfig.getAction(event) ?: return@onPreviewKeyEvent false

            when (action) {
                AppAction.NEW_TAB -> {
                    shellViewModel.addTab("file:///")
                    true
                }
                AppAction.CLOSE_TAB -> {
                    activePaneId?.let { shellViewModel.closeTab(it) }
                    true
                }
                AppAction.GO_BACK -> {
                    activePane?.viewModel?.goBack()
                    true
                }
                AppAction.GO_FORWARD -> {
                    activePane?.viewModel?.goForward()
                    true
                }
                AppAction.GO_UP -> {
                    activePane?.viewModel?.goUp()
                    true
                }
            }
        }
    ) {
        content()
    }
}