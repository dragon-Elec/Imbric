package com.imbric.core.testing.contracts

import org.junit.jupiter.api.Test

/**
 * Contract: "Opening folder X shows X's contents, not Y's."
 *
 * These tests verify that navigation is correct — each folder shows its own files,
 * and switching folders shows the new folder's files.
 */
class NavigationContractTest : ContractTestBase() {

    @Test
    fun `opening different folders shows different contents`() = contractTest {
        fs.createFile("memory://alpha/one.txt")
        fs.createFile("memory://alpha/two.txt")
        fs.createFile("memory://beta/three.txt")

        val alphaView = openDir("memory://alpha")
        alphaView.assertShowsExactly("one.txt", "two.txt")

        val betaView = openDir("memory://beta")
        betaView.assertShowsExactly("three.txt")

        // Alpha view should still be correct
        alphaView.assertShowsExactly("one.txt", "two.txt")
    }

    @Test
    fun `reopening the same folder returns cached state`() = contractTest {
        fs.createFile("memory://cached/file.txt")

        val view1 = openDir("memory://cached")
        view1.assertShowsExactly("file.txt")

        val view2 = openDir("memory://cached")
        view2.assertShowsExactly("file.txt")
    }

    @Test
    fun `parent folder does not contain child folder contents`() = contractTest {
        fs.createFolder("memory://root/child")
        fs.createFile("memory://root/child/deep.txt")
        fs.createFile("memory://root/shallow.txt")

        val rootView = openDir("memory://root")
        rootView.assertShowsExactly("child", "shallow.txt")
        rootView.assertNotContains("deep.txt")
    }
}
