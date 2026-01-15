# AI Context System: Conventions & Usage Guide

> **Purpose:** Defines markers, patterns, and workflows for AI-assisted project management.  
> **Audience:** LLMs maintaining project context files.

---

## 1. Marker Reference

### 1.1. Status Markers

| Marker | Meaning | Usage Context |
|:-------|:--------|:--------------|
| `[VERIFIED: YYYY-MM-DD]` | Documentation confirmed accurate | Module docs, file index |
| `[STALE]` | May be outdated, verify before trusting | Any documentation section |
| `[AI-TODO]` | Needs AI investigation/analysis | Discovered issues, unexplored areas |
| `[AI-TODO: description]` | Specific investigation needed | When context is important |
| `[DEPRECATED]` | Marked for removal | Code, features, files |
| `[LEGACY]` | Old code kept for compatibility | Code sections |
| `[WIP]` | Work in progress | Documentation being written |

### 1.2. Task Markers

| Marker | State | Meaning |
|:-------|:------|:--------|
| `[ ]` | Pending | Not started |
| `[/]` | In Progress | Currently active |
| `[x]` | Complete | Done and verified |
| `[!]` | Blocked | Cannot proceed |
| `[~]` | On Hold | Paused intentionally |
| `[-]` | Cancelled | Will not be done |

### 1.3. Priority Tags

| Tag | Level | Response Time |
|:----|:------|:--------------|
| `P0` | Critical | Immediate — blocks everything |
| `P1` | High | This session/day |
| `P2` | Medium | This week/sprint |
| `P3` | Low | When time permits |

### 1.4. Risk Levels

| Level | Definition | Examples |
|:------|:-----------|:---------|
| `LOW` | Read-only, no side effects | Getters, formatters, validators |
| `MED` | Modifies local/recoverable state | Config writes, cache updates |
| `HIGH` | System state, potentially destructive | File deletion, DB writes, privilege escalation |

### 1.5. Instruction Markers

| Marker | Purpose |
|:-------|:--------|
| `[AI-INSTRUCTION]` | Guidance on how to fill/maintain a section |
| `[AI-NOTE]` | Context note for future AI sessions |
| `[AI-WARNING]` | Critical gotcha or danger zone |

---

## 2. File Naming Conventions

### 2.1. Context Files (Root Level)

| File | Purpose | Update Frequency |
|:-----|:--------|:-----------------|
| `PROJECT_CONTEXT.md` | Architecture, modules, safety | Major changes |
| `TASK.md` | Active work tracking | Every session |
| `CHANGELOG.md` | Change history | After each feature/fix |

### 2.2. Optional Companion Files

| File | Purpose | When to Use |
|:-----|:--------|:------------|
| `RESEARCH.md` | Investigation notes, findings | Complex problem solving |
| `DECISIONS.md` | ADRs (Architecture Decision Records) | Major technical choices |
| `API.md` | Public interface documentation | Libraries, APIs |
| `TESTING.md` | Test strategy, coverage notes | Test-heavy projects |

---

## 3. AI Session Workflow

### 3.1. Session Start Checklist

```markdown
1. Read PROJECT_CONTEXT.md → "Quick Context" section
2. Read TASK.md → "Current Focus" + "In Progress"
3. Check for [!] Blocked items
4. Update TASK.md → "Current Session" goals
```

### 3.2. During Session

```markdown
- Move tasks between sections as status changes
- Add [AI-TODO] markers when discovering issues
- Update "Current Session > Accomplished" incrementally
```

### 3.3. Session End Checklist

```markdown
1. Update TASK.md:
   - Mark completed items [x]
   - Update "Accomplished" list
   - Write "Handoff Notes" for next session
   
2. Update PROJECT_CONTEXT.md (if applicable):
   - Section 9.1 "Last Session Summary"
   - Any [STALE] → [VERIFIED] updates
   
3. Update CHANGELOG.md:
   - Add entries under [Unreleased]
```

---

## 4. Documentation Style

### 4.1. Compression Principles

<!-- Aligned with user's semantic compression preferences -->

| Rule | Before | After |
|:-----|:-------|:------|
| Remove fluff | "In order to achieve..." | "To achieve..." |
| Use symbols | "returns" | `→` |
| Use symbols | "not equal" | `!=` |
| Use symbols | "and/or" | `&&` / `\|\|` |
| Flatten | Nested paragraphs | `Key: Value` pairs |
| Be specific | "the function" | `function_name()` |

### 4.2. Code References

```markdown
✓ `module.function()`     — backtick wrap
✓ `path/to/file.py`       — full path when ambiguous
✓ `file.py:45`            — with line number
✓ `Class.method()`        — qualified name

✗ module.function()       — no backticks
✗ "the save function"     — vague reference
```

### 4.3. Table Usage

**Use tables for:**
- Function/method signatures
- File indexes
- Configuration options
- Comparison of alternatives

**Avoid tables for:**
- Narrative explanations
- Step-by-step procedures (use numbered lists)

---

## 5. Section Expansion Guidelines

| Section | Expand When | Keep Brief When |
|:--------|:------------|:----------------|
| Core Modules | Complex logic, many functions | Simple utilities |
| UI Layer | UI-heavy project | Backend/CLI focus |
| Safety | System-level operations | Pure computation |
| Data Flow | Complex state, async | Stateless operations |
| Known Issues | Active bugs, workarounds | Clean codebase |

---

## 6. Cross-Referencing

### 6.1. Internal Links

```markdown
See [Section Name](#section-name)
Defined in [Core Modules](#3-core-modules)
```

### 6.2. File References

```markdown
Managed by `core/config.py`
See `TASK.md > In Progress`
Documented in `PROJECT_CONTEXT.md#4-interfaceui-layer`
```

### 6.3. Issue/Task References

```markdown
Related to TASK#003
Fixes Known Issue #001
See CHANGELOG [0.2.0]
```

---

## 7. Maintenance Commands

### 7.1. Freshness Audit

Periodically scan for stale documentation:

```markdown
grep -n "STALE" PROJECT_CONTEXT.md
grep -n "VERIFIED: 2024" PROJECT_CONTEXT.md  # Old dates
grep -n "AI-TODO" *.md
```

### 7.2. Completed Task Pruning

Keep `TASK.md > Recently Completed` to last 10-15 items.  
Archive older items to `CHANGELOG.md` if notable.

### 7.3. Session History Rotation

Keep last 5 sessions in `PROJECT_CONTEXT.md > 9.2 Session History`.  
Summarize and archive older sessions.

---

## 8. Template Customization

### 8.1. Project Type Adaptations

| Project Type | Customize |
|:-------------|:----------|
| **GUI App** | Expand UI Layer, add component map |
| **CLI Tool** | Replace UI with Commands section |
| **API Server** | Add Endpoints, Auth, Rate Limits sections |
| **Library** | Add Public API, Deprecation Policy |
| **Scripts** | Minimize structure, focus on Quick Context |

### 8.2. Scale Adaptations

| Project Size | Guidance |
|:-------------|:---------|
| **Small (<10 files)** | Single PROJECT_CONTEXT.md may suffice |
| **Medium (10-50 files)** | Full template set |
| **Large (50+ files)** | Consider splitting by subsystem |

---

## 9. Quick Reference Card

```
MARKERS:
  [VERIFIED: date]  [STALE]  [AI-TODO]  [DEPRECATED]
  
TASKS:
  [ ] pending  [/] active  [x] done  [!] blocked  [~] hold  [-] cancelled
  
PRIORITY:
  P0 critical  P1 high  P2 medium  P3 low
  
RISK:
  LOW (read-only)  MED (recoverable)  HIGH (destructive)
  
FILES:
  PROJECT_CONTEXT.md  →  Architecture & state
  TASK.md             →  Work tracking
  CHANGELOG.md        →  History
  CONVENTIONS.md      →  This guide
```

---

<!-- 
This file should rarely change after initial setup.
Update only when adding new conventions or markers.
-->
