package com.imbric.core.testing.contracts

import org.junit.jupiter.api.Test

/**
 * Contract: "File operations change the filesystem as expected."
 */
class MutationContractTest : ContractTestBase() {

    @Test
    fun `copy creates a duplicate at the destination`() = contractTest {
        fs.createFile("memory://src/original.txt")
        fs.createFolder("memory://dest")

        runSuspend { fs.backend.copy(job("copy", "memory://src/original.txt", "memory://dest/copy.txt")).collect {} }

        assert(fs.fileExists("memory://src/original.txt")) { "Source should still exist" }
        assert(fs.fileExists("memory://dest/copy.txt")) { "Destination should exist" }
    }

    @Test
    fun `move removes source and creates destination`() = contractTest {
        fs.createFile("memory://src/movable.txt")
        fs.createFolder("memory://dest")

        runSuspend { fs.backend.move(job("move", "memory://src/movable.txt", "memory://dest/moved.txt")).collect {} }

        assert(!fs.fileExists("memory://src/movable.txt")) { "Source should be gone" }
        assert(fs.fileExists("memory://dest/moved.txt")) { "Destination should exist" }
    }

    @Test
    fun `delete removes the file`() = contractTest {
        fs.createFile("memory://folder/doomed.txt")

        runSuspend { fs.backend.delete(job("delete", "memory://folder/doomed.txt")).getOrThrow() }

        assert(!fs.fileExists("memory://folder/doomed.txt"))
    }

    @Test
    fun `rename changes the name`() = contractTest {
        fs.createFile("memory://folder/old.txt")

        val newUri = runSuspend { fs.backend.rename("memory://folder/old.txt", "new.txt").getOrThrow() }

        assert(!fs.fileExists("memory://folder/old.txt"))
        assert(fs.fileExists("memory://folder/new.txt"))
        assert(newUri == "memory://folder/new.txt")
    }

    @Test
    fun `create file makes a new entry`() = contractTest {
        fs.createFolder("memory://parent")

        runSuspend { fs.backend.createFile("memory://parent", "child.txt").getOrThrow() }

        assert(fs.fileExists("memory://parent/child.txt"))
    }

    @Test
    fun `create folder makes a new directory`() = contractTest {
        fs.createFolder("memory://parent")

        runSuspend { fs.backend.createFolder("memory://parent", "newdir").getOrThrow() }

        assert(fs.fileExists("memory://parent/newdir"))
    }

    @Test
    fun `trash and restore roundtrip`() = contractTest {
        fs.createFile("memory://docs/important.txt")

        runSuspend {
            val trashUri = fs.backend.trash(job("trash", "memory://docs/important.txt")).getOrThrow()
            assert(!fs.fileExists("memory://docs/important.txt")) { "Gone after trash" }

            fs.backend.restoreFromTrash(trashUri, "memory://docs/important.txt").getOrThrow()
            assert(fs.fileExists("memory://docs/important.txt")) { "Back after restore" }
        }
    }
}
