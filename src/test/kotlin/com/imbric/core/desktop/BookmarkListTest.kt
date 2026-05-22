@file:OptIn(ExperimentalCoroutinesApi::class)

package com.imbric.core.desktop

import com.imbric.core.models.Bookmark
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import java.io.File
import kotlin.test.*

class BookmarkListTest {

    private lateinit var tempDir: File
    private lateinit var jsonFile: File
    private lateinit var gtkFile: File
    private lateinit var bookmarkList: BookmarkList

    @BeforeTest
    fun setup() {
        tempDir = createTempDirectory("bookmark-test")
        jsonFile = File(tempDir, "bookmarks.json")
        gtkFile = File(tempDir, "gtk-bookmarks")

        bookmarkList = BookmarkList(
            scope = CoroutineScope(UnconfinedTestDispatcher() + SupervisorJob()),
            jsonPath = jsonFile.toPath(),
            gtkPath = gtkFile.toPath(),
            enableMonitoring = false,
            uriValidator = { it.isNotBlank() } // Simple validator for tests
        )
    }

    @AfterTest
    fun teardown() {
        bookmarkList.dispose()
        tempDir.deleteRecursively()
    }

    // ── Bookmark data class ──────────────────────────────────────────────

    @Test
    fun testBookmarkDisplayName() {
        val withLabel = Bookmark(name = "Documents", uri = "file:///docs", label = "My Docs")
        assertEquals("My Docs", withLabel.displayName)

        val withoutLabel = Bookmark(name = "Documents", uri = "file:///docs")
        assertEquals("Documents", withoutLabel.displayName)
    }

    // ── GTK Parsing ──────────────────────────────────────────────────────

    @Test
    fun testParseGtkBookmarksBasic() {
        val text = """
            file:///home/user/Documents Documents
            file:///home/user/Downloads Downloads
            file:///home/user/Music
        """.trimIndent()

        val bookmarks = bookmarkList.parseGtkBookmarks(text)
        assertEquals(3, bookmarks.size)

        assertEquals("file:///home/user/Documents", bookmarks[0].uri)
        assertEquals("Documents", bookmarks[0].label)
        assertEquals("Documents", bookmarks[0].name)

        assertEquals("file:///home/user/Downloads", bookmarks[1].uri)
        assertEquals("Downloads", bookmarks[1].label)

        assertEquals("file:///home/user/Music", bookmarks[2].uri)
        assertNull(bookmarks[2].label)
        assertEquals("Music", bookmarks[2].name) // Derived from URI
    }

    @Test
    fun testParseGtkBookmarksEmpty() {
        val bookmarks = bookmarkList.parseGtkBookmarks("")
        assertTrue(bookmarks.isEmpty())
    }

    @Test
    fun testParseGtkBookmarksBlankLines() {
        val text = "file:///docs Docs\n\n\nfile:///music Music\n"
        val bookmarks = bookmarkList.parseGtkBookmarks(text)
        assertEquals(2, bookmarks.size)
    }

    // ── Add / Contains / Get ─────────────────────────────────────────────

    @Test
    fun testAddBookmark() {
        val bookmark = Bookmark(name = "Documents", uri = "file:///home/user/Documents")
        assertTrue(bookmarkList.add(bookmark))
        assertTrue(bookmarkList.contains("file:///home/user/Documents"))
        assertEquals(bookmark, bookmarkList.getBookmark("file:///home/user/Documents"))
    }

    @Test
    fun testAddDuplicateReturnsFalse() {
        val bookmark = Bookmark(name = "Documents", uri = "file:///home/user/Documents")
        assertTrue(bookmarkList.add(bookmark))
        assertFalse(bookmarkList.add(bookmark)) // Duplicate
        assertEquals(1, bookmarkList.getAll().size)
    }

    @Test
    fun testAddBlankUriReturnsFalse() {
        val bookmark = Bookmark(name = "Empty", uri = "")
        assertFalse(bookmarkList.add(bookmark))
    }

    @Test
    fun testAddAtIndex() {
        val b1 = Bookmark(name = "First", uri = "file:///first")
        val b2 = Bookmark(name = "Second", uri = "file:///second")
        val b3 = Bookmark(name = "Insert", uri = "file:///insert")

        bookmarkList.add(b1)
        bookmarkList.add(b2)
        bookmarkList.add(b3, index = 1) // Insert between first and second

        val all = bookmarkList.getAll()
        assertEquals(3, all.size)
        assertEquals("file:///first", all[0].uri)
        assertEquals("file:///insert", all[1].uri)
        assertEquals("file:///second", all[2].uri)
    }

    // ── Remove ───────────────────────────────────────────────────────────

    @Test
    fun testRemoveBookmark() {
        val bookmark = Bookmark(name = "Documents", uri = "file:///home/user/Documents")
        bookmarkList.add(bookmark)
        assertTrue(bookmarkList.contains("file:///home/user/Documents"))

        bookmarkList.remove("file:///home/user/Documents")
        assertFalse(bookmarkList.contains("file:///home/user/Documents"))
        assertTrue(bookmarkList.getAll().isEmpty())
    }

    @Test
    fun testRemoveNonexistentDoesNothing() {
        bookmarkList.remove("file:///nonexistent")
        assertTrue(bookmarkList.getAll().isEmpty())
    }

    // ── Move ─────────────────────────────────────────────────────────────

    @Test
    fun testMoveItem() {
        val b1 = Bookmark(name = "First", uri = "file:///first")
        val b2 = Bookmark(name = "Second", uri = "file:///second")
        val b3 = Bookmark(name = "Third", uri = "file:///third")

        bookmarkList.add(b1)
        bookmarkList.add(b2)
        bookmarkList.add(b3)

        bookmarkList.moveItem(0, 2) // Move first to after second

        val all = bookmarkList.getAll()
        assertEquals("file:///second", all[0].uri)
        assertEquals("file:///third", all[1].uri)
        assertEquals("file:///first", all[2].uri)
    }

    @Test
    fun testMoveItemOutOfBoundsDoesNothing() {
        val b1 = Bookmark(name = "First", uri = "file:///first")
        bookmarkList.add(b1)

        bookmarkList.moveItem(0, 5) // Out of bounds
        assertEquals(1, bookmarkList.getAll().size)
        assertEquals("file:///first", bookmarkList.getAll()[0].uri)
    }

    // ── canBookmark ──────────────────────────────────────────────────────

    @Test
    fun testCanBookmark() {
        assertTrue(bookmarkList.canBookmark("file:///new"))
        assertFalse(bookmarkList.canBookmark(""))

        bookmarkList.add(Bookmark(name = "Test", uri = "file:///new"))
        assertFalse(bookmarkList.canBookmark("file:///new"))
    }

    // ── Persistence ──────────────────────────────────────────────────────

    @Test
    fun testSaveAndLoadJson() {
        bookmarkList.add(Bookmark(name = "Docs", uri = "file:///docs"))
        bookmarkList.add(Bookmark(name = "Music", uri = "file:///music"))
        bookmarkList.saveJson()

        // Create a new instance that loads from the same JSON file
        val loaded = BookmarkList(
            scope = CoroutineScope(UnconfinedTestDispatcher() + SupervisorJob()),
            jsonPath = jsonFile.toPath(),
            gtkPath = gtkFile.toPath(),
            enableMonitoring = false,
            uriValidator = { it.isNotBlank() }
        )

        assertEquals(2, loaded.getAll().size)
        assertEquals("file:///docs", loaded.getAll()[0].uri)
        assertEquals("file:///music", loaded.getAll()[1].uri)
        loaded.dispose()
    }

    @Test
    fun testGtkImportOnFirstRun() {
        // Write a GTK bookmarks file
        gtkFile.writeText("file:///home/user/Documents Documents\nfile:///home/user/Downloads\n")

        // Create a new instance with no JSON file (first run)
        val fresh = BookmarkList(
            scope = CoroutineScope(UnconfinedTestDispatcher() + SupervisorJob()),
            jsonPath = File(tempDir, "new-bookmarks.json").toPath(),
            gtkPath = gtkFile.toPath(),
            enableMonitoring = false,
            uriValidator = { it.isNotBlank() }
        )

        assertEquals(2, fresh.getAll().size)
        assertEquals("file:///home/user/Documents", fresh.getAll()[0].uri)
        assertEquals("Documents", fresh.getAll()[0].label)
        assertEquals("file:///home/user/Downloads", fresh.getAll()[1].uri)
        fresh.dispose()
    }

    @Test
    fun testWriteGtkBookmarks() {
        bookmarkList.add(Bookmark(name = "Docs", uri = "file:///docs", label = "My Documents"))
        bookmarkList.add(Bookmark(name = "Music", uri = "file:///music"))
        bookmarkList.writeGtkBookmarks()

        val content = gtkFile.readText()
        assertTrue(content.contains("file:///docs My Documents"))
        assertTrue(content.contains("file:///music"))
    }

    // ── Reactive StateFlow ───────────────────────────────────────────────

    @Test
    fun testBookmarksStateFlowEmits() = runTest {
        val collected = mutableListOf<List<Bookmark>>()
        val job = launch(UnconfinedTestDispatcher(testScheduler)) {
            bookmarkList.bookmarks.collect { collected.add(it) }
        }

        bookmarkList.add(Bookmark(name = "A", uri = "file:///a"))
        bookmarkList.add(Bookmark(name = "B", uri = "file:///b"))

        // Initial empty + 2 adds
        assertTrue(collected.size >= 3)
        assertTrue(collected.last().size == 2)

        job.cancel()
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private fun createTempDirectory(prefix: String): File {
        val dir = File.createTempFile(prefix, "")
        dir.delete()
        dir.mkdirs()
        return dir
    }
}
