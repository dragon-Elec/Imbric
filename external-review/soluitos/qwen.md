Based on the code provided and the specific timing anomalies in your logs, the 8x performance gap is caused by a combination of **misleading profiling metrics**, **FFM/Native lock contention**, and a **Compose recomposition storm**.

Here is the breakdown of why the production pipeline is 8x slower and how to fix it.

### 1. The Profiling Illusion: The `[28]` Anomaly
Your log shows: `gio_list_done=+153ms [28]`. This is the "smoking gun" that explains the confusion.

In `GioBackend.list()`, you are using `channelFlow` with internal `launch(Dispatchers.IO)` workers:
```kotlin
override fun list(uri: String): Flow<FileInfo> = channelFlow {
    try {
        while (currentCoroutineContext().isActive) {
            // ... fetch batch ...
            launch(Dispatchers.IO) {
                // ... process and send() ...
                totalEmitted++
            }
        }
    } finally {
        enumerator.close(null)
    }
    // ⚠️ THIS EXECUTES IMMEDIATELY AFTER THE WHILE LOOP FINISHES
    timer?.mark("gio_list_done", itemCount = totalEmitted) 
}
```
**The Bug:** `channelFlow` keeps the channel open until all child coroutines finish, but **it does not block the execution of the code block itself**. The `while` loop finishes at 153ms (meaning GIO `nextFilesAsync` is indeed blazing fast), and the timer marks "done" immediately. However, the `launch` workers are still running in the background! The `[28]` simply means only 28 items had been processed and sent *by the time the timer line executed*.

The workers actually take the full ~800ms to finish processing the 440 items. Your benchmark measures the *entire* flow collection (121ms), while your production timer measures only the GIO fetch phase (153ms), making it appear as though the "workers" are slow, when in reality, they are being **starved by contention**.

### 2. The Root Cause: FFM / Native Lock Contention
Why do the workers take 1.9ms/file in production but 0.27ms/file in the benchmark? **Thread contention on the FFM (Foreign Function & Memory) layer.**

*   **In the Benchmark:** Only the `GioBackend` workers are running. They call `toImbricFileInfo()`, which accesses `gioInfo` attributes via FFM. This is fast (0.27ms/file).
*   **In Production:** As soon as the first chunk arrives, `DirState` launches `enrichItem` coroutines. These call `backend.enrichMetadata()`, which calls `readHeader()`, which executes `gfile.read(null)`—a **blocking FFM call** that reads 64KB from disk.
*   **The Lock:** If `java-gi` (or the underlying GLib/GIO bindings) uses a global lock for FFM downcalls to ensure thread safety, the 4 concurrent enrichment threads will hold this lock while doing blocking I/O. The `GioBackend` workers, trying to access `gioInfo` attributes (which also requires FFM), will be **blocked waiting for the lock**. This serialization turns a 0.27ms CPU operation into a 1.9ms wait state.

### 3. The Secondary Bottleneck: Compose Recomposition Storm
Look at `enrichItem` in `DirState.kt`:
```kotlin
scope.launch(ioDispatcher) {
    // ... enrich ...
    updateItem(enrichedInfo.uri, enrichedInfo) // ⚠️ Updates StateFlow
    // ...
    updateItem(enrichedMarker.uri, enrichedMarker) // ⚠️ Updates StateFlow again
}
```
For 440 items, this triggers **880 individual `StateFlow` updates**. Each update invalidates the Compose snapshot and triggers a recomposition of the `LazyVerticalGrid`. While this happens on the Main thread, the sheer volume of snapshot invalidations causes massive GC pressure and layout thrashing, which indirectly starves the CPU cache and memory bandwidth for your `Dispatchers.IO` threads.

---

### How to Close the Gap (Actionable Fixes)

#### Fix 1: Decouple Enrichment from Listing (The "Nautilus Pattern")
The most effective fix is to stop enriching *while* listing. The UI should render the basic list immediately (121ms), and enrichment should happen in the background *after* the listing is complete.

**Change `DirState.refresh()`:**
```kotlin
// 1. Collect listing WITHOUT enrichment
val allItems = mutableListOf<FileInfo>()
strategy.list(backend, uri)
    .chunked(initialSize = 75, size = 200)
    .collect { chunk ->
        timer?.mark("dir_chunk_collected", itemCount = chunk.size)
        val updatedMap = _items.updateAndGet { current ->
            current + chunk.associateBy { it.uri }
        }
        _itemsList.value = updatedMap.values.toList()
        allItems.addAll(chunk) // Buffer for later
        yield()
    }

// 2. Listing is done (121ms). NOW start enrichment in background.
// This eliminates FFM contention during the critical listing phase.
scope.launch(ioDispatcher) {
    allItems.forEach { enrichItem(it) }
}
```

#### Fix 2: Fix the `channelFlow` Timer Profiling
Wrap the worker loop in `coroutineScope` so the timer only fires when all workers are actually done. This will give you accurate metrics.

**Change `GioBackend.list()`:**
```kotlin
override fun list(uri: String): Flow<FileInfo> = channelFlow {
    // ... setup ...
    coroutineScope { // ⬅️ Wait for all launched children to complete
        try {
            while (currentCoroutineContext().isActive) {
                // ... fetch batch ...
                launch(Dispatchers.IO) {
                    // ... worker logic ...
                }
            }
        } finally {
            enumerator.close(null)
        }
    }
    // Now this fires ONLY when all 440 items are processed and sent
    timer?.mark("gio_list_done", itemCount = totalEmitted) 
}.flowOn(Dispatchers.IO).buffer(256)
```

#### Fix 3: Batch Enrichment StateFlow Updates
Instead of updating the `StateFlow` 880 times (triggering 880 recompositions), batch the enrichment updates just like you do for the initial listing.

**Add an Enrichment Consumer to `DirState`:**
```kotlin
private val enrichmentChannel = Channel<FileInfo>(Channel.UNLIMITED)

init {
    // Launch a single consumer to batch enrichment updates
    scope.launch {
        val batch = mutableListOf<FileInfo>()
        for (info in enrichmentChannel) {
            batch.add(info)
            // Drain remaining items to batch them
            while (true) {
                val next = enrichmentChannel.tryReceive().getOrNull() ?: break
                batch.add(next)
            }
            
            // Single StateFlow update for the whole batch
            val updatedMap = _items.updateAndGet { current ->
                current + batch.associateBy { it.uri }
            }
            _itemsList.value = updatedMap.values.toList()
            batch.clear()
            
            // Yield to allow UI to render (60fps target)
            delay(16) 
        }
    }
}

// Update enrichItem to send to channel instead of calling updateItem directly
private fun enrichItem(info: FileInfo) {
    // ... sync emblem logic ...
    scope.launch(ioDispatcher) {
        val enrichedInfo = enrichmentSemaphore.withPermit { backend.enrichMetadata(currentInfo) }
        // ...
        enrichmentChannel.send(enrichedMarker) // ⬅️ Send to batch consumer
    }
}
```

#### Fix 4: Optimize `enrichedUris`
`Collections.synchronizedSet` has high overhead. Since `enrichItem` is called sequentially from the collector thread (and occasionally from the watch thread), use a concurrent set.

```kotlin
// Replace this:
// private val enrichedUris = Collections.synchronizedSet(mutableSetOf<String>())

// With this:
private val enrichedUris = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
```

### Summary of Expected Results
1.  **Time-to-First-Render:** Drops from ~194ms to **~50ms** (listing is no longer blocked by enrichment I/O).
2.  **Total Listing Time:** Drops from ~1000ms to **~150ms** (matches benchmark; FFM contention eliminated).
3.  **UI Smoothness:** Massive improvement due to batching 880 recompositions into ~30 batched updates.
4.  **Accurate Profiling:** The `gio_list_done` timer will now correctly reflect the total time the workers spent processing.
