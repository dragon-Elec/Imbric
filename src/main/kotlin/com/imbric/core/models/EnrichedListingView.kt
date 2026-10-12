package com.imbric.core.models

/**
 * Immutable composite of a [ListingDirectory] snapshot + delta layer (additions,
 * deletions, enrichments), computed once in the constructor. A new instance per
 * rebuild gives StateFlow a fresh identity that always emits (see [equals]).
 *
 * **Aliasing caveat:** the base is held by reference and read live by [get]; when
 * [com.imbric.core.ifs.directories.DirState.sortBy] re-sorts it in place, reads are
 * transiently reordered until the rebuilt view publishes microseconds later. The
 * view's own mapping stays immutable.
 *
 * **Zero-delta fast path:** with all three delta collections empty, rows come from
 * the base's lazy [ListingDirectory.asList] delegate — no mapping array, no row
 * walked. A fresh instance is still created per rebuild, so revision behavior is
 * unchanged.
 */
class EnrichedListingView(
    private val base: ListingDirectory,
    private val comparator: Comparator<FileEntry>,
    private val additions: Map<String, FileInfo>,
    private val deletions: Set<String>,
    private val enrichments: Map<String, FileInfo>
) : AbstractList<FileEntry>() {

    private val additionsList: List<FileInfo>

    private val passthrough: List<FileEntry>?

    /** Base-index → view-index mapping; null while [passthrough] is active. */
    private val mapping: IntArray?

    init {
        additionsList = additions.values.sortedWith(comparator)

        if (additions.isEmpty() && deletions.isEmpty() && enrichments.isEmpty()) {
            passthrough = base.asList()
            mapping = null
        } else {
            passthrough = null

            if (additions.isEmpty() && deletions.isEmpty()) {
                mapping = IntArray(base.size) { it }
            } else {
                // Two-pointer merge: base (skipping deletions/additions) + sorted additions
                val result = IntArrayList(base.size + additionsList.size)
                var baseIdx = 0
                var addIdx = 0

                while (baseIdx < base.size && addIdx < additionsList.size) {
                    val baseUri = base.getUri(baseIdx)

                    // Skip deleted or modified base entries (modified = in additions)
                    if (baseUri in deletions || baseUri in additions) {
                        baseIdx++
                        continue
                    }

                    val addEntry = additionsList[addIdx]
                    val cmp = comparator.compare(base.get(baseIdx), addEntry)
                    if (cmp <= 0) {
                        result.add(baseIdx)
                        baseIdx++
                    } else {
                        result.add(-(addIdx + 1))
                        addIdx++
                    }
                }

                while (baseIdx < base.size) {
                    val baseUri = base.getUri(baseIdx)
                    if (baseUri !in deletions && baseUri !in additions) {
                        result.add(baseIdx)
                    }
                    baseIdx++
                }

                while (addIdx < additionsList.size) {
                    result.add(-(addIdx + 1))
                    addIdx++
                }

                mapping = result.toArray()
            }
        }
    }

    override val size: Int
        get() {
            val direct = passthrough
            if (direct != null) return direct.size
            // Pair invariant: mapping is non-null whenever passthrough is null.
            val mapped = requireNotNull(mapping) { "passthrough is null, so mapping must be non-null" }
            return mapped.size
        }

    override fun get(index: Int): FileEntry {
        val direct = passthrough
        if (direct != null) return direct[index]

        // Pair invariant: mapping is non-null whenever passthrough is null.
        val encoded = requireNotNull(mapping) { "passthrough is null, so mapping must be non-null" }[index]
        return if (encoded >= 0) {
            val uri = base.getUri(encoded)
            enrichments[uri] ?: base.get(encoded)
        } else {
            val additionIdx = -(encoded + 1)
            val addition = additionsList[additionIdx]
            enrichments[addition.uri] ?: addition
        }
    }

    // Identity equality — each instance is unique, forces StateFlow emission
    override fun equals(other: Any?): Boolean = this === other
    override fun hashCode(): Int = System.identityHashCode(this)

    private class IntArrayList(initialCapacity: Int) {
        private var data = IntArray(initialCapacity)
        var size: Int = 0
            private set

        fun add(value: Int) {
            if (size >= data.size) {
                data = data.copyOf(data.size * 2)
            }
            data[size++] = value
        }

        fun toArray(): IntArray = data.copyOf(size)
    }
}
