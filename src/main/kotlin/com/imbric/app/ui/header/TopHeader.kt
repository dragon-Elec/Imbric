package com.imbric.app.ui.header

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ViewList
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.unit.dp
import com.imbric.app.ui.LayoutMode

/**
 * Main application header bar.
 * Houses folder navigation, breadcrumb address bar, layout toggling, and global window menus.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TopHeader(
    isHome: Boolean,
    canGoUp: Boolean,
    onGoUp: () -> Unit,
    uri: String,
    virtualUri: String,
    onNavigate: (String) -> Unit,
    onAddressBarPositioned: (Rect) -> Unit,
    layoutMode: LayoutMode,
    onToggleLayout: () -> Unit,
    onGoHome: () -> Unit,
    forceShowAnimation: Boolean,
    onToggleAnimation: () -> Unit,
    modifier: Modifier = Modifier
) {
    TopAppBar(
        modifier = modifier.height(42.dp),
        windowInsets = WindowInsets(0.dp),
        title = {
            if (isHome) {
                Text(
                    text = "Home",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onSurface
                )
            } else {
                AddressBar(
                    uri = uri,
                    virtualUri = virtualUri,
                    modifier = Modifier
                        .fillMaxWidth()
                        .onGloballyPositioned { coordinates ->
                            onAddressBarPositioned(coordinates.boundsInWindow())
                        },
                    onSegmentClick = onNavigate
                )
            }
        },
        navigationIcon = {
            if (!isHome && canGoUp) {
                IconButton(
                    onClick = onGoUp,
                    enabled = canGoUp
                ) {
                    Icon(
                        imageVector = Icons.Default.ArrowUpward,
                        contentDescription = "Go Up"
                    )
                }
            }
        },
        actions = {
            if (!isHome) {
                IconButton(onClick = onToggleLayout) {
                    Icon(
                        imageVector = if (layoutMode == LayoutMode.GRID) Icons.AutoMirrored.Filled.ViewList else Icons.Default.GridView,
                        contentDescription = "Toggle Layout",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            HeaderMenu(
                onGoHome = onGoHome,
                forceShowAnimation = forceShowAnimation,
                onToggleAnimation = onToggleAnimation
            )
        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.surface,
            titleContentColor = MaterialTheme.colorScheme.onSurface,
        )
    )
}
