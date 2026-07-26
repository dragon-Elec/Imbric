package com.imbric.core.testing

import com.imbric.core.ifs.contracts.BackendContract

class InMemoryBackendContractTest : IOBackendContractTest() {
    private lateinit var inMemoryBackend: InMemoryBackend

    override fun createBackend(): BackendContract = inMemoryBackend

    override fun getTestRootUri(): String = "memory://"

    override fun setupTestEnvironment() {
        inMemoryBackend = InMemoryBackend()
    }

    override fun teardownTestEnvironment() {
        // Nothing to do
    }
}