package com.imbric.core.models

import kotlinx.datetime.Instant

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
        return i
    }

    /** Get a FileEntry at index (creates object on-demand). */
    fun get(index: Int): FileEntry = ArrayBackedEntry(index)

    /** Sort by swapping array indices using the given comparator on FileEntry. */
    fun sortWith(comparator: Comparator<FileEntry>) {
        // Create boxed index array for sorting ( unavoidable boxing for comparator )
        val indices = Array(size) { it }
        indices.sortWith { a, b -> comparator.compare(ArrayBackedEntry(a), ArrayBackedEntry(b)) }
        // Apply permutation to all parallel arrays
        val perm = IntArray(size) { indices[it] }
        applyPermutation(perm)
    }

    private fun applyPermutation(perm: IntArray) {
        val done = BooleanArray(size)
        for (i in 0 until size) {
            if (done[i]) continue
            var j = i
            while (!done[perm[j]]) {
                swap(j, perm[j])
                done[j] = true
                j = perm[j]
            }
            done[j] = true
        }
    }

    private fun swap(i: Int, j: Int) {
        var tmp: Any?

        tmp = names[i]; names[i] = names[j]; names[j] = tmp as? String
        tmp = uris[i]; uris[i] = uris[j]; uris[j] = tmp as? String
        tmp = paths[i]; paths[i] = paths[j]; paths[j] = tmp as? String
        tmp = pathTypes[i]; pathTypes[i] = pathTypes[j]; pathTypes[j] = tmp as? PathType
        tmp = iconNames[i]; iconNames[i] = iconNames[j]; iconNames[j] = tmp as? String
        tmp = mimeTypes[i]; mimeTypes[i] = mimeTypes[j]; mimeTypes[j] = tmp as? String

        var tmpB: Boolean
        tmpB = isDirs[i]; isDirs[i] = isDirs[j]; isDirs[j] = tmpB
        tmpB = isHiddens[i]; isHiddens[i] = isHiddens[j]; isHiddens[j] = tmpB
        tmpB = isInTrashes[i]; isInTrashes[i] = isInTrashes[j]; isInTrashes[j] = tmpB
        tmpB = isInRecents[i]; isInRecents[i] = isInRecents[j]; isInRecents[j] = tmpB
        tmpB = isRemotes[i]; isRemotes[i] = isRemotes[j]; isRemotes[j] = tmpB

        var tmpL: Long
        tmpL = sizes[i]; sizes[i] = sizes[j]; sizes[j] = tmpL
        tmpL = modifiedTimes[i]; modifiedTimes[i] = modifiedTimes[j]; modifiedTimes[j] = tmpL
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
