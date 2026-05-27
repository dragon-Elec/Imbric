package com.imbric.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.ViewList
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.imbric.core.ifs.IfsUri

@Composable
fun AddressBar(
    uri: String, 
    layoutMode: LayoutMode,
    onToggleLayoutMode: () -> Unit,
    modifier: Modifier = Modifier,
    onSegmentClick: (String) -> Unit = {}
) {
    val ifsUri = remember(uri) { IfsUri(uri) }
    val segments = remember(ifsUri) { 
        val result = mutableListOf<Pair<String, String>>()
        var current = ifsUri
        while (true) {
            result.add(0, (if (current.isRootUri()) "Root" else current.name) to current.uriString)
            if (current.isRootUri()) break
            current = current.parent
        }
        result
    }

    Surface(
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 8.dp, vertical = 4.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Default.Folder,
                contentDescription = "Current Folder",
                modifier = Modifier.size(18.dp).padding(start = 4.dp),
                tint = MaterialTheme.colorScheme.primary
            )
            
            Spacer(modifier = Modifier.width(8.dp))

            Row(
                modifier = Modifier.weight(1f),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Show only last few segments if too many
                val visibleSegments = if (segments.size > 4) {
                    segments.takeLast(4)
                } else {
                    segments
                }

                visibleSegments.forEachIndexed { index, (name, segmentUri) ->
                    val isLast = index == visibleSegments.size - 1
                    
                    if (index > 0) {
                        Icon(
                            imageVector = Icons.Default.ChevronRight,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.outlineVariant
                        )
                    }
                    
                    Text(
                        text = name,
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .clickable { onSegmentClick(segmentUri) }
                            .padding(horizontal = 6.dp, vertical = 2.dp),
                        style = if (isLast) 
                            MaterialTheme.typography.titleSmall 
                        else 
                            MaterialTheme.typography.bodyMedium,
                        color = if (isLast) 
                            MaterialTheme.colorScheme.onSurface 
                        else 
                            MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1
                    )
                }
            }

            IconButton(
                onClick = onToggleLayoutMode,
                modifier = Modifier.padding(end = 4.dp).size(32.dp)
            ) {
                Icon(
                    imageVector = if (layoutMode == LayoutMode.LIST) Icons.Default.GridView else Icons.Default.ViewList,
                    contentDescription = if (layoutMode == LayoutMode.LIST) "Switch to Grid View" else "Switch to List View",
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp)
                )
            }
        }
    }
}
