package com.imbric.core.testing

import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.assertEquals
import java.io.File

class BashHelperTest {
    private val testDir = "/tmp/imbric-bash-test"

    @BeforeEach
    fun setup() {
        BashHelper.runScript("""
            mkdir -p $testDir/deep/tree
            touch $testDir/deep/tree/file.txt
            ln -s $testDir/deep/tree $testDir/shortcut
            chmod 400 $testDir/deep/tree/file.txt
            touch $testDir/.hidden_config
        """.trimIndent())
    }

    @AfterEach
    fun teardown() {
        BashHelper.runScript("rm -rf $testDir")
    }

    @Test
    fun testBashHelperCreatesFilesystemState() {
        assertTrue(File("$testDir/deep/tree/file.txt").exists(), "File should exist")
        assertTrue(File("$testDir/shortcut").exists(), "Symlink should exist")
        assertTrue(File("$testDir/.hidden_config").exists(), "Hidden file should exist")
        
        // Verify permissions
        val output = BashHelper.runScript("stat -c %a $testDir/deep/tree/file.txt").trim()
        assertEquals("400", output, "File should have 400 permissions")
    }
}