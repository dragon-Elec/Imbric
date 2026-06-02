package com.imbric.app.ui.components.animations

import androidx.compose.animation.core.*
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import kotlinx.coroutines.delay

enum class RevealState { HIDDEN, LOADING, REVEALING }

/**
 * A premium two-phase transition:
 * 1. Loading: A persistent tinted overlay with a continuous shimmer line sweeping across it.
 * 2. Revealing: When loading finishes, a final sweep wipes the tint away, leaving a transparent trail to reveal the items.
 */
@Composable
fun WipeReveal(
    isLoading: Boolean,
    modifier: Modifier = Modifier,
    delayMillis: Long = 200L,
    content: @Composable () -> Unit
) {
    var state by remember { mutableStateOf(RevealState.HIDDEN) }
    val revealAnimatable = remember { Animatable(0f) }

    // 1. Manage the two-phase state machine
    LaunchedEffect(isLoading) {
        if (isLoading) {
            delay(delayMillis)
            state = RevealState.LOADING
            revealAnimatable.snapTo(0f)
        } else {
            if (state == RevealState.LOADING) {
                state = RevealState.REVEALING
                // The final wipe reveal
                try {
                    revealAnimatable.animateTo(
                        targetValue = 1f,
                        animationSpec = tween(
                            durationMillis = 800,
                            easing = CubicBezierEasing(0.2f, 0.0f, 0.0f, 1.0f) // Premium decelerate
                        )
                    )
                } finally {
                    state = RevealState.HIDDEN
                }
            }
        }
    }

    // 2. The continuous sweep loop (only active during LOADING)
    val transition = rememberInfiniteTransition()
    val loopProgress by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = keyframes {
                durationMillis = 2000
                1f at 1200 using CubicBezierEasing(0.45f, 0.0f, 0.55f, 1.0f)
                1f at 2000
            },
            repeatMode = RepeatMode.Restart
        )
    )

    val isDark = isSystemInDarkTheme()
    val curtainColor = if (isDark) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.surfaceVariant
    val shimmerHighlight = if (isDark) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface

    Box(modifier = modifier.fillMaxSize()) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .drawWithContent {
                    // Draw the actual content first (Level 1)
                    drawContent()

                    if (state != RevealState.HIDDEN) {
                        val isRevealing = state == RevealState.REVEALING
                        val progress = if (isRevealing) revealAnimatable.value else loopProgress

                        val w = size.width
                        val h = size.height
                        val edgeWidth = 1000f
                        
                        val maxDistance = w + h + (edgeWidth * 2)
                        val sweepPosition = (maxDistance * progress) - edgeWidth
                        
                        val shimmerBrush = if (isRevealing) {
                            // Phase 2: The Wipe Reveal (Transparent trail behind the line)
                            Brush.linearGradient(
                                0.0f to Color.Transparent,
                                0.7f to shimmerHighlight.copy(alpha = 0.6f),
                                1.0f to curtainColor.copy(alpha = 0.8f),
                                start = Offset((sweepPosition - edgeWidth) / 2, (sweepPosition - edgeWidth) / 2),
                                end = Offset(sweepPosition / 2, sweepPosition / 2),
                                tileMode = TileMode.Clamp
                            )
                        } else {
                            // Phase 1: The Loading Loop (Solid curtain behind the line)
                            Brush.linearGradient(
                                0.0f to curtainColor.copy(alpha = 0.8f),
                                0.5f to shimmerHighlight.copy(alpha = 0.6f),
                                1.0f to curtainColor.copy(alpha = 0.8f),
                                start = Offset((sweepPosition - edgeWidth) / 2, (sweepPosition - edgeWidth) / 2),
                                end = Offset(sweepPosition / 2, sweepPosition / 2),
                                tileMode = TileMode.Clamp
                            )
                        }
                        
                        drawRect(brush = shimmerBrush)
                    }
                }
        ) {
            content()
        }
    }
}
