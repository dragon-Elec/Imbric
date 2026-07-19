package com.imbric.core.testing.contracts

import org.junit.jupiter.api.Test

/**
 * Contract: "When the disk changes, the view updates."
 */
class MonitoringContractTest : ContractTestBase() {

    @Test
    fun `new file on disk appears in the view`() = contractTest {
        fs.createFile("memory://watched/existing.txt")
        val view = openDir("memory://watched")
        view.assertShowsExactly("existing.txt")

        fs.createFile("memory://watched/new.txt")
        simulateCreated("memory://watched/new.txt")
        waitForEvents()

        view.waitUntil { it.size == 2 }
        view.assertShowsExactly("existing.txt", "new.txt")
    }

    @Test
    fun `deleted file on disk disappears from the view`() = contractTest {
        fs.createFile("memory://watched/keep.txt")
        fs.createFile("memory://watched/remove.txt")
        val view = openDir("memory://watched")
        view.assertShowsExactly("keep.txt", "remove.txt")

        fs.deleteFile("memory://watched/remove.txt")
        simulateDeleted("memory://watched/remove.txt")
        waitForEvents()

        view.waitUntil { it.size == 1 }
        view.assertShowsExactly("keep.txt")
    }

    @Test
    fun `renamed file updates in the view`() = contractTest {
        fs.createFile("memory://watched/old_name.txt")
        val view = openDir("memory://watched")
        view.assertShowsExactly("old_name.txt")

        fs.deleteFile("memory://watched/old_name.txt")
        fs.createFile("memory://watched/new_name.txt")
        simulateRenamed("memory://watched/old_name.txt", "memory://watched/new_name.txt")
        waitForEvents()

        view.waitUntil { items -> items.any { it.name == "new_name.txt" } }
        view.assertNotContains("old_name.txt")
        view.assertContains("new_name.txt")
    }

    @Test
    fun `multiple rapid changes are all reflected`() = contractTest {
        fs.createFile("memory://watched/a.txt")
        val view = openDir("memory://watched")
        view.assertShowsExactly("a.txt")

        fs.createFile("memory://watched/b.txt")
        fs.createFile("memory://watched/c.txt")
        fs.deleteFile("memory://watched/a.txt")
        simulateCreated("memory://watched/b.txt")
        simulateCreated("memory://watched/c.txt")
        simulateDeleted("memory://watched/a.txt")
        waitForEvents()

        view.waitUntil { it.size == 2 }
        view.assertShowsExactly("b.txt", "c.txt")
    }

    @Test
    fun `modified file stays in the view`() = contractTest {
        fs.createFile("memory://watched/doc.txt", size = 100)
        val view = openDir("memory://watched")
        view.assertShowsExactly("doc.txt")

        simulateModified("memory://watched/doc.txt")
        waitForEvents()

        view.assertContains("doc.txt")
    }

    @Test
    fun `events for other directories are ignored`() = contractTest {
        fs.createFile("memory://watched/local.txt")
        val view = openDir("memory://watched")
        view.assertShowsExactly("local.txt")

        fs.createFile("memory://other/remote.txt")
        simulateCreated("memory://other/remote.txt")
        waitForEvents()

        view.assertShowsExactly("local.txt")
    }

    @Test
    fun `rename out of directory removes file from view`() = contractTest {
        fs.createFile("memory://watched/moving.txt")
        val view = openDir("memory://watched")
        view.assertShowsExactly("moving.txt")

        fs.deleteFile("memory://watched/moving.txt")
        fs.createFile("memory://other/moved.txt")
        simulateRenamed("memory://watched/moving.txt", "memory://other/moved.txt")
        waitForEvents()

        view.waitUntil { it.isEmpty() }
        view.assertEmpty()
    }

    @Test
    fun `nested directory events are ignored by parent`() = contractTest {
        fs.createFile("memory://watched/parent_file.txt")
        fs.createFolder("memory://watched/subdir")
        val view = openDir("memory://watched")
        view.assertShowsExactly("parent_file.txt", "subdir")

        fs.createFile("memory://watched/subdir/nested.txt")
        simulateCreated("memory://watched/subdir/nested.txt")
        waitForEvents()

        // Parent should NOT show the nested file
        view.assertShowsExactly("parent_file.txt", "subdir")
    }
}
