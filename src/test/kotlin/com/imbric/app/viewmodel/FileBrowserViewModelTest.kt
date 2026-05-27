package com.imbric.app.viewmodel

import com.imbric.core.ifs.provider.DirState
import com.imbric.core.ifs.provider.DirStateRegistry
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.*
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class FileBrowserViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private val testScope = TestScope(testDispatcher)
    private var backend = InMemoryBackend()

    @BeforeEach
    fun setup() {
        Dispatchers.setMain(testDispatcher)
        backend = InMemoryBackend()
        // We will initialize registry in the test using backgroundScope
    }

    @AfterEach
    fun teardown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `test initial state is correct`() = testScope.runTest {
        val registry = DirStateRegistry(backend, backgroundScope)
        val rootUri = "memory:///"
        backend.createFolder("memory://", "")
        
        val viewModel = FileBrowserViewModel(registry, rootUri, backgroundScope)
        
        val state = viewModel.state.first()
        assertEquals(rootUri, state.uri)
        assertFalse(state.canGoUp) // Root cannot go up
    }

    @Test
    fun `test navigateTo changes URI and stops old DirState but retains it in cache`() = testScope.runTest {
        val registry = DirStateRegistry(backend, backgroundScope)
        val oldUri = "memory:///old"
        val newUri = "memory:///new"
        backend.createFolder("memory:///", "old")
        backend.createFolder("memory:///", "new")
        
        val viewModel = FileBrowserViewModel(registry, oldUri, backgroundScope)
        assertEquals(oldUri, viewModel.currentUri.value)
        
        val oldState = registry.getOrCreate(oldUri)
        assertFalse(oldState.isDestroyedState)
        
        viewModel.navigateTo(newUri)
        
        assertEquals(newUri, viewModel.currentUri.value)
        val state = viewModel.state.value
        assertEquals(newUri, state.uri)
        
        // Old state should NOT be destroyed, but kept in the cache for fast back/forward navigation
        assertFalse(oldState.isDestroyedState)
        assertTrue(registry.contains(oldUri), "Old URI should still be in registry cache")
    }

    @Test
    fun `test goUp navigates to parent directory`() = testScope.runTest {
        val registry = DirStateRegistry(backend, backgroundScope)
        val childUri = "memory:///home/user/Documents"
        val parentUri = "memory:///home/user"
        backend.createFolder("memory:///home/user", "Documents")
        
        val viewModel = FileBrowserViewModel(registry, childUri, backgroundScope)
        assertEquals(childUri, viewModel.currentUri.value)
        assertTrue(viewModel.state.value.canGoUp)
        
        viewModel.goUp()
        
        assertEquals(parentUri, viewModel.currentUri.value)
    }
}
