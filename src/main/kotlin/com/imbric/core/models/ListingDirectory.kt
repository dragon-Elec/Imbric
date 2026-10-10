package com.imbric.core.models

import kotlin.time.Instant

/**
 * Struct-of-Arrays (SoA) storage for directory listings.
 * Stores file metadata in parallel primitive arrays for zero per-object heap allocation.
 * Sorting swaps array indices instead of creating new objects.
 *
 * This eliminates the ~1ms/item object construction overhead of ListingFile data classes.
 * Objects are only created lazily via [asList] for visible UI items (~20-30 at a time).
 */
class ListingDirectory(initialCapacity: Int = 512) {
    var size: Int = 0
        private set

    private var names = arrayOfNulls<String>(initialCapacity)
    private var uris = arrayOfNulls<String>(initialCapacity)
    private var paths = arrayOfNulls<String>(initialCapacity)
    private var pathTypes = arrayOfNulls<PathType>(initialCapacity)
    private var isDirs = BooleanArray(initialCapacity)
    private var sizes = LongArray(initialCapacity)
    private var mimeTypes = arrayOfNulls<String>(initialCapacity)
    private var modifiedTimes = LongArray(initialCapacity) // epoch millis, -1 for null
    private var isHiddens = BooleanArray(initialCapacity)
    private var iconNames = arrayOfNulls<String>(initialCapacity)
    private var isInTrashes = BooleanArray(initialCapacity)
    private var isInRecents = BooleanArray(initialCapacity)
    private var isRemotes = BooleanArray(initialCapacity)
    private var isSymlinks = BooleanArray(initialCapacity)

    /** URI → array index map. Built after sorting, invalidated only by clear(). */
    private var uriIndex: HashMap<String, Int> = HashMap(initialCapacity)

    private fun ensureCapacity(minCapacity: Int) {
        if (minCapacity <= names.size) return
        val newCapacity = maxOf(minCapacity, names.size * 2)
        names = names.copyOf(newCapacity)
        uris = uris.copyOf(newCapacity)
        paths = paths.copyOf(newCapacity)
        pathTypes = pathTypes.copyOf(newCapacity)
        isDirs = isDirs.copyOf(newCapacity)
        sizes = sizes.copyOf(newCapacity)
        mimeTypes = mimeTypes.copyOf(newCapacity)
        modifiedTimes = modifiedTimes.copyOf(newCapacity)
        isHiddens = isHiddens.copyOf(newCapacity)
        iconNames = iconNames.copyOf(newCapacity)
        isInTrashes = isInTrashes.copyOf(newCapacity)
        isInRecents = isInRecents.copyOf(newCapacity)
        isRemotes = isRemotes.copyOf(newCapacity)
        isSymlinks = isSymlinks.copyOf(newCapacity)
    }

    /** Add a file entry. Returns the index. */
    fun add(entry: FileEntry): Int {
        ensureCapacity(size + 1)
        val i = size++
        names[i] = entry.name
        uris[i] = entry.uri
        paths[i] = entry.path
        pathTypes[i] = entry.pathType
        isDirs[i] = entry.isDirectory
        sizes[i] = entry.size
        mimeTypes[i] = entry.mimeType
        modifiedTimes[i] = entry.modifiedTime?.toEpochMilliseconds() ?: -1L
        isHiddens[i] = entry.isHidden
        iconNames[i] = entry.iconName
        isInTrashes[i] = entry.isInTrash
        isInRecents[i] = entry.isInRecent
        isRemotes[i] = entry.isRemote
        isSymlinks[i] = entry.isSymlink
        return i
    }

    /** Add from ListingFile (avoids interface dispatch). */
    fun addListing(listing: ListingFile): Int {
        ensureCapacity(size + 1)
        val i = size++
        names[i] = listing.name
        uris[i] = listing.uri
        paths[i] = listing.path
        pathTypes[i] = listing.pathType
        isDirs[i] = listing.isDirectory
        sizes[i] = listing.size
        mimeTypes[i] = listing.mimeType
        modifiedTimes[i] = listing.modifiedTime?.toEpochMilliseconds() ?: -1L
        isHiddens[i] = listing.isHidden
        iconNames[i] = listing.iconName
        isInTrashes[i] = listing.isInTrash
        isInRecents[i] = listing.isInRecent
        isRemotes[i] = listing.isRemote
        isSymlinks[i] = listing.isSymlink
        return i
    }

    /** Get a FileEntry at index (creates object on-demand). */
    fun get(index: Int): FileEntry = ArrayBackedEntry(index)

    /** Get the URI at index (no object allocation). */
    fun getUri(index: Int): String = uris[index]!!

    /** Get the name at index (no object allocation). */
    fun getName(index: Int): String = names[index]!!

    /** Get the size at index (no allocation). Indexes are valid only while the caller holds DirState's lock / before mutation, same rule as [getUri]. */
    fun getSizeAt(index: Int): Long = sizes[index]

    /** Get the modified time at index in epoch millis, -1 for null (no allocation). Indexes are valid only while the caller holds DirState's lock / before mutation, same rule as [getUri]. */
    fun getModifiedMillisAt(index: Int): Long = modifiedTimes[index]

    /** Get the directory flag at index (no allocation). Indexes are valid only while the caller holds DirState's lock / before mutation, same rule as [getUri]. */
    fun isDirAt(index: Int): Boolean = isDirs[index]

    /** Get the MIME type at index (no allocation). Indexes are valid only while the caller holds DirState's lock / before mutation, same rule as [getUri]. */
    fun getMimeAt(index: Int): String = mimeTypes[index]!!

    /**
     * Build the URI → index map. Must be called after sorting or adding entries.
     *
     * Reuses the existing HashMap table: clear() keeps the bucket array, so the
     * common re-sort path (same listing size) allocates nothing and rehashes
     * nothing; put() grows the table automatically if the listing grew.
     */
    fun buildUriIndex() {
        uriIndex.clear()
        for (i in 0 until size) {
            uriIndex[uris[i]!!] = i
        }
    }

    /** Find the array index for a URI. O(1) lookup. Returns -1 if not found. */
    fun findIndex(uri: String): Int = uriIndex.getOrDefault(uri, -1)

    /** Check if a URI exists in this directory. O(1) lookup. */
    fun containsUri(uri: String): Boolean = uriIndex.containsKey(uri)

    /**
     * Sort by swapping array indices using the given comparator on FileEntry.
     *
     * Allocation-free stable index sort: the order array and one scratch buffer
     * are the only allocations — no boxed Integers, no per-pass index copies,
     * no flags array. The sort order is identical to the previous
     * `indices.sortedWith` implementation (same comparator, same stability):
     * equal keys keep their original relative order.
     */
    fun sortWith(comparator: Comparator<FileEntry>) {
        if (size > 1) {
            val order = IntArray(size) { it }
            val scratch = IntArray(size)
            mergeSort(order, scratch, comparator)
            applyPermutation(order)
        }
        // Rebuild URI index after sort
        buildUriIndex()
    }

    /**
     * Bottom-up stable merge sort over the index array. Alternates [src]/[dst]
     * between passes so no per-pass copy-back is needed; when an odd number of
     * passes leaves the result in [scratch] it is copied back once at the end.
     */
    private fun mergeSort(order: IntArray, scratch: IntArray, comparator: Comparator<FileEntry>) {
        val n = order.size
        var src = order
        var dst = scratch
        var width = 1
        while (width < n) {
            var start = 0
            while (start < n) {
                val mid = minOf(start + width, n)
                val end = minOf(start + 2 * width, n)
                if (mid < end) {
                    merge(src, dst, start, mid, end, comparator)
                } else {
                    // Tail run with no merge partner: carry it over
                    // verbatim so dst is fully rewritten every pass
                    // (otherwise the next pass would read stale slots).
                    for (x in start until mid) dst[x] = src[x]
                }
                start += 2 * width
            }
            val tmp = src; src = dst; dst = tmp
            width *= 2
        }
        if (src !== order) {
            System.arraycopy(src, 0, order, 0, n)
        }
    }

    /** Merges the sorted runs [start, mid) and [mid, end) of [src] into [dst]. */
    private fun merge(
        src: IntArray, dst: IntArray, start: Int, mid: Int, end: Int,
        comparator: Comparator<FileEntry>
    ) {
        var i = start
        var j = mid
        var k = start
        while (i < mid && j < end) {
            // <= (not <) keeps the sort stable: on equal keys the element from
            // the left run — the one that appeared earlier originally — wins.
            if (comparator.compare(get(src[i]), get(src[j])) <= 0) {
                dst[k++] = src[i++]
            } else {
                dst[k++] = src[j++]
            }
        }
        while (i < mid) dst[k++] = src[i++]
        while (j < end) dst[k++] = src[j++]
    }

    /**
     * Applies [perm] (position k pulls from perm[k]) to all parallel arrays,
     * in place, via a cycle walk. Sign-marking (perm[x] -= n) replaces the old
     * BooleanArray flags — zero extra allocation. [perm] is restored to its
     * original values before returning, so the helper stays non-destructive.
     */
    private fun applyPermutation(perm: IntArray) {
        val n = perm.size
        for (i in 0 until n) {
            if (perm[i] < 0) continue
            var j = i
            // The perm[j] >= 0 guard covers self-loops (j == perm[j]): once j
            // is marked, perm[j] is negative and must not be used as an index
            // by the nested perm[perm[j]] check.
            while (perm[j] >= 0 && perm[perm[j]] >= 0) {
                val target = perm[j]
                swap(j, target)
                perm[j] -= n
                j = target
            }
            if (perm[j] >= 0) perm[j] -= n
        }
        for (i in 0 until n) perm[i] += n
    }

    private fun swap(i: Int, j: Int) {
        val tmpName = names[i]; names[i] = names[j]; names[j] = tmpName
        val tmpUri = uris[i]; uris[i] = uris[j]; uris[j] = tmpUri
        val tmpPath = paths[i]; paths[i] = paths[j]; paths[j] = tmpPath
        val tmpType = pathTypes[i]; pathTypes[i] = pathTypes[j]; pathTypes[j] = tmpType
        val tmpIcon = iconNames[i]; iconNames[i] = iconNames[j]; iconNames[j] = tmpIcon
        val tmpMime = mimeTypes[i]; mimeTypes[i] = mimeTypes[j]; mimeTypes[j] = tmpMime

        val tmpIsDir = isDirs[i]; isDirs[i] = isDirs[j]; isDirs[j] = tmpIsDir
        val tmpIsHidden = isHiddens[i]; isHiddens[i] = isHiddens[j]; isHiddens[j] = tmpIsHidden
        val tmpIsInTrash = isInTrashes[i]; isInTrashes[i] = isInTrashes[j]; isInTrashes[j] = tmpIsInTrash
        val tmpIsInRecent = isInRecents[i]; isInRecents[i] = isInRecents[j]; isInRecents[j] = tmpIsInRecent
        val tmpIsRemote = isRemotes[i]; isRemotes[i] = isRemotes[j]; isRemotes[j] = tmpIsRemote
        val tmpIsSymlink = isSymlinks[i]; isSymlinks[i] = isSymlinks[j]; isSymlinks[j] = tmpIsSymlink

        val tmpSize = sizes[i]; sizes[i] = sizes[j]; sizes[j] = tmpSize
        val tmpModified = modifiedTimes[i]; modifiedTimes[i] = modifiedTimes[j]; modifiedTimes[j] = tmpModified
    }

    /** Returns a lazy List<FileEntry> view. Objects created only when accessed by index. */
    fun asList(): List<FileEntry> = ListingView(this)

    /** Returns a map of uri -> FileEntry (creates all objects — use sparingly). */
    fun toMap(): Map<String, FileEntry> {
        val map = HashMap<String, FileEntry>(size)
        for (i in 0 until size) {
            map[uris[i]!!] = ArrayBackedEntry(i)
        }
        return map
    }

    /**
     * Lazy FileEntry backed by parallel arrays. No heap allocation per entry —
     * the object is ephemeral, created only when Compose accesses a visible item.
     */
    private inner class ArrayBackedEntry(private val index: Int) : FileEntry {
        override val name: String get() = names[index]!!
        override val uri: String get() = uris[index]!!
        override val path: String get() = paths[index]!!
        override val pathType: PathType get() = pathTypes[index]!!
        override val isDirectory: Boolean get() = isDirs[index]
        override val size: Long get() = sizes[index]
        override val mimeType: String get() = mimeTypes[index]!!
        override val modifiedTime: Instant?
            get() {
                val ms = modifiedTimes[index]
                return if (ms == -1L) null else Instant.fromEpochMilliseconds(ms)
            }
        override val isHidden: Boolean get() = isHiddens[index]
        override val iconName: String? get() = iconNames[index]
        override val isInTrash: Boolean get() = isInTrashes[index]
        override val isInRecent: Boolean get() = isInRecents[index]
        override val isRemote: Boolean get() = isRemotes[index]
        override val isSymlink: Boolean get() = isSymlinks[index]

        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (other !is FileEntry) return false
            return uri == other.uri
        }

        override fun hashCode(): Int = uri.hashCode()
        override fun toString(): String = "ListingEntry($name)"
    }
}

/**
 * Lazy List<FileEntry> backed by ListingDirectory.
 * Creates ArrayBackedEntry objects only when Compose accesses them by index.
 * Since Compose LazyVerticalGrid only accesses visible items (~20-30),
 * we only create ~20-30 objects instead of 440+.
 */
private class ListingView(private val dir: ListingDirectory) : AbstractList<FileEntry>() {
    override val size: Int get() = dir.size
    override fun get(index: Int): FileEntry = dir.get(index)
}
