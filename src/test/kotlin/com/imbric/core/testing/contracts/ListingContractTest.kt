package com.imbric.core.testing.contracts

import org.junit.jupiter.api.Test

/**
 * Contract: "Opening a folder shows what is on disk."
 *
 * These tests verify that DirState's listing matches the actual filesystem state.
 * If SoA, ListingDirectory, or the listing pipeline breaks, these catch it.
 */
class ListingContractTest : ContractTestBase() {

    @Test
    fun `empty folder shows nothing`() = contractTest {
        fs.createFolder("memory://empty")
        val view = openDir("memory://empty")
        view.assertEmpty()
        view.assertNotLoading()
        view.assertNoError()
    }

    @Test
    fun `folder with files shows exactly those files`() = contractTest {
        fs.createFile("memory://docs/a.txt")
        fs.createFile("memory://docs/b.txt")
        fs.createFile("memory://docs/c.txt")

        val view = openDir("memory://docs")
        view.assertShowsExactly("a.txt", "b.txt", "c.txt")
        view.assertSize(3)
        view.assertNoError()
    }

    @Test
    fun `nested files are not included in parent listing`() = contractTest {
        fs.createFile("memory://root/file.txt")
        fs.createFolder("memory://root/subdir")
        fs.createFile("memory://root/subdir/nested.txt")

        val view = openDir("memory://root")
        view.assertShowsExactly("file.txt", "subdir")
        view.assertSize(2)
    }

    @Test
    fun `hidden files are included in listing`() = contractTest {
        fs.createFile("memory://folder/visible.txt")
        fs.createFile("memory://folder/.hidden", isHidden = true)

        val view = openDir("memory://folder")
        view.assertShowsExactly(".hidden", "visible.txt")
    }

    @Test
    fun `directories and files are both shown`() = contractTest {
        fs.createFolder("memory://mixed/folder1")
        fs.createFolder("memory://mixed/folder2")
        fs.createFile("memory://mixed/file.txt")

        val view = openDir("memory://mixed")
        view.assertShowsExactly("file.txt", "folder1", "folder2")
    }

    @Test
    fun `listing matches filesystem exactly — no phantom files`() = contractTest {
        fs.createFile("memory://exact/real.txt")

        val view = openDir("memory://exact")
        view.assertShowsExactly("real.txt")
        view.assertNotContains("phantom.txt")
    }

    @Test
    fun `large directory lists all files`() = contractTest {
        val names = (1..500).map { "file_$it.txt" }
        names.forEach { fs.createFile("memory://large/$it") }

        val view = openDir("memory://large")
        view.assertSize(500)
        names.forEach { view.assertContains(it) }
    }
}
