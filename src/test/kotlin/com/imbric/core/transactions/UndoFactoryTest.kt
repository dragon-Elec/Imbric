@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.transactions.models.TransactionOperation
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertNotNull
import kotlin.uuid.Uuid

class UndoFactoryTest {

    @Test
    fun testCreateInverseCopy() {
        val op = TransactionOperation(
            jobId = Uuid.random(),
            opType = "copy",
            src = "file:///src.txt",
            dest = "file:///dest.txt"
        )
        val inverse = UndoFactory.createInverse(op)
        assertNotNull(inverse)
        assertEquals("undo_copy", inverse["action"])
        assertEquals("file:///dest.txt", inverse["target"])
    }

    @Test
    fun testCreateInverseMove() {
        val op = TransactionOperation(
            jobId = Uuid.random(),
            opType = "move",
            src = "file:///src.txt",
            dest = "file:///dest.txt"
        )
        val inverse = UndoFactory.createInverse(op)
        assertNotNull(inverse)
        assertEquals("undo_move", inverse["action"])
        assertEquals("file:///dest.txt", inverse["target"])
        assertEquals("file:///src.txt", inverse["dest"])
    }

    @Test
    fun testCreateInverseRename() {
        val op = TransactionOperation(
            jobId = Uuid.random(),
            opType = "rename",
            src = "file:///old.txt",
            dest = "file:///new.txt"
        )
        val inverse = UndoFactory.createInverse(op)
        assertNotNull(inverse)
        assertEquals("undo_rename", inverse["action"])
        assertEquals("file:///new.txt", inverse["target"])
        assertEquals("file:///old.txt", inverse["dest"])
    }

    @Test
    fun testCreateInverseUnknown() {
        val op = TransactionOperation(
            jobId = Uuid.random(),
            opType = "unknown",
            src = "file:///src.txt",
            dest = "file:///dest.txt"
        )
        val inverse = UndoFactory.createInverse(op)
        assertNull(inverse)
    }
}
