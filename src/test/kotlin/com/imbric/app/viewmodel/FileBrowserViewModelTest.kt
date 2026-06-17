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
    fun `test initial state is correct`() = runTest {
        val registry = DirStateRegistry(backend, backgroundScope)
        val rootUri = "memory:///"
        backend.createFolder("memory://", "")
        
        val viewModel = FileBrowserViewModel(registry, rootUri, backgroundScope)
        
        val state = viewModel.state.first()
        assertEquals(rootUri, state.uri)
        assertFalse(state.canGoUp) // Root cannot go up
    }

    @Test
    fun `test navigateTo changes URI and stops old DirState but retains it in cache`() = runTest {
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
        
        // Old state should NOT be destroyed, but kept in the cache for fast back/forward navigation
        assertFalse(oldState.isDestroyedState)
        assertTrue(registry.contains(oldUri), "Old URI should still be in registry cache")
    }

    @Test
    fun `test goUp navigates to parent directory`() = runTest {
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

    @Test
    fun `test virtualUri tracks currentUri on normal navigation and retains deep parent path when going back`() = runTest {
        val registry = DirStateRegistry(backend, backgroundScope)
        val parent = "memory:///home/user"
        val child1 = "memory:///home/user/Downloads"
        val child2 = "memory:///home/user/Downloads/Pictures"
        backend.createFolder("memory:///home/user", "Downloads")
        backend.createFolder("memory:///home/user/Downloads", "Pictures")
        
        val viewModel = FileBrowserViewModel(registry, parent, backgroundScope)
        assertEquals(parent, viewModel.virtualUri.value)
        
        viewModel.navigateTo(child1)
        assertEquals(child1, viewModel.virtualUri.value)
        
        viewModel.navigateTo(child2)
        assertEquals(child2, viewModel.virtualUri.value)
        
        // Go back: current goes to child1, but virtualUri retains child2 (deeper path)
        viewModel.goBack()
        assertEquals(child1, viewModel.currentUri.value)
        assertEquals(child2, viewModel.virtualUri.value)
        
        // Go back again: current goes to parent, but virtualUri still retains child2
        viewModel.goBack()
        assertEquals(parent, viewModel.currentUri.value)
        assertEquals(child2, viewModel.virtualUri.value)
    }

    @Test
    fun `test virtualUri resets completely when navigating to different hierarchy`() = runTest {
        val registry = DirStateRegistry(backend, backgroundScope)
        val pathA = "memory:///home/user/Downloads/Pictures"
        val pathB = "memory:///home/user/Downloads"
        val pathC = "memory:///etc/nginx"
        backend.createFolder("memory:///home/user/Downloads", "Pictures")
        backend.createFolder("memory:///etc", "nginx")
        
        val viewModel = FileBrowserViewModel(registry, pathA, backgroundScope)
        assertEquals(pathA, viewModel.virtualUri.value)
        
        viewModel.navigateTo(pathB)
        assertEquals(pathB, viewModel.currentUri.value)
        assertEquals(pathA, viewModel.virtualUri.value)
        
        // Jump completely to a non-child branch: virtualUri must reset to nginx
        viewModel.navigateTo(pathC)
        assertEquals(pathC, viewModel.currentUri.value)
        assertEquals(pathC, viewModel.virtualUri.value)
    }
}
