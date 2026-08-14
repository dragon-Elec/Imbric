package com.imbric.app.ui.header

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.unit.dp

/**
 * Top header dropdown menu containing window-level actions (Home, Settings, animation toggles).
 */
@Composable
fun HeaderMenu(
    onGoHome: () -> Unit,
    forceShowAnimation: Boolean,
    onToggleAnimation: () -> Unit,
    modifier: Modifier = Modifier
) {
    var isMenuExpanded by remember { mutableStateOf(false) }

    Box(modifier = modifier) {
        IconButton(onClick = { isMenuExpanded = !isMenuExpanded }) {
            Icon(
                imageVector = Icons.Default.MoreVert,
                contentDescription = "Menu",
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        DropdownMenu(
            expanded = isMenuExpanded,
            onDismissRequest = { isMenuExpanded = false }
        ) {
            DropdownMenuItem(
                text = {
                    Text(
                        text = "Go to Home",
                        style = MaterialTheme.typography.bodyMedium
                    )
                },
                leadingIcon = {
                    Icon(
                        imageVector = Icons.Default.Home,
                        contentDescription = "Home",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                },
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                modifier = Modifier.heightIn(min = 32.dp),
                onClick = {
                    isMenuExpanded = false
                    onGoHome()
                }
            )
            DropdownMenuItem(
                text = {
                    Text(
                        text = "Wipe Animation",
                        style = MaterialTheme.typography.bodyMedium
                    )
                },
                leadingIcon = {
                    Text(
                        text = "🪄",
                        style = MaterialTheme.typography.bodyMedium
                    )
                },
                trailingIcon = {
                    Switch(
                        checked = forceShowAnimation,
                        onCheckedChange = null,
                        modifier = Modifier.scale(0.75f)
                    )
                },
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                modifier = Modifier.heightIn(min = 32.dp),
                onClick = {
                    onToggleAnimation()
                }
            )
        }
    }
}
