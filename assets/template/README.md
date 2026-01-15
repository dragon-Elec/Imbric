# AI Project Context Template

A flexible, LLM-optimized documentation system for maintaining project context across AI coding sessions.

---

## Purpose

When working with AI coding assistants on complex projects, context is frequently lost between sessions. This template system provides:

- **Cold-start recovery** — AI can quickly understand project state
- **Continuity** — Session handoffs preserve progress and intent
- **Safety** — Critical paths and dangerous operations are documented
- **Efficiency** — Compressed, scannable format optimized for token usage
- **Customizable** — Choose only the sections your project needs

---

## Files Included

| File | Purpose | Required |
|:-----|:--------|:---------|
| [`SETUP.md`](./SETUP.md) | **AI entry point** — Interactive setup questionnaire | Start here |
| [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) | Architecture, modules, safety, AI notes | Core |
| [`TASK.md`](./TASK.md) | Active work tracking, session boundaries | Core |
| [`CHANGELOG.md`](./CHANGELOG.md) | Change history, version tracking | Optional |
| [`CONVENTIONS.md`](./CONVENTIONS.md) | Marker definitions, workflow guide | Optional |

---

## Quick Start (Interactive)

### 1. Copy Template to Your Project

```bash
cp -r ai-project-context-template/ /path/to/your/project/.context/
# or place at project root
```

### 2. Ask AI to Initialize

Tell your AI assistant:
> "Read SETUP.md and help me configure the context system for this project"

The AI will:
1. **Ask about your project type** (GUI, CLI, API, Library, etc.)
2. **Present feature options** with recommendations
3. **Let you choose** which sections to include
4. **Offer to scan** your codebase to auto-populate
5. **Generate only what you selected**

### 3. Quick Presets (Optional)

If you prefer fast setup, ask for a preset:

| Preset | Time | Best For |
|:-------|:-----|:---------|
| **Minimal** | ~5 min | Scripts, small tools |
| **Standard** ⭐ | ~15 min | Most projects |
| **Full** | ~30 min | Large/team projects |

---

## Manual Setup (Alternative)

If you prefer to fill templates manually:

### Fill in PROJECT_CONTEXT.md

Start with these essential sections:
1. **Quick Context** — Most critical, enables cold starts
2. **Project Vision** — Goals and non-goals
3. **High-Level Architecture** — Directory tree with markers
4. **Known Issues** — Prevent repeated mistakes

### Use TASK.md for Active Work

Update at session start and end:
- "Current Focus" section
- Move tasks between Pending → In Progress → Completed

### Reference CONVENTIONS.md

Use consistent markers:
```
[VERIFIED: 2026-01-15]  — Documentation is current
[STALE]                 — Needs verification
[AI-TODO]               — Requires investigation
P0/P1/P2/P3             — Priority levels
LOW/MED/HIGH            — Risk levels
```

---

## AI Session Workflow

### Session Start
```
1. PROJECT_CONTEXT.md → Read "Quick Context"
2. TASK.md → Read "Current Focus" + "In Progress"
3. Check for [!] Blocked items
4. Set session goals in TASK.md
```

### Session End
```
1. TASK.md → Mark completed [x], write handoff notes
2. PROJECT_CONTEXT.md → Update AI Session Notes (section 9)
3. CHANGELOG.md → Add entries under [Unreleased]
```

---

## Customization

### By Project Type

| Type | Customize |
|:-----|:----------|
| GUI App | Expand UI Layer section, add component details |
| CLI Tool | Replace "UI Layer" with "Commands" |
| API Server | Add Endpoints, Authentication sections |
| Library | Add Public API surface documentation |

### By Scale

| Size | Approach |
|:-----|:---------|
| Small (<10 files) | PROJECT_CONTEXT.md alone may suffice |
| Medium (10-50 files) | Use full template set |
| Large (50+ files) | Consider splitting by subsystem |

---

## Key Design Principles

1. **Human-readable, LLM-optimized** — Tables, markers, and structured sections
2. **Semantic compression** — Remove fluff, use symbols (`→`, `&&`)
3. **Freshness tracking** — `[VERIFIED: date]` and `[STALE]` markers
4. **Layered detail** — Quick scans + deep dives where needed
5. **Session continuity** — Explicit handoff notes and history

---

## Marker Quick Reference

```
STATUS:     [VERIFIED: date]  [STALE]  [AI-TODO]  [DEPRECATED]
TASKS:      [ ] pending  [/] active  [x] done  [!] blocked  [~] hold
PRIORITY:   P0 critical → P3 low
RISK:       LOW (read)  MED (recoverable)  HIGH (destructive)
```

---

## License

This template is provided as-is for use in any project.
