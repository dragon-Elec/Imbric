package com.imbric.app.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.InsertDriveFile
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.imbric.app.aggregators.HomeAggregator
import com.imbric.app.aggregators.HomeQuickAccessItem
import com.imbric.app.aggregators.HomeRecentGroup
import com.imbric.app.aggregators.HomeStorageItem
import com.imbric.app.aggregators.HomeUiState
import com.imbric.core.models.FileEntry
import kotlinx.coroutines.flow.StateFlow
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue

/**
 * Homepage landing view ("My Computer") — rendered by [MainWindow] when the
 * active pane URI is `imbric://home`. Three sections: recent files, quick
 * access, storage. Data comes from [HomeAggregator], never from core directly.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HomePageView(
    stateFlow: StateFlow<HomeUiState>,
    onItemClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by stateFlow.collectAsState()

    BoxWithConstraints(modifier = modifier.fillMaxSize()) {
        val wide = maxWidth >= 900.dp

        if (wide) {
            Row(Modifier.fillMaxSize().padding(24.dp)) {
                Column(Modifier.weight(1f).fillMaxHeight().padding(end = 24.dp)) {
                    SectionTitle("Recent files")
                    Spacer(Modifier.height(8.dp))
                    RecentList(state.recents, onItemClick, Modifier.weight(1f))
                }
                Column(Modifier.weight(1f).fillMaxHeight()) {
                    SectionTitle("Quick access")
                    Spacer(Modifier.height(8.dp))
                    QuickAccessGrid(state.quickAccess, onItemClick)
                    Spacer(Modifier.height(24.dp))
                    SectionTitle("Storage")
                    Spacer(Modifier.height(8.dp))
                    StorageList(state.storage)
                }
            }
        } else {
            LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                item {
                    SectionTitle("Quick access")
                    Spacer(Modifier.height(8.dp))
                    QuickAccessGrid(state.quickAccess, onItemClick)
                }
                item {
                    SectionTitle("Recent files")
                    Spacer(Modifier.height(8.dp))
                }
                RecentListItems(state.recents, onItemClick)
                item {
                    SectionTitle("Storage")
                    Spacer(Modifier.height(8.dp))
                    StorageList(state.storage)
                }
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.onSurface,
    )
}

// --- Recent files ----------------------------------------------------------

@Composable
private fun RecentList(
    groups: List<HomeRecentGroup>,
    onItemClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        RecentListItems(groups, onItemClick)
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.RecentListItems(
    groups: List<HomeRecentGroup>,
    onItemClick: (String) -> Unit,
) {
    if (groups.isEmpty()) {
        item {
            Text(
                text = "No recent files yet",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        return
    }
    groups.forEach { group ->
        item(key = "hdr-${group.label}") {
            Text(
                text = group.label,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        items(group.items, key = { it.uri }) { entry ->
            RecentRow(entry, onItemClick)
        }
    }
}

@Composable
private fun RecentRow(entry: FileEntry, onItemClick: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                MaterialTheme.colorScheme.surfaceContainerLow,
                MaterialTheme.shapes.small,
            )
            .clickable { onItemClick(entry.uri) }
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = if (entry.isDirectory) Icons.Default.Folder else Icons.Default.InsertDriveFile,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.width(10.dp))
        Text(
            text = entry.name,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
    }
}

// --- Quick access ----------------------------------------------------------

@Composable
private fun QuickAccessGrid(items: List<HomeQuickAccessItem>, onItemClick: (String) -> Unit) {
    if (items.isEmpty()) return
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items.forEach { item ->
            QuickAccessChip(item, onItemClick)
        }
    }
}

@Composable
private fun QuickAccessChip(item: HomeQuickAccessItem, onItemClick: (String) -> Unit) {
    Row(
        modifier = Modifier
            .background(
                MaterialTheme.colorScheme.surfaceContainerLow,
                MaterialTheme.shapes.medium,
            )
            .clickable { onItemClick(item.uri) }
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = if (item.uri == "imbric://home") Icons.Default.Home else Icons.Default.Folder,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = item.label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
        )
    }
}

// --- Storage ---------------------------------------------------------------

@Composable
private fun StorageList(items: List<HomeStorageItem>) {
    if (items.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        items.forEach { item ->
            StorageRow(item)
        }
    }
}

@Composable
private fun StorageRow(item: HomeStorageItem) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = item.label,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = "${formatBytes(item.availableBytes)} free",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.height(6.dp))
        LinearProgressIndicator(
            progress = { (1f - item.usedPercent).toFloat().coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth().height(6.dp),
            color = MaterialTheme.colorScheme.primary,
            trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
        )
    }
}

private fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "0 B"
    val units = arrayOf("B", "KB", "MB", "GB", "TB")
    val digitGroups = (Math.log10(bytes.toDouble()) / Math.log10(1024.0)).toInt().coerceIn(0, units.size - 1)
    return String.format("%.1f %s", bytes / Math.pow(1024.0, digitGroups.toDouble()), units[digitGroups])
}
