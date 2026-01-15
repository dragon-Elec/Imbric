# AI Context System: Interactive Setup Guide

> **For AI:** When initializing this template for a new project, follow this guide.  
> **Do NOT fill the templates automatically.** Ask the user first.

---

## 🚀 Initialization Protocol

When a user introduces this template to a project, present the following questionnaire.
After gathering responses, generate only the selected sections/files.

---

## Step 1: Project Profile Questions

Ask these questions first to understand the project:

```
1. What type of project is this?
   □ Desktop GUI Application
   □ CLI Tool / Scripts
   □ REST/GraphQL API Server
   □ Library / Package
   □ Web Application (Frontend)
   □ Full-Stack Application
   □ Other: ___________

2. What's the primary language/framework?
   (e.g., Python/GTK, TypeScript/React, Rust, Go, etc.)

3. What's the approximate project size?
   □ Small (< 10 files)
   □ Medium (10-50 files)  
   □ Large (50+ files)
   □ Monorepo / Multi-package

4. Does this project interact with the system in privileged ways?
   (e.g., file system writes, network requests, system configs, databases)
   □ Yes — document safety-critical paths
   □ No — minimal safety section needed
```

---

## Step 2: Feature Selection

Present this feature menu with recommendations based on project profile:

```
═══════════════════════════════════════════════════════════════
           CONTEXT SYSTEM FEATURE SELECTION
═══════════════════════════════════════════════════════════════

CORE FILES (Recommended for all projects):
──────────────────────────────────────────
[✓] PROJECT_CONTEXT.md — Main architecture doc
    └─ Minimal version available for small projects

[✓] TASK.md — Work tracking
    └─ Can be simplified to just "Current Focus" section

[ ] CHANGELOG.md — Version history
    └─ Recommended for: libraries, versioned releases
    └─ Skip for: scripts, personal tools

[ ] CONVENTIONS.md — Marker reference guide
    └─ Recommended for: teams, complex projects
    └─ Skip for: solo, small projects (markers explained inline)

───────────────────────────────────────────────────────────────

PROJECT_CONTEXT.md SECTIONS:
────────────────────────────
Select which sections to include:

[✓] 1. Quick Context (ESSENTIAL — always include)
[✓] 2. Project Vision & Goals (RECOMMENDED)
[✓] 3. High-Level Architecture (RECOMMENDED)

[ ] 4. Core Modules Deep Dive
    └─ Recommended for: medium/large projects, complex logic
    └─ Skip for: small projects, simple structure

[ ] 5. Interface/UI Layer  
    └─ Recommended for: GUI apps, APIs, CLIs with many commands
    └─ Skip for: libraries, single-purpose scripts

[ ] 6. Data Flow & Patterns
    └─ Recommended for: async, stateful, complex workflows
    └─ Skip for: stateless, simple utilities

[ ] 7. Safety & Critical Paths
    └─ Recommended for: system tools, privileged ops, data mutations
    └─ Skip for: read-only tools, sandboxed apps

[ ] 8. Configuration & Environment
    └─ Recommended for: apps with config files, env vars, secrets
    └─ Skip for: zero-config tools

[✓] 9. Known Issues & Historical Context (RECOMMENDED)
[✓] 10. AI Session Notes (RECOMMENDED)

[ ] Appendix: Full File Index
    └─ Recommended for: large projects (50+ files)
    └─ Skip for: small/medium projects

───────────────────────────────────────────────────────────────

TASK.md COMPLEXITY:
───────────────────
[ ] Full — All sections (backlog, priorities, session boundaries)
[✓] Standard — Current focus, in-progress, completed, blocked
[ ] Minimal — Just "Current Focus" and "Session Notes"

───────────────────────────────────────────────────────────────

OPTIONAL ADD-ONS:
─────────────────
[ ] RESEARCH.md — For investigation notes during problem-solving
[ ] DECISIONS.md — Architecture Decision Records (ADRs)
[ ] API.md — Public interface documentation (for libraries)
[ ] TESTING.md — Test strategy and coverage notes

═══════════════════════════════════════════════════════════════
```

---

## Step 3: Recommendations by Project Type

Use this table to suggest defaults:

| Project Type | Recommended Selections |
|:-------------|:-----------------------|
| **Small Script** | Quick Context + Vision + Architecture + Known Issues + Minimal TASK.md |
| **CLI Tool** | Above + Core Modules + Config section |
| **GUI Application** | Full PROJECT_CONTEXT.md + Standard TASK.md + CHANGELOG |
| **API Server** | Full PROJECT_CONTEXT.md + Safety + Config + CHANGELOG |
| **Library** | Full PROJECT_CONTEXT.md + CHANGELOG + API.md (optional) |
| **Large/Team Project** | Everything + CONVENTIONS.md + Full TASK.md |

---

## Step 4: Confirm and Generate

After user selects features:

```
Based on your selections, I will create:

📄 PROJECT_CONTEXT.md with sections:
   ✓ Quick Context
   ✓ Project Vision & Goals  
   ✓ High-Level Architecture
   ✓ Core Modules (detailed)
   ✓ Known Issues
   ✓ AI Session Notes

📋 TASK.md (Standard complexity)

📜 CHANGELOG.md

Shall I proceed? I'll need you to answer a few questions to fill in
the project-specific details, or I can scan the codebase first.
```

---

## Step 5: Information Gathering

For selected sections, ask targeted questions:

### Quick Context (Always)
```
- What does this project do? (one line)
- Current development phase? (e.g., "early development", "refactoring auth")
- Any critical context I should know before touching code?
- Any active blockers?
```

### Project Vision
```
- What problem does this solve?
- Any explicit non-goals? (things you deliberately won't do)
- Target users?
```

### Architecture
```
- Shall I scan the codebase to auto-generate the directory tree?
- Any key dependency rules? (e.g., "UI never imports from core directly")
```

### Core Modules (if selected)
```
- Which modules are most critical to document?
- Any complex functions I should analyze in detail?
```

### Safety (if selected)
```
- What operations modify system state?
- Any privilege escalation (sudo, pkexec)?
- What validations must happen before destructive operations?
```

### Config (if selected)
```
- Where are config files located?
- Any environment variables required?
- Build/run commands?
```

---

## Step 6: Auto-Population Offer

```
Would you like me to:

[A] Scan the codebase and auto-populate what I can
    └─ I'll analyze files, extract structure, identify patterns
    └─ You review and correct my findings

[B] Start with empty templates
    └─ You fill in manually or dictate section by section

[C] Hybrid — I scan, you confirm each section before I write

Recommendation: Option [A] or [C] for faster setup
```

---

## AI Behavior Notes

### DO:
- Present options clearly with recommendations marked
- Explain WHY each section might be useful or skippable
- Offer to scan codebase before asking detailed questions
- Generate only what the user selected
- Mark auto-populated sections with `[AI-GENERATED: verify]`

### DON'T:
- Auto-create all files without asking
- Assume project type — ask first
- Over-document small projects
- Under-document safety-critical projects

---

## Quick Setup Presets

For users who want fast setup, offer these presets:

```
PRESET A: "Minimal Context" (5 min setup)
├── PROJECT_CONTEXT.md (Quick Context + Architecture only)
└── TASK.md (Minimal)

PRESET B: "Standard Project" (15 min setup) ⭐ RECOMMENDED
├── PROJECT_CONTEXT.md (Sections 1-3, 8-10)
├── TASK.md (Standard)
└── CHANGELOG.md

PRESET C: "Full Documentation" (30+ min setup)
├── PROJECT_CONTEXT.md (All sections)
├── TASK.md (Full)
├── CHANGELOG.md
└── CONVENTIONS.md
```

---

<!-- 
After setup is complete, this file can be:
1. Deleted (if user prefers cleaner structure)
2. Kept as reference for future re-configuration
3. Moved to .archive/ folder
-->
