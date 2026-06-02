package com.imbric.app.ui.shell

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.imbric.app.viewmodel.PaneContext
import com.imbric.core.ifs.IfsUri
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

@OptIn(ExperimentalUuidApi::class)
@Composable
fun TabBarView(
    tabs: List<PaneContext>,
    activePaneId: Uuid?,
    onTabSelected: (Uuid) -> Unit,
    onTabClosed: (Uuid) -> Unit,
    onNewTab: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        modifier = modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            ScrollableTabRow(
                selectedTabIndex = tabs.indexOfFirst { it.id == activePaneId }.coerceAtLeast(0),
                edgePadding = 0.dp,
                containerColor = MaterialTheme.colorScheme.surface,
                divider = {}, // Remove default bottom divider
                indicator = {}, // Remove default bottom indicator
                modifier = Modifier.weight(1f)
            ) {
                tabs.forEach { pane ->
                    val isSelected = pane.id == activePaneId
                    TabItem(
                        pane = pane,
                        isSelected = isSelected,
                        onClick = { onTabSelected(pane.id) },
                        onClose = { onTabClosed(pane.id) }
                    )
                }
            }

            Spacer(modifier = Modifier.width(8.dp))

            IconButton(
                onClick = onNewTab,
                modifier = Modifier.size(32.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Add,
                    contentDescription = "New Tab",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@OptIn(ExperimentalUuidApi::class)
@Composable
private fun TabItem(
    pane: PaneContext,
    isSelected: Boolean,
    onClick: () -> Unit,
    onClose: () -> Unit
) {
    // Collect the URI from the pane's view model to show the folder name
    val state by pane.viewModel.state.collectAsState()
    val folderName = IfsUri(state.uri).name.ifEmpty { "Root" }

    val backgroundColor = if (isSelected) {
        MaterialTheme.colorScheme.surfaceContainerHigh
    } else {
        MaterialTheme.colorScheme.surface
    }

    val contentColor = if (isSelected) {
        MaterialTheme.colorScheme.onSurface
    } else {
        MaterialTheme.colorScheme.onSurfaceVariant
    }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .padding(horizontal = 4.dp)
            .height(36.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(backgroundColor)
            .clickable(onClick = onClick)
            .padding(start = 12.dp, end = 4.dp)
    ) {
        Text(
            text = folderName,
            style = MaterialTheme.typography.labelLarge,
            color = contentColor,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 120.dp)
        )
        
        Spacer(modifier = Modifier.width(4.dp))
        
        IconButton(
            onClick = onClose,
            modifier = Modifier.size(24.dp)
        ) {
            Icon(
                imageVector = Icons.Default.Close,
                contentDescription = "Close Tab",
                modifier = Modifier.size(14.dp),
                tint = contentColor.copy(alpha = 0.7f)
            )
        }
    }
}