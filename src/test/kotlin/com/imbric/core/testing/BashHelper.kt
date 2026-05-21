package com.imbric.core.testing

import java.io.File

object BashHelper {
    /**
     * Executes a bash script and returns its output.
     * Throws an exception if the script fails.
     */
    fun runScript(script: String, workDir: File = File("/tmp")): String {
        val process = ProcessBuilder("/bin/bash", "-c", script)
            .directory(workDir)
            .redirectErrorStream(true)
            .start()
            
        val output = process.inputStream.bufferedReader().readText()
        val exitCode = process.waitFor()
        
        if (exitCode != 0) {
            throw RuntimeException("Bash script failed with exit code $exitCode:\n$output")
        }
        return output
    }
}