package com.imbric.core.testing

import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.backends.GioBackend

class GioBackendContractTest : IOBackendContractTest() {
    private val testDir = "/tmp/imbric-gio-contract-test"

    override fun createBackend(): IOBackend = GioBackend()

    override fun getTestRootUri(): String = "file://$testDir"

    override fun setupTestEnvironment() {
        BashHelper.runScript("mkdir -p $testDir")
    }

    override fun teardownTestEnvironment() {
        BashHelper.runScript("rm -rf $testDir")
    }
}