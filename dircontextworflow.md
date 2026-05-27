---
description: Workflow to create/update package context audit files with Logic-DNA grammar (Kotlin-native). Context files inherit directory name as prefix (e.g., corecontext.md). Single root index.md for project structure. Bottom-up contexting order.
---

# Package Context Creation Guide

## What is a context file?
A context file is a per-package audit file placed inside source packages (e.g., `core/`, `core/ifs/`).
Naming inherits the directory name as prefix: `corecontext.md`, `ifscontext.md`.
It acts as a Router and a Map. An AI reads this file FIRST when entering a package.

### Scope Rule

- Top-level packages (`com.imbric.core.ifs`, `com.imbric.core.transactions`): one context file (e.g., `ifscontext.md`, `transactionscontext.md`)
- Sub-packages only get their own if they exceed ~700 lines combined or have complex logic
- No per-file audit blocks for trivial files (<50 lines, no branching)
- Target: 10 files × ~70 lines each = worth a context file
- Single `index.md` at project root indexes entire project

### Naming Convention
- Context files inherit the directory name as prefix
- Pattern: `{dirname}context.md`
- Examples:
  - `/imbric-kt/core` → `corecontext.md`
  - `/imbric-kt/core/ifs` → `ifscontext.md`
  - `/imbric-kt/core/transactions` → `transactionscontext.md`

From this file alone, the AI should be able to:
1. Understand what this package does and why it exists.
2. Identify which specific `.kt` file to open for a given task.
3. Avoid opening files it does not need.

## What a context file is NOT
- NOT a changelog or history file. No dates, no "recently added" prose.
- NOT a TODO list. Use HANDOVER.md or the project board.
- NOT a code generation spec. The audit blocks describe existing code, not desired code.
- NOT a replacement for reading the source. It is a routing layer that tells you WHAT to read, not a substitute for reading it.
- NOT a signal that the code is messy. Good code deserves routing too.

## Quality Benchmark

Each audit block should provide enough logical density that an AI can understand and modify the file with 95% accuracy without reading the full source.

---

## Navigation Protocol
When an AI needs to fix a bug or add a feature:
1. Read the context file of the package closest to the problem (e.g., `corecontext.md`).
2. Use the Index section to decide if a sub-directory is relevant.
3. Use the Audit blocks to identify which `.kt` file(s) to open.
4. Only THEN open the actual source file.
This prevents unnecessary file reads and reduces context pollution.

---

## Structure

Each context file follows this order:

1. **Identity** — 1-2 lines. Package path and why this folder exists.
2. **Rules** — Strict package-specific coding instructions (thread safety, etc). Use sparingly.
3. **Atomic Notes** — Informational patterns (`!Pattern`) and architectural choices (`!Decision`). Do NOT use `!Rule` for simple information giving.
4. **Index** — 1-line intent per sub-package or key file. Acts as a router.
5. **Audits** — Per-file logical DNA. See Section: Audit Blocks.

For small packages (<3 files), merge Index and Audits into a flat list.

---

## index.md

### Purpose
Quick lookup for AI agent to know directory structure. NOT a context file.

### Difference from Context File

| **index.md** | **context file** |
|--------------|------------------|
| Single root file | Per-directory file |
| Directory structure map | Package logic map |
| "What files exist here" | "What this code does" |
| Self-maintaining registry | Static audit |
| Entry point for navigation | Entry point for understanding |

### Naming Convention
- Single `index.md` at project root
- Indexes entire project structure
- Context files remain per-directory: `{dirname}context.md`

### Contents
- Project root directory tree with 1-line summaries
- Self-maintain instructions at top
- No logic, no DNA, no dependencies — just structure
- Registers all directories and key files
- Registers all context files when created

### Example
```
/imbric-kt/
├── core/                     — Core business logic
│   ├── ifs/                  — File system operations (GIO backend)
│   ├── transactions/         — Transaction management
│   ├── models/               — Data classes (FileJob, FileState)
│   ├── CoreEngine.kt         — Main orchestrator
│   └── Config.kt             — App configuration
├── utils/                    — Shared utilities
│   ├── Extensions.kt         — Kotlin extension functions
│   └── Constants.kt          — App-wide constants
├── build.gradle.kts          — Build configuration
└── index.md                  — This file (project index)
```

### Self-Maintain Instructions
Every `index.md` must include this header:
```
<!-- INDEX MAINTENANCE RULES
1. New file created → add to this index with 1-line summary
2. File deleted → remove from this index
3. File renamed → update entry
4. Context file created → register in this index
-->
```

---

## Bottom-Up Contexting Order

### Why Bottom-Up Works
- Leaf packages have no dependencies to understand first
- Each context file can reference its sub-packages' context files
- Agent builds understanding from concrete → abstract
- Root context file is LAST, synthesizing everything below

### Order
```
1. /core/ifs/gio/          → giocontext.md
2. /core/ifs/              → ifscontext.md (references giocontext.md)
3. /core/transactions/     → transactionscontext.md
4. /core/                  → corecontext.md (references ifs, transactions)
5. /                       → projectcontext.md (root overview)
```

### Agent Reading Protocol
1. Start at deepest directory
2. Read only files in current directory
3. Write context file for that directory
4. Register context file in root `index.md`
5. Move up one level
6. Repeat until root

### What NOT to Do
- Do NOT read all files first
- Do NOT start from root
- Do NOT skip leaf packages
- Do NOT create context files for directories with <3 files (mention in parent's index)

---

## Formatting Rules

- NO bold text for keys. Use plain `Key: Value`.
- NO full sentences. Use fragments.
- Fragments must retain technical specificity. "Resets currentIndex if out of bounds" is correct. "Adjusts focus" is too vague.
- NO nested lists deeper than 2 levels.
- NO changelogs, dates, or version numbers.
- NO clustered blocks. Use blank lines between Role, /DNA/, Dependencies, and API.
- Inline code backticks for identifiers: `GioBackend`, `StateFlow`, `limitedParallelism`.

---

## Logic-DNA Grammar

Compressed notation for mapping causality in code. Optimized for LLM parsing.

Symbols:

- `->` : Causes / Triggers / Leads to
- `=>` : Returns / Resolves to
- `++` / `--` : Increments / Decrements state
- `em:` : Emits to Flow / updates StateFlow
- `call:` : Invokes a method
- `suspend` : Suspending function (coroutine)
- `if()` : Conditional branch
- `wait` : Pauses for async resolution
- `C|F` : Success (Completed) or Failure
- `[...]` : Logic block or grouped operation

Kotlin examples:

```
[call:backend.copy(job) -> if(cancelled) em:_progress.error | em:_progress.done]
[suspend withContext(IO) -> gfile.queryInfo(attrs, cancellable) => FileInfo]
[em:conflictDetected -> wait channel.receive() -> resume with action]
```

---

## Audit Block Rules

1. **Logical Density**: Exactly ONE `/DNA/` line per file. If multiple loops exist, merge using `[...] + [...]` grouping.
2. **Spacing**: Blank line between `/DNA/` and Dependencies, another before API section.
3. **Dependencies**: Inline on a single line per key.
   
   - Kotlin: `kotlinx.coroutines{flow, channel}`, `org.gnome.gio{File, Cancellable}`
   
   - Internal: `.ifs.IOBackend`, `.models.FileJob`
   
   - Short lists (1-2 items) skip braces: `.IOBackend`, `.Cancellable`
4. **Caveats**: Use for Kotlin-specific gotchas like backing field quirks, initialization ordering, or FFM memory lifetimes.

---

## Atomic Notes

Prefix: `!Pattern`, `!Decision`, or `!Rule`
Format: `!Category: [X > Y] - Reason: one-line explanation.`

Kotlin examples:

- `!Decision: [sync-on-IO > native async] - Reason: GIO async requires GLib MainLoop; coroutine wrappers not needed for Cancellable-enabled sync ops.`
- `!Pattern: [Cancellable per FileJob] - Reason: Shared cancellables cause cross-job cancellation; each job gets a fresh Cancellable injected at submit time.`
- `!Pattern: [Flow for progress > callback] - Reason: FileProgressCallback updates MutableStateFlow; Compose observes via collectAsState().`
- `!Rule: [Call ensureInitialized before GIO] - Reason: JVM doesn't run `<clinit>` for interface static methods; missing = `UnsupportedOperationException`.`

Authorship Protocol:

- NEVER add a Rule, Atomic Note, or Maintenance entry without explicit user permission.
- To suggest a new note, confirm the pattern exists across 2+ files, present with reasoning.
- A wrong rule is worse than no rule.

---

## Audit Blocks

Each `.kt` file gets one block.

Schema:

```
### [FILE: FileName.kt] [STATUS]
Role: One-line intent.

/DNA/: Compressed causal map of the core logic loops.

- SrcDeps: .ifs.IOBackend, .models.FileJob
- SysDeps: kotlinx.coroutines{flow}, org.gnome.gio{File, Cancellable}

API:
  - ClassName:
    - fun method(args): ReturnType — technically specific contract
    - StateFlow<Type> — observable state
!Caveat: Gotcha or non-obvious behavior.
```

Status tags: [DONE], [USABLE], [WIP], [STUB], [DEPRECATED]

- [USABLE] = technically complete, not yet reviewed by user
- Never use [DONE] without user confirmation

Deprecated Methods: Keep OUT of API section. Document as `!Caveat` line.

---

## Anti-Patterns

- Never write prose paragraphs in an audit block.
- Never duplicate information that belongs in HANDOVER.md or AGENTS.md.
- Never audit trivial files (<50 lines, single class, no branching) — mention them in Index, skip the block.
- Never use bold, italic, or decorative markdown.
- Never include coroutine plumbing boilerplate in audit (the LLM already knows how `withContext` works).

---

## Kotlin-Specific Patterns to Document

When auditing Kotlin files, highlight these if present:

- **Explicit backing fields**: `val isCancelled: Boolean get() = _isCancelled` — note the `_prop` pattern
- **Sealed class hierarchies**: algebraic types used for state machines
- **Flow bridging**: `channelFlow { }`, `callbackFlow { }`, `MutableStateFlow`
- **FFI memory lifetimes**: Arena usage in generated bindings
- **Cancellable injection**: per-job vs shared patterns

---

## Validation

To verify an audit block hasn't missed public API, use grep to list top-level declarations:

```bash
grep -n "^\(fun \|val \|var \|class \|object \|sealed \|data class \|interface \)" src/main/kotlin/com/imbric/core/FILE.kt
```

Private/internal declarations (no `private` or `internal` modifier) should be in the audit API if they're part of the package's public contract.

### Context File Validation
To verify context files follow naming convention:
```bash
find . -name "*context.md" -type f | sort
```
Expected pattern: `{dirname}context.md` in each package directory.

---

## Maintenance

- Sync Protocol: When file logic changes, diff the existing audit block against the source. Update ONLY the changed parts. Preserve unchanged wording.
- New Packages: Add a context file BEFORE or during implementation, not after. Use `{dirname}context.md` naming.
- New Files: Register in root `index.md` with 1-line summary.
- Context Files: Register in root `index.md` when created.
- Pruning: If HANDOVER.md grows too large, migrate file-level detail to the relevant context file.
