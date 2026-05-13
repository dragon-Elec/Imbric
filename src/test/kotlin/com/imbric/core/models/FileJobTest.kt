@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class FileJobTest {

    @Test
    fun testCancellationToken() {
        val token = CancellationToken()
        assertFalse(token.isCancelled)
        token.cancel()
        assertTrue(token.isCancelled)
    }

    @Test
    fun testFileJobCreation() {
        val token = CancellationToken()
        val job = FileJob(
            opType = "copy",
            source = "file:///src/file.txt",
            dest = "file:///dest/file.txt",
            cancellable = token
        )

        assertEquals("copy", job.opType)
        assertEquals("file:///src/file.txt", job.source)
        assertEquals("file:///dest/file.txt", job.dest)
        assertTrue(job.id != Uuid.NIL)
        assertFalse(job.cancellable!!.isCancelled)
    }

    @Test
    fun testTransferProgress() {
        val jobId = Uuid.random()
        val progress = TransferProgress(
            jobId = jobId,
            currentFile = "test.txt",
            completedCount = 1,
            totalCount = 10,
            completedSize = 100L,
            totalSize = 1000L
        )

        assertEquals(jobId, progress.jobId)
        assertEquals("test.txt", progress.currentFile)
        assertEquals(10, progress.totalCount)
    }
}
