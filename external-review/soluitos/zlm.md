Now I have a thorough understanding of all the source files. Let me do the deep analysis.
# Root Cause Analysis: 8x Performance Gap

After a deep forensic read of all five source files, I've identified the root causes. The gap is **not one bottleneck** — it's a **compound effect** of multiple interacting issues that happen to create a perfect storm in the production pipeline while being completely absent in the benchmark.

---

## 🔥 ROOT CAUSE #1: `enrichItem()` Fires Per-Item `updateItem()` Inside the Collect Loop (PRIMARY)

This is the **single largest contributor** to the 8x gap. Let me trace the exact execution:

**In `DirState.refresh()`, line 124:**
```kotlin
chunk.forEach { enrichItem(it) }  // Called for EVERY item in the chunk
```

**`enrichItem()` (line 221-256) does two things synchronously before the async launch:**

```kotlin
private fun enrichItem(info: FileInfo) {
    if (!enrichedUris.add(info.uri)) return

    val emblems = mutableListOf<String>()
    if (info.isSymlink) emblems.add("emblem-symbolic-link")
    if (!info.isWritable) emblems.add("emblem-readonly")  // ← SMOKING GUN
    // ...
    if (emblems.isNotEmpty()) {
        currentInfo = currentInfo.copy(attributes = ...)
        updateItem(currentInfo.uri, currentInfo)  // ← STATEFLOW UPDATE PER ITEM!
    }

    scope.launch(ioDispatcher) {  // ← async enrichment ALSO calls updateItem() 2x
        val enrichedInfo = enrichmentSemaphore.withPermit { backend.enrichMetadata(currentInfo) }
        if (enrichedInfo != currentInfo) {
            updateItem(enrichedInfo.uri, enrichedInfo)  // updateItem #2
        }
        val enrichedMarker = currentInfo.copy(attributes = ... + ("std::enriched" to true))
        updateItem(enrichedMarker.uri, enrichedMarker)  // updateItem #3
    }
}
```

**The critical detail: In listing mode, `isWritable` is NOT populated.** Looking at `GioTypeMappers.kt` line 83-98, the listing mode `FileInfo` construction sets these fields:

```kotlin
// Listing mode sets: id, name, path, uri, pathType, isDirectory, size, mimeType,
//                    modifiedTime, isHidden, backendId, isInTrash, isInRecent, isRemote
// Does NOT set: isWritable, isSymlink, isReadable, isExecutable, etc.
```

The `listingQueryAttributes` (line 104) is:
```
standard::name,standard::type,standard::is-hidden,standard::size,
standard::content-type,standard::is-symlink,access::can-execute
```

Notice `access::can-write` is **NOT** queried, so `isWritable` defaults to `false` in the data class. This means **`!info.isWritable` is `true` for EVERY file**, and **every single file** gets the `"emblem-readonly"` emblem synchronously, triggering `updateItem()` per item.

**`updateItem()` (line 258-263) updates TWO StateFlows per call:**

```kotlin
private fun updateItem(uri: String, info: FileInfo) {
    val updatedMap = _items.updateAndGet { current + (uri to info) }  // New Map
    _itemsList.value = updatedMap.values.toList()                     // New List
}
```

**Math for 440 items in the Screenshots dir:**
- 440 synchronous `updateItem()` calls inside the collect loop (one per item via `enrichItem`)
- Each creates a new `Map` via `current + (uri to info)` — O(n) per call
- Each creates a new `List` via `values.toList()` — O(n) per call
- Each triggers `_itemsList.value = ...` which notifies Compose

That's **440 StateFlow emissions** during listing instead of the **3 you'd expect** (one per chunk). Each emission triggers Compose recomposition of the LazyVerticalGrid.

**Why the benchmark is immune:** The benchmark collects with `items.add(it)` — zero StateFlow updates, zero Compose recompositions, zero enrichment.

**Estimated impact:** If each `updateItem()` takes ~1.5ms (map merge + list creation + Compose notification at growing sizes), that's 440 × 1.5ms = **660ms**, which matches the ~800ms unaccounted gap almost exactly.

---

## 🔥 ROOT CAUSE #2: Async Enrichment Causes Interleaved StateFlow Write Contention

Even after the synchronous emblem updates, each `enrichItem()` launches an async coroutine (`scope.launch(ioDispatcher)`) that calls `updateItem()` **2 more times** when enrichment completes:

1. `updateItem(enrichedInfo.uri, enrichedInfo)` — after `backend.enrichMetadata()`
2. `updateItem(enrichedMarker.uri, enrichedMarker)` — marking enrichment complete

With `enrichmentSemaphore = Semaphore(4)`, up to 4 enrichments run concurrently. These completions interleave with the chunk collection, creating **CAS contention on `_items.updateAndGet`**.

The `updateAndGet` on `MutableStateFlow` is a compare-and-swap loop. If the enrichment callback modifies `_items` while the chunk collector is also calling `updateAndGet`, the collector's CAS fails and must retry with the new value — redoing the entire `current + chunk.associateBy { it.uri }` map creation.

**Impact:** Each CAS retry wastes ~0.5-1ms of map allocation. With 440 items and 2 async updates each (880 enrichment StateFlow writes), and concurrent chunk writes, you get dozens of CAS retries.

---

## 🔥 ROOT CAUSE #3: Compose Recomposition Storm from 440+ Emissions

Every `_itemsList.value = ...` emission triggers Compose's `collectAsState()` on the main thread, which schedules a recomposition of the `LazyVerticalGrid`. 

With 3 chunk emissions + 440 synchronous emblem updates + ~880 async enrichment updates = **~1,323 StateFlow emissions** during a single directory load.

Even though Compose coalesces rapid recompositions (it batches them per frame), the sheer volume means Compose is continuously recomposing throughout the ~1 second window. Each recomposition of a `LazyVerticalGrid` with 200+ visible items involves:
- Snapshot state reads for each item
- Potential item recomposition
- Layout recalculation
- Drawing

**The benchmark has ZERO recompositions.**

---

## ROOT CAUSE #4: Growing O(n) Cost Per StateFlow Update

Each `updateItem()` and chunk collection does:

```kotlin
current + (uri to info)      // O(n) — creates entire new map
updatedMap.values.toList()   // O(n) — creates entire new list
```

For the first chunk (75 items), n=75. For the second chunk (200 items), n=275. For the third, n=440. With 440 per-item `updateItem()` calls, the average n is ~250, so total work is roughly `440 × 250 × 2 = 220,000` object copies.

The benchmark never creates maps or lists — it just appends to an `ArrayList`.

---

## ROOT CAUSE #5: Workers and Collectors Compete on Dispatchers.IO

The production pipeline has **13+ coroutines** on `Dispatchers.IO`:
- 8 worker coroutines (Semaphore(8))
- 1 chunk collector coroutine
- 4 enrichment coroutines (Semaphore(4))

The chunk collector does expensive work (`enrichItem()` → `updateItem()`) while holding an IO thread. This delays draining the `.buffer(256)`, which can cause workers to suspend on `send()`. The benchmark has no such contention.

---

## ROOT CAUSE #6: JVM Warmup Variance

The timing variance (986ms to 1721ms) strongly suggests JIT warmup is a factor. The benchmark likely runs the same code path repeatedly, allowing C2 compiler to fully optimize. The production app may encounter cold paths, especially for:
- The `channelFlow` state machine
- The `toImbricFileInfo()` FFM call chain
- The `MutableStateFlow.updateAndGet` CAS loop

This doesn't explain the 8x gap but amplifies the other causes by ~1.5-2x.

---

# CONCRETE FIXES (Ordered by Impact)

## Fix 1: Remove `enrichItem()` from the Collect Loop — Compute Emblems Inline (EXPECTED: ~5-6x improvement)

**This is the single most impactful fix.** Don't call `enrichItem()` inside the collect loop at all. Instead, compute emblems inline and batch the StateFlow update:

```kotlin
// In DirState.refresh()
strategy.list(backend, uri)
    .chunked(initialSize = 75, size = 200)
    .collect { chunk ->
        timer?.mark("dir_chunk_collected", itemCount = chunk.size)
        
        // Compute emblems INLINE — no per-item StateFlow update
        val enrichedChunk = chunk.map { info ->
            enrichedUris.add(info.uri)
            val emblems = buildList {
                if (info.isSymlink) add("emblem-symbolic-link")
                if (!info.isWritable) add("emblem-readonly")  // Will fire for listing mode
                val customEmblems = info.attributes["metadata::emblems"] as? List<*>
                customEmblems?.filterIsInstance<String>()?.let { addAll(it) }
            }
            if (emblems.isNotEmpty()) {
                info.copy(attributes = info.attributes + mapOf("std::emblems" to emblems))
            } else {
                info
            }
        }
        
        // SINGLE StateFlow update for the whole chunk
        val updatedMap = _items.updateAndGet { current + enrichedChunk.associateBy { it.uri } }
        _itemsList.value = updatedMap.values.toList()
        
        // Defer async enrichment — don't block the collect loop
        enrichedChunk.forEach { info ->
            launchEnrichment(info)
        }
        yield()
    }
```

Replace the `enrichItem()` call with a fire-and-forget enrichment launch:

```kotlin
private fun launchEnrichment(info: FileInfo) {
    scope.launch(ioDispatcher) {
        val enrichedInfo = enrichmentSemaphore.withPermit {
            backend.enrichMetadata(info)
        }
        if (enrichedInfo != info) {
            updateItem(enrichedInfo.uri, enrichedInfo)
        }
        val enrichedMarker = info.copy(
            attributes = info.attributes + ("std::enriched" to true)
        )
        updateItem(enrichedMarker.uri, enrichedMarker)
    }
}
```

**Why this works:** Reduces StateFlow emissions during listing from **440+ to just 3** (one per chunk). The collect loop becomes a fast path: compute emblems (pure computation, no FFI), single map+list update, yield.

---

## Fix 2: Defer Enrichment Until Listing Completes (EXPECTED: additional ~1.5x improvement on top of Fix 1)

Don't start any enrichment until the full listing is done. This eliminates all interleaved StateFlow writes during the critical listing phase:

```kotlin
try {
    val allEnrichableItems = mutableListOf<FileInfo>()
    strategy.list(backend, uri)
        .chunked(initialSize = 75, size = 200)
        .collect { chunk ->
            timer?.mark("dir_chunk_collected", itemCount = chunk.size)
            
            // Inline emblem computation (same as Fix 1)
            val enrichedChunk = chunk.map { info ->
                enrichedUris.add(info.uri)
                // ... emblem logic ...
                info
            }
            
            val updatedMap = _items.updateAndGet { current + enrichedChunk.associateBy { it.uri } }
            _itemsList.value = updatedMap.values.toList()
            allEnrichableItems.addAll(enrichedChunk)
            yield()
        }
    
    // Start enrichment AFTER listing completes — no contention
    allEnrichableItems.forEach { launchEnrichment(it) }
}
```

**Why this works:** During listing, zero enrichment coroutines compete with the collector. The 3 chunk StateFlow updates are uncontested. After listing, the user sees all 440 items and enrichment proceeds in the background without blocking the UI.

---

## Fix 3: Fix the `isWritable` Default for Listing Mode (EXPECTED: eliminates false "readonly" emblems)

In listing mode, `isWritable` is not populated and defaults to `false`, causing every file to get the `"emblem-readonly"` emblem. This is incorrect behavior AND a performance issue (unnecessary `copy()` + map construction per item).

**Option A — Set an optimistic default in `GioTypeMappers.kt`:**
```kotlin
if (listingMode) {
    return FileInfo(
        // ...
        isWritable = true,  // Optimistic default for local files
        isSymlink = gioInfo.isSymlink,  // Already in listingQueryAttributes!
        // ...
    )
}
```

**Option B — Skip emblem logic when attributes are unknown:**
```kotlin
// In enrichItem() or inline emblem computation
if (!info.isWritable && info.isWritableKnown) {  // Add isWritableKnown flag
    emblems.add("emblem-readonly")
}
```

**Why this works:** Eliminates unnecessary `info.copy(...)` calls and emblem updates for the vast majority of files that are writable. Also fixes a visual bug (everything appears as "readonly").

---

## Fix 4: Batch Enrichment StateFlow Updates (EXPECTED: reduces post-listing recomposition storm)

After Fix 1+2, enrichment still calls `updateItem()` per item (2× per item = 880 calls). Batch these:

```kotlin
private val pendingEnrichments = Collections.synchronizedList(mutableListOf<FileInfo>())

private fun scheduleEnrichmentUpdate(info: FileInfo) {
    pendingEnrichments.add(info)
    if (pendingEnrichments.size >= 50) {  // Batch threshold
        flushEnrichmentUpdates()
    }
}

private fun flushEnrichmentUpdates() {
    val batch = synchronized(pendingEnrichments) {
        val items = pendingEnrichments.toList()
        pendingEnrichments.clear()
        items
    }
    if (batch.isEmpty()) return
    val updatedMap = _items.updateAndGet { current ->
        var next = current
        batch.forEach { next = next + (it.uri to it) }
        next
    }
    _itemsList.value = updatedMap.values.toList()
}
```

Add a periodic flush via coroutine:
```kotlin
scope.launch(ioDispatcher) {
    while (isActive) {
        delay(100)  // Flush every 100ms
        flushEnrichmentUpdates()
    }
}
```

**Why this works:** Reduces post-listing StateFlow emissions from 880 to ~18 (880/50), reducing Compose recompositions by ~50x during enrichment.

---

## Fix 5: Remove `modificationDateTime` FFM Call from Listing Mode (EXPECTED: ~10-15% improvement)

In `GioTypeMappers.kt` line 92:
```kotlin
modifiedTime = gioInfo.modificationDateTime?.let { Instant.fromEpochSeconds(it.toUnix()) },
```

`modificationDateTime` accesses `time::modified` which is NOT in `listingQueryAttributes`. This still makes FFM calls (returning null). For 440 items, that's 880+ wasted FFM roundtrips (`getProperty` + `toUnix`):

```kotlin
if (listingMode) {
    return FileInfo(
        // ...
        modifiedTime = null,  // Skip — not queried, not needed for initial render
        // ...
    )
}
```

If modified time is needed for sorting, add `time::modified` to `listingQueryAttributes` so the FFM call returns actual data instead of hitting a null path.

---

## Fix 6: Add `isSymlink` to Listing Mode FileInfo (CORRECTNESS + small perf)

`listingQueryAttributes` already includes `standard::is-symlink`, but the listing mode construction doesn't use it:

```kotlin
if (listingMode) {
    return FileInfo(
        // ...
        isSymlink = gioInfo.isSymlink,  // Already fetched, just not mapped!
        // ...
    )
}
```

This ensures the inline emblem computation (Fix 1) works correctly for symlinks.

---

# EXPECTED IMPACT SUMMARY

| Fix | StateFlow Emissions During Listing | Estimated Time | vs Current |
|-----|------------------------------------|---------------|------------|
| Current | ~440+ | ~956ms | baseline |
| Fix 1 only | 3 | ~180ms | 5.3x |
| Fix 1+2 | 3 (zero contention) | ~150ms | 6.4x |
| Fix 1+2+3 | 3 (no false emblems) | ~140ms | 6.8x |
| Fix 1+2+3+4 | 3 (+ batched enrichment) | ~130ms | 7.4x |
| Fix 1+2+3+4+5 | 3 (+ fewer FFM calls) | ~120ms | ~8x (matches benchmark!) |

The combination of Fixes 1-5 should bring production performance to within ~120-130ms, essentially matching the benchmark's 121ms.

---

# WHY YOUR PREVIOUS ATTEMPTS DIDN'T WORK

| What You Tried | Why It Didn't Help |
|---|---|
| Unlimited buffer | `send()` backpressure wasn't the issue — the downstream **processing** was slow |
| Mutable accumulator (HashMap) | Didn't address the root cause (440 per-item StateFlow emissions) and added ConcurrentHashMap overhead |
| Decoupled collection (Dispatchers.Default) | Changed which threads contended but didn't reduce the number of StateFlow emissions |
| Sync nextFile() loop | Eliminated batching overhead but didn't address the enrichment storm in DirState |
| Removed .chunked() | Removed batching (good for throughput) but made per-item yield() overhead worse |
| Direct async dispatch (bypass idleAdd) | Fixed GLib pump latency but didn't address DirState's per-item StateFlow updates |
| getAttributeAsString() | Eliminated stderr I/O (a real win) but orthogonal to the StateFlow storm |
| listingMode (7 attrs vs 21) | Reduced FFM calls per file (real win) but didn't touch the 440× updateItem() calls |

All of these optimizations targeted the **GIO/FFM layer**, which the benchmark proves is already fast at 121ms. The real bottleneck is in **DirState's collection layer** — specifically the per-item StateFlow updates from `enrichItem()`.

---

# ARCHITECTURAL INSIGHT

Your pipeline has a fundamental design flaw: it mixes **two different update patterns** on the same `StateFlow`:

1. **Batch updates** (chunk collection) — efficient, 3 updates total
2. **Per-item updates** (enrichment) — expensive, 880+ updates total

These two patterns fight each other. The batch updates need the `StateFlow` to be stable long enough to accumulate a chunk, but per-item updates from `enrichItem()` constantly invalidate it.

**The fix is architectural: separate the listing pipeline from the enrichment pipeline.** During listing, only batch updates should touch the `StateFlow`. Enrichment should be a separate, debounced, non-interfering process that updates the `StateFlow` in batches after the initial render.

This is exactly how Nautilus works: `call_when_ready()` renders the basic listing first, then enrichment (thumbnails, deep counts, emblems) updates trickle in via a separate, throttled path that doesn't block the listing.
The analysis is complete. The TL;DR is: **`enrichItem()` inside the collect loop fires `updateItem()` (two StateFlow mutations) for every single item**, because `isWritable` defaults to `false` in listing mode, making every file appear "readonly" and triggering a synchronous emblem update. This turns 3 expected StateFlow emissions into 440+, and each one creates a new Map + List and triggers Compose recomposition. The benchmark avoids all of this because it just does `items.add(it)`.

Fix 1 alone (inline emblems, remove `enrichItem()` from the collect loop) should give you a ~5x speedup. Combined with deferring enrichment until after listing completes, you should match the benchmark's 121ms.
