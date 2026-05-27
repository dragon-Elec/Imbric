package com.imbric.core.desktop.backends

import com.imbric.core.ifs.backends.GioRecentBackend
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.gnome.gio.Gio
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test
import kotlin.system.measureTimeMillis
import kotlin.test.assertTrue

class GioRecentBackendBenchmark {
    companion object {
        @JvmStatic
        @BeforeAll
        fun setup() {
            Gio.`javagi$ensureInitialized`()
        }
    }

    @Test
    fun benchmarkListRecents() = runBlocking {
        val backend = GioRecentBackend()

        // Warmup
        backend.list("recent:///").toList()

        val times = mutableListOf<Long>()
        var count = 0
        for (i in 1..5) {
            val time = measureTimeMillis {
                val items = backend.list("recent:///").toList()
                count = items.size
            }
            times.add(time)
        }

        println("Avg time for list() with $count items: ${times.average()} ms (times: $times)")
        assertTrue(true)
    }
}

