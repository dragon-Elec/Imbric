package com.imbric.core.testing.contracts

import org.junit.jupiter.api.Test

/**
 * Contract: "Bad input produces errors, not crashes."
 */
class ErrorContractTest : ContractTestBase() {

    @Test
    fun `listing a non-existent folder returns empty or error`() = contractTest {
        val view = openDir("memory://nonexistent")
        assert(view.items.isEmpty() || view.error != null) {
            "Expected empty or error, got ${view.items.size} items"
        }
    }

    @Test
    fun `deleting a non-existent file returns error`() = contractTest {
        val result = runSuspend { fs.backend.delete(job("delete", "memory://folder/ghost.txt")) }
        assert(result.isFailure) { "Expected failure" }
    }

    @Test
    fun `renaming a non-existent file returns error`() = contractTest {
        val result = runSuspend { fs.backend.rename("memory://folder/ghost.txt", "new.txt") }
        assert(result.isFailure) { "Expected failure" }
    }

    @Test
    fun `copy to existing destination without overwrite returns error`() = contractTest {
        fs.createFile("memory://src/file.txt")
        fs.createFile("memory://dest/file.txt")

        val result = runCatching {
            runSuspend {
                fs.backend.copy(job("copy", "memory://src/file.txt", "memory://dest/file.txt")).collect {}
            }
        }
        assert(result.isFailure) { "Expected failure" }
    }

    @Test
    fun `view remains stable after backend error`() = contractTest {
        fs.createFile("memory://stable/exists.txt")
        val view = openDir("memory://stable")
        view.assertShowsExactly("exists.txt")

        runSuspend { fs.backend.delete(job("delete", "memory://stable/ghost.txt")) }

        view.assertShowsExactly("exists.txt")
        view.assertNoError()
    }
}
