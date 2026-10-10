package com.imbric.app.ui.components.animations

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.innerShadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.unit.dp

/**
 * A subtle, premium edge pulse animation that triggers when content updates.
 * It uses the native Compose 1.9.0+ innerShadow modifier to draw a soft,
 * hardware-accelerated inset shadow that fades in and out.
 *
 * This is a `@Composable` [Modifier] extension on purpose. It used to be a
 * `Modifier.composed` factory: `composed` wraps its lambda in a
 * `ComposedModifier`, a plain `Modifier.Element` with *identity* equality. Because
 * the lambda captured [trigger], [resetKey] and [color], a brand new element was
 * produced on every recomposition, so the element was replaced, the nested
 * composition was thrown away and both the `Animatable` and the `LaunchedEffect`
 * were recreated from scratch on every single DirState emission. The
 * fade-in/fade-out pair therefore restarted forever and never ran to completion.
 *
 * Hoisting the state here — into the caller's own recompose scope instead of a
 * disposable sub-composition — keeps the [Animatable] alive across
 * recompositions, so each trigger plays one full 300ms + 500ms pulse.
 * [remember] also pins the returned `innerShadow` element to a single stable
 * draw block, so the draw node is created once instead of on every recomposition.
 *
 * @param trigger The value that triggers the pulse when it changes (e.g., a list hash).
 * @param resetKey The value that resets the pulse state (e.g., navigating to a new URI).
 *                 The pulse will NOT fire on the first trigger after a reset.
 * @param color The color of the pulse shadow.
 */
@Composable
fun Modifier.edgePulse(
    trigger: Any?,
    resetKey: Any?,
    color: Color
): Modifier {
    val base = this
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

    // Read through a stable State so the remembered draw block never has to be rebuilt
    // when the theme colour changes; the draw phase observes the read and invalidates itself.
    val currentColor = rememberUpdatedState(color)

    // Use the native innerShadow API (Compose 1.9.0+)
    // The block-based overload allows reading animatable.value during the draw phase,
    // completely bypassing recomposition for maximum performance.
    return remember(base, animatable, currentColor) {
        base.innerShadow(shape = RectangleShape) {
            val progress = animatable.value
            this.color = currentColor.value.copy(alpha = 0.3f * progress)
            this.radius = (60.dp * progress).toPx()
            this.spread = (5.dp * progress).toPx()
        }
    }
}
