package com.imbric.core.desktop.backends

import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlin.system.measureTimeMillis
import kotlin.test.Test

class GioDesktopEnvironmentBenchmark {
    @Test
    fun benchmarkObserveDrives() {
        val env = GioDesktopEnvironment()
        var drives: List<Any>? = null
        val time = measureTimeMillis {
            runBlocking {
                drives = env.observeDrives().first()
            }
        }
        println("observeDrives() first emission took $time ms. Found ${drives?.size} drives.")
    }
}
