package com.imbric.app.ui

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.ViewList
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.onPointerEvent
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.imbric.core.ifs.IfsUri

@Composable
fun AddressBar(
    uri: String, 
    virtualUri: String,
    modifier: Modifier = Modifier,
    onSegmentClick: (String) -> Unit = {}
) {
    var isEditing by remember { mutableStateOf(false) }

    Surface(
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier.clickable(
            interactionSource = remember { MutableInteractionSource() },
            indication = null,
            enabled = !isEditing
        ) { isEditing = true }
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Default.Folder,
                contentDescription = "Current Folder",
                modifier = Modifier.size(18.dp).padding(start = 4.dp),
                tint = MaterialTheme.colorScheme.primary
            )
            
            Spacer(modifier = Modifier.width(8.dp))

            Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
                if (isEditing) {
                    AddressInput(
                        uri = uri,
                        onSubmit = { newUri -> 
                            onSegmentClick(newUri)
                            isEditing = false 
                        },
                        onCancel = { isEditing = false }
                    )
                } else {
                    BreadcrumbRow(uri = uri, virtualUri = virtualUri, onSegmentClick = onSegmentClick)
                }
            }
        }
    }
}

@Composable
private fun AddressInput(
    uri: String,
    onSubmit: (String) -> Unit,
    onCancel: () -> Unit
) {
    var inputText by remember { mutableStateOf(TextFieldValue(uri, selection = TextRange(0, uri.length))) }
    val focusRequester = remember { FocusRequester() }
    var hasFocused by remember { mutableStateOf(false) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        BasicTextField(
            value = inputText,
            onValueChange = { inputText = it },
            modifier = Modifier
                .weight(1f)
                .focusRequester(focusRequester)
                .onFocusChanged { state -> 
                    if (state.isFocused) {
                        hasFocused = true
                    } else if (hasFocused) {
                        onCancel()
                    }
                }
                .onKeyEvent { event ->
                    if (event.type == KeyEventType.KeyDown) {
                        when (event.key) {
                            Key.Enter -> { onSubmit(inputText.text); true }
                            Key.Escape -> { onCancel(); true }
                            else -> false
                        }
                    } else false
                },
            textStyle = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurface),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { onSubmit(inputText.text) })
        )
        
        IconButton(
            onClick = onCancel,
            modifier = Modifier.size(24.dp)
        ) {
            Icon(
                imageVector = Icons.Default.Close,
                contentDescription = "Cancel",
                modifier = Modifier.size(16.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
    
    LaunchedEffect(Unit) { focusRequester.requestFocus() }
}

@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
private fun BreadcrumbRow(uri: String, virtualUri: String, onSegmentClick: (String) -> Unit) {
    val scrollState = rememberScrollState()
    val virtualIfs = remember(virtualUri) { IfsUri(virtualUri) }
    
    val segments = remember(virtualIfs, uri) { 
        val result = mutableListOf<Triple<String, String, Boolean>>() // Name, URI, isFuture
        var current = virtualIfs
        while (true) {
            val name = if (current.isRootUri()) {
                if (current.scheme == "file") "Root" else "${current.scheme}://"
            } else current.name
            
            // isFuture is true if the segment path is deeper than the active uri path
            val isFuture = current.uriString.length > uri.length
            
            result.add(0, Triple(name, current.uriString, isFuture))
            if (current.isRootUri()) break
            current = current.parent
        }
        result
    }

    LaunchedEffect(uri) {
        scrollState.animateScrollTo(scrollState.maxValue)
    }

    val density = LocalDensity.current

    Row(
        modifier = Modifier
            .dynamicHorizontalFadingEdge(scrollState, 32.dp)
            .onPointerEvent(PointerEventType.Scroll) { event ->
                val delta = event.changes.fold(0f) { acc, change -> 
                    acc + change.scrollDelta.y 
                }
                val deltaPx = with(density) { delta * 32.dp.toPx() }
                scrollState.dispatchRawDelta(deltaPx)
            }
            .horizontalScroll(scrollState),
        verticalAlignment = Alignment.CenterVertically
    ) {
        segments.forEachIndexed { index, (name, segmentUri, isFuture) ->
            val isLastActive = index == segments.indexOfLast { !it.third }
            
            if (index > 0) {
                Text(
                    text = "/",
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.3f),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 2.dp)
                )
            }
            
            Crumb(name = name, isLastActive = isLastActive, isFuture = isFuture, onClick = { onSegmentClick(segmentUri) })
        }
    }
}

@Composable
private fun Crumb(name: String, isLastActive: Boolean, isFuture: Boolean, onClick: () -> Unit) {
    val interactionSource = remember { MutableInteractionSource() }
    val isPressed by interactionSource.collectIsPressedAsState()
    
    // Premium click physics: scale down slightly when pressed
    val scale by animateFloatAsState(
        targetValue = if (isPressed) 0.96f else 1f,
        animationSpec = tween(durationMillis = 120, easing = FastOutSlowInEasing),
        label = "CrumbScale"
    )

    val opacity = if (isFuture) 0.4f else 1f

    // Dynamically calculate background color based on active, pressed, and hovered states
    val backgroundColor = when {
        isPressed -> MaterialTheme.colorScheme.primary.copy(alpha = 0.25f)
        isLastActive -> MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)
        else -> Color.Transparent
    }

    val contentColor = if (isLastActive) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.onSurfaceVariant
    }

    Box(
        modifier = Modifier
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
                alpha = opacity
            }
            .clip(RoundedCornerShape(6.dp))
            .background(backgroundColor)
            .clickable(
                interactionSource = interactionSource,
                indication = LocalIndication.current
            ) { onClick() }
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Text(
            text = name,
            style = if (isLastActive) MaterialTheme.typography.titleSmall else MaterialTheme.typography.bodyMedium,
            color = contentColor,
            fontWeight = if (isLastActive) FontWeight.Bold else FontWeight.Normal
        )
    }
}



/**
 * Native Compose implementation of a fading edge for horizontal scrolling.
 * Uses BlendMode.DstIn to mask the content smoothly at the edges.
 */
private fun Modifier.dynamicHorizontalFadingEdge(
    scrollState: ScrollState,
    edgeWidth: Dp = 32.dp
): Modifier = this
    .graphicsLayer(compositingStrategy = CompositingStrategy.Offscreen)
    .drawWithContent {
        drawContent()
        val edgeWidthPx = edgeWidth.toPx()

        // Left fading edge (only visible if we can scroll left)
        if (scrollState.value > 0) {
            drawRect(
                brush = Brush.horizontalGradient(
                    colors = listOf(Color.Transparent, Color.Black),
                    startX = 0f,
                    endX = edgeWidthPx
                ),
                blendMode = BlendMode.DstIn
            )
        }

        // Right fading edge (only visible if we can scroll right)
        if (scrollState.value < scrollState.maxValue) {
            drawRect(
                brush = Brush.horizontalGradient(
                    colors = listOf(Color.Black, Color.Transparent),
                    startX = size.width - edgeWidthPx,
                    endX = size.width
                ),
                blendMode = BlendMode.DstIn
            )
        }
    }