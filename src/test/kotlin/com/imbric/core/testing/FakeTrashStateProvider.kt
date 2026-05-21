package com.imbric.core.testing

import com.imbric.core.desktop.TrashStateProvider
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * A fake [TrashStateProvider] for testing.
 */
class FakeTrashStateProvider(initialEmpty: Boolean = true) : TrashStateProvider {
    private val _isEmpty = MutableStateFlow(initialEmpty)
    override val isEmpty: StateFlow<Boolean> = _isEmpty.asStateFlow()

    var refreshCount = 0
        private set

    override fun refresh() {
        refreshCount++
    }

    fun setEmpty(empty: Boolean) {
        _isEmpty.value = empty
    }
}
