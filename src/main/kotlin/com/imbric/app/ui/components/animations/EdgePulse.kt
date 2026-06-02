package com.imbric.app.ui.components.animations

import androidx.compose.animation.core.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.innerShadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.unit.dp

/**
 * A subtle, premium edge pulse animation that triggers when content updates.
 * It uses the native Compose 1.9.0+ innerShadow modifier to draw a soft, 
 * hardware-accelerated inset shadow that fades in and out.
 *
 * @param trigger The value that triggers the pulse when it changes (e.g., a list hash).
 * @param resetKey The value that resets the pulse state (e.g., navigating to a new URI).
 *                 The pulse will NOT fire on the first trigger after a reset.
 * @param color The color of the pulse shadow.
 */
fun Modifier.edgePulse(
    trigger: Any?,
    resetKey: Any?,
    color: Color
): Modifier = composed {
    val animatable = remember { Animatable(0f) }
    var isFirstTriggerAfterReset by remember { mutableStateOf(true) }
    var lastResetKey by remember { mutableStateOf(resetKey) }

    // Merge both into a single key-tracking effect to enforce deterministic snaps and animation cycles
    LaunchedEffect(trigger, resetKey) {
        if (resetKey != lastResetKey) {
            lastResetKey = resetKey
            isFirstTriggerAfterReset = true
            animatable.snapTo(0f)
        } else {
            if (isFirstTriggerAfterReset) {
                isFirstTriggerAfterReset = false
            } else {
                animatable.snapTo(0f)
                // Fade in quickly
                animatable.animateTo(
                    targetValue = 1f,
                    animationSpec = tween(durationMillis = 300, easing = FastOutSlowInEasing)
                )
                // Fade out slowly
                animatable.animateTo(
                    targetValue = 0f,
                    animationSpec = tween(durationMillis = 500, easing = FastOutSlowInEasing)
                )
            }
        }
    }

    // Use the native innerShadow API (Compose 1.9.0+)
    // The block-based overload allows reading animatable.value during the draw phase,
    // completely bypassing recomposition for maximum performance.
    this.innerShadow(shape = RectangleShape) {
        val progress = animatable.value
        this.color = color.copy(alpha = 0.3f * progress)
        this.radius = (60.dp * progress).toPx()
        this.spread = (5.dp * progress).toPx()
    }
}