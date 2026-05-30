# Performance Roadmap — Directory Listing Pipeline

## Current State (May 2026)

**Benchmarked on 440-item directory (Screenshots):**

| Component | Time | Notes |
|-----------|------|-------|
| Raw GIO fetch | 71ms | `nextFilesAsync(5000)` via `awaitGioAsync` |
| Object construction | 6ms | `toListingFile()` — 11-field `ListingFile` |
| Sorting | 4ms | `sortedWith(FileEntry.comparatorFor)` |
| HashMap | 1ms | `associateBy { it.uri }` |
| **Sum of parts** | **83ms** | Isolated benchmark |
| **Production pipeline** | **940ms** | With DirState collect + Compose rendering |

**Breakdown of the 857ms gap:**
- Coroutine emission overhead (~190ms): per-item `emit()` through `flow {}` collected by DirState
- DirState sorting + map building (~180ms): `sortedWith()` + `associateBy()` at 200-item threshold + final 440
- Compose rendering (~374ms): `LazyVerticalGrid` layout + composition

**What was already optimized:**
1. Async GIO batching (`nextFilesAsync(5000)`) — single FFM batch call
2. `getAttributeAsString()` replacing `getAttributeString()` — eliminated stderr syscalls (28% gain)
3. `listingMode` with 5 targeted attributes vs 21 wildcard categories (49% gain)
4. Progressive chunking (200-item emission threshold)
5. Native OS daemon thread for GLib pump (eliminated frame-rate polling latency)
6. Direct dispatch in `awaitGioAsync` (bypassing `GLib.idleAdd`)
7. `ListingFile` (11 fields) replacing `FileInfo` (35 fields) on listing path
8. Removed `.flowOn(Dispatchers.IO)` — eliminated internal channel (37% pipeline gain)

---

## Phase 1: Batch Emission (High Impact, Medium Effort)

**Problem:** `Flow<FileEntry>` emits 440 individual items. Each `emit()` + `collect()` is a coroutine suspension point. DirState inserts each into HashMap individually, then sorts at 200-item and 440-item thresholds.

**Fix:** Change `IOBackend.list()` to return `Flow<List<FileEntry>>`. GioBackend builds the full list internally and emits once. DirState receives 440 items in a single collect, sorts once, emits once to StateFlow.

**Expected gain:** ~300-400ms (eliminates 440 per-item coroutine suspensions + reduces sort/map operations from 2 to 1).

**Touches:** `IOBackend` interface, `GioBackend`, `ListingStrategy`, `DirState`, ~20 test callsites.

**Progressive variant:** Emit first ~200 items sorted (fast render), then full list sorted. Two emissions total instead of 440.

---

## Phase 2: Multi-Field Value Classes (Medium Impact, Low Effort)

**Kotlin 2.4 experimental feature.** `ListingFile` as a multi-field value class would eliminate heap allocation per file — properties inlined directly into method parameters and stack.

```kotlin
@JvmInline
value class ListingFile(
    val name: String,
    val uri: String,
    val isDirectory: Boolean,
    // ...
)
```

**Caveats:**
- Requires `-Xmulti-field-value-classes` compiler flag
- Boxing occurs when stored in `List<T>`, `Map<K, V>`, or any generic container
- `StateFlow<List<ListingFile>>` would force boxing, negating the benefit
- `remember { mutableStateOf(listingFile) }` also boxes
- Best suited for intermediate pipeline stages, not final storage

**When to adopt:** After Kotlin 2.5+ stabilizes MFVC and Compose adds unboxed collection support.

---

## Phase 3: DirStateRegistry Lifecycle Management (Low Perf Impact, High Reliability)

**Problem:** Every visited folder creates a `DirState` with active coroutines that hold strong references to `this`, preventing `WeakReference` GC. This is a memory leak — 50 visited folders = 50 active file monitors + coroutines.

**Options:**
1. **LRU eviction** — keep last N (e.g., 20) DirStates, destroy oldest on eviction
2. **Reference counting** — UI calls `retain()`/`release()`, destroy on zero refs
3. **ViewModel-owned lifecycle** — ViewModel explicitly creates/destroys DirStates
4. **Idle timeout** — destroy DirStates not accessed for N minutes

---

## Phase 4: Compose Rendering (Low Control, Framework-Dependent)

**374ms for 440 items in LazyVerticalGrid.** This is Compose's layout + composition overhead.

**Possible improvements:**
- `derivedStateOf` for sorting (already implemented — avoids re-sorting on recomposition)
- Stable keys via `key(item.uri)` in LazyVerticalGrid (already implemented)
- Minimize per-cell composition cost (already flattened — Box + clip + clickable)
- `GridCells.Fixed(N)` pre-calculated (already implemented — avoids per-recomposition column recalculation)

**Remaining option:** Move sorting to `Dispatchers.Default` via `produceState` or `snapshotFlow`, so Compose thread only handles rendering. But this adds complexity for marginal gain.

---

## Phase 5: Show-First-Sort-Later (UX Trade-off)

**Concept:** Emit first ~200 items in filesystem order immediately (~100ms), then replace with fully sorted list (~50ms later). User sees items appear instantly, then a brief reorder.

**Trade-off:** Faster perceived performance vs brief visual reorder flash. Similar to how web pages render progressive JPEG — show something fast, refine later.

**Implementation:** Two-phase emission in `DirState.refresh()`:
1. First 200 items: sort only those, emit to StateFlow
2. All items collected: sort all, emit final StateFlow update

---

## Theoretical Minimum

With all optimizations applied:
- GIO + construction + sort: **83ms** (benchmarked)
- Single batch emission: **~5ms** (one Flow collect, one StateFlow update)
- Compose rendering: **~200ms** (optimistic lower bound for 440 grid cells)
- **Total: ~290ms** for 440 items cold load

Current: 940ms. Theoretical minimum: ~290ms. **3.2x potential improvement remaining.**
