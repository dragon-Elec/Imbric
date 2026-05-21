package com.imbric.core.testing

import com.imbric.core.ifs.IOBackend

class InMemoryBackendContractTest : IOBackendContractTest() {
    private lateinit var inMemoryBackend: InMemoryBackend

    override fun createBackend(): IOBackend = inMemoryBackend

    override fun getTestRootUri(): String = "memory://"

    override fun setupTestEnvironment() {
        inMemoryBackend = InMemoryBackend()
    }

    override fun teardownTestEnvironment() {
        // Nothing to do
    }
}