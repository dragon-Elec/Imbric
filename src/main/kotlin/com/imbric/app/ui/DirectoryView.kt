package com.imbric.app.ui

import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.imbric.app.NavTimer
import com.imbric.core.models.FileInfo
import kotlin.math.max

enum class LayoutMode {
    LIST, GRID
}

@Composable
fun DirectoryView(
    items: List<FileInfo>,
    layoutMode: LayoutMode,
    onItemClick: (FileInfo) -> Unit,
    modifier: Modifier = Modifier
) {
    when (layoutMode) {
        LayoutMode.LIST -> FileList(items = items, onItemClick = onItemClick, modifier = modifier)
        LayoutMode.GRID -> FileGrid(items = items, onItemClick = onItemClick, modifier = modifier)
    }
}

/**
 * Maps a FileInfo object to an appropriate Material Design icon based on its MIME type.
 */
fun getIconForFile(item: FileInfo): ImageVector {
    if (item.isDirectory) return Icons.Default.Folder
    if (item.isArchive) return Icons.Default.Archive

    val mime = item.mimeType.lowercase()
    return when {
        mime.startsWith("image/") -> Icons.Default.Image
        mime.startsWith("video/") -> Icons.Default.Movie
        mime.startsWith("audio/") -> Icons.Default.Audiotrack
        mime.startsWith("text/html") || mime.startsWith("text/xml") || mime.startsWith("application/json") -> Icons.Default.Code
        mime.startsWith("text/") -> Icons.Default.Description
        mime == "application/pdf" -> Icons.Default.PictureAsPdf
        item.isLaunchable -> Icons.Default.Terminal
        else -> Icons.Default.FilePresent // Fallback generic file icon
    }
}

@Composable
fun FileList(
    items: List<FileInfo>,
    onItemClick: (FileInfo) -> Unit,
    modifier: Modifier = Modifier
) {
    NavTimer.record("list_render")
    val state = rememberLazyListState()
    Box(modifier = modifier.fillMaxSize()) {
        LazyColumn(
            state = state,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            items(
                items = items, 
                key = { it.uri },
                contentType = { if (it.isDirectory) "folder" else "file" }
            ) { item ->
                FileRow(
                    item = item, 
                    onClick = { onItemClick(item) }
                )
            }
        }

        VerticalScrollbar(
            adapter = rememberScrollbarAdapter(state),
            modifier = Modifier.align(Alignment.CenterEnd).fillMaxHeight().width(12.dp),
            style = ScrollbarStyle(
                minimalHeight = 16.dp,
                thickness = 8.dp,
                shape = RoundedCornerShape(4.dp),
                hoverDurationMillis = 300,
                unhoverColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f),
                hoverColor = MaterialTheme.colorScheme.outline
            )
        )
    }
}

@Composable
fun FileGrid(
    items: List<FileInfo>,
    onItemClick: (FileInfo) -> Unit,
    modifier: Modifier = Modifier
) {
    NavTimer.record("grid_render")
    val state = rememberLazyGridState()

    // Pre-calculate column count from available width for justified layout
    // This avoids GridCells.Adaptive's per-recomposition column width calculation
    val density = LocalDensity.current
    BoxWithConstraints(modifier = modifier.fillMaxSize()) {
        val columns = max(1, (maxWidth / 120.dp).toInt())
        val cellWidth = maxWidth / columns

        LazyVerticalGrid(
            columns = GridCells.Fixed(columns),
            state = state,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(
                items = items,
                key = { it.uri },
                contentType = { if (it.isDirectory) "folder" else "file" }
            ) { item ->
                FileGridCell(
                    item = item,
                    onClick = { onItemClick(item) }
                )
            }
        }

        VerticalScrollbar(
            adapter = rememberScrollbarAdapter(state),
            modifier = Modifier.align(Alignment.CenterEnd).fillMaxHeight().width(12.dp),
            style = ScrollbarStyle(
                minimalHeight = 16.dp,
                thickness = 8.dp,
                shape = RoundedCornerShape(4.dp),
                hoverDurationMillis = 300,
                unhoverColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f),
                hoverColor = MaterialTheme.colorScheme.outline
            )
        )
    }
}

@Composable
fun FileRow(
    item: FileInfo, 
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val interactionSource = remember { MutableInteractionSource() }
    val isHovered by interactionSource.collectIsHoveredAsState()

    Box(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(if (isHovered) MaterialTheme.colorScheme.surfaceVariant else Color.Transparent)
            .clickable(
                interactionSource = interactionSource,
                indication = LocalIndication.current,
                onClick = onClick
            )
    ) {
        ListItem(
            headlineContent = {
                Text(
                    text = item.name,
                    style = MaterialTheme.typography.bodyLarge
                )
            },
            supportingContent = if (!item.isDirectory) {
                {
                    Text(
                        text = item.humanReadableSize,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            } else null,
            leadingContent = {
                val icon = getIconForFile(item)
                Icon(
                    imageVector = icon,
                    contentDescription = item.mimeType,
                    modifier = Modifier.size(28.dp),
                    tint = if (item.isDirectory) 
                        MaterialTheme.colorScheme.primary 
                    else 
                        MaterialTheme.colorScheme.outline
                )
            },
            colors = ListItemDefaults.colors(
                containerColor = Color.Transparent
            )
        )
    }
}

@Composable
fun FileGridCell(
    item: FileInfo,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val interactionSource = remember { MutableInteractionSource() }
    val isHovered by interactionSource.collectIsHoveredAsState()

    Box(
        modifier = modifier
            .height(130.dp)
            .padding(4.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (isHovered) MaterialTheme.colorScheme.surfaceVariant else Color.Transparent)
            .clickable(
                interactionSource = interactionSource,
                indication = LocalIndication.current,
                onClick = onClick
            )
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .fillMaxSize()
                .padding(top = 16.dp, start = 8.dp, end = 8.dp, bottom = 8.dp)
        ) {
            Icon(
                imageVector = getIconForFile(item),
                contentDescription = item.mimeType,
                modifier = Modifier.size(48.dp)
                    .padding(bottom = 8.dp),
                tint = if (item.isDirectory)
                    MaterialTheme.colorScheme.primary
                else
                    MaterialTheme.colorScheme.outline
            )

            Text(
                text = item.name,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                color = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

