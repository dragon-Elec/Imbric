# OpenCode LSP Configuration Guide (Linux, No venv)

> **Context:** This guide documents the complete troubleshooting process for getting Pyright/basedpyright to work correctly with PySide6, GIO/GLib, and other C-extension libraries in OpenCode on Linux without virtual environments.

---

## The Problem

When using OpenCode's built-in Pyright LSP with PySide6 installed globally (`pip install --user`), the language server floods the console with false positives:
- `Cannot access attribute "FramelessWindowHint" for class "type[Qt]"`
- `Cannot access attribute "scanner" for class "Property"`
- `"Gio" is unknown import symbol`
- `Argument of type "FileMonitor" cannot be assigned to parameter "backend"`

These are **not real errors**. They occur because:
1. **PySide6 uses dynamic C++ bindings** — Static analyzers cannot introspect `.so` files without explicit `.pyi` stubs.
2. **GIO/GLib are dynamic C-bindings** — They have no static type stubs at all.
3. **Pyright's default fallback interpreter** doesn't find user-local `site-packages` (`~/.local/lib/python3.12/site-packages`) when OpenCode spawns it as a background daemon.

---

## What DID NOT Work

### 1. Complex `opencode.json` with `initialization` blocks
```json
{
  "lsp": {
    "pyright": {
      "initialization": {
        "python": { "pythonPath": "/usr/bin/python3" },
        "analysis": { "extraPaths": ["..."] }
      }
    }
  }
}
```
**Why it failed:** OpenCode's schema validator **requires** a `command` array when defining an LSP entry. Without it, the app crashes on startup with `ConfigInvalidError: Invalid input lsp`.

### 2. `opencode.json` with `env` approach
```json
{
  "lsp": {
    "pyright": {
      "env": { "PYTHONPATH": "/home/ray/.local/lib/python3.12/site-packages" }
    }
  }
}
```
**Why it failed:** While valid schema-wise, it didn't resolve the PySide6 false positives. The LSP still couldn't resolve Qt metaclass attributes.

### 3. `pyrightconfig.json` with `executionEnvironments`
```json
{
  "executionEnvironments": [{
    "root": ".",
    "extraPaths": ["..."]
  }]
}
```
**Why it failed:** Partially worked for the CLI, but the OpenCode agent's internal LSP checker ignored it entirely due to a workspace root mismatch.

### 4. `pyrightconfig.json` with `typeCheckingMode: "off"`
**Why it failed:** Too aggressive. It silenced false positives but also hid real syntax errors and undefined name errors.

### 5. CLI `opencode debug lsp diagnostics` returning `{}`
**Why it happened:** The CLI has a **hardcoded 3-second timeout**. Pyright takes longer than 3 seconds to parse PySide6 + site-packages, so the CLI gives up and returns empty results. **This does NOT mean the LSP is clean.**

### 6. Killing processes without full restart
```bash
pkill -f "pyright-langserver"
```
**Why it failed:** OpenCode's process manager holds zombie/stopped processes (status `Tl`). A full OpenCode restart is required to flush the process cache and spawn the new binary.

### 7. Standard `pyright` with PySide6
**Why it failed:** Pyright fundamentally cannot resolve PySide6's dynamic C-extension attributes (`Qt.FramelessWindowHint`, `@Property` decorators) without thousands of lines of custom `.pyi` stubs.

---

## What DID Work

### 1. Install `basedpyright` (Pyright fork)
```bash
pip install --user --break-system-packages basedpyright
```
**Why it worked:** Basedpyright is a community fork designed to handle dynamic Python patterns better than upstream Pyright. It's more tolerant of C-extension libraries.

### 2. Simple `opencode.json` with `command` override
```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": {
    "pyright": {
      "command": ["/home/ray/.local/bin/basedpyright-langserver", "--stdio"]
    }
  }
}
```
**Why it worked:** This is the **only valid way** to override the built-in LSP in OpenCode. The `command` array is mandatory. No `initialization` blocks needed.

### 3. `pyrightconfig.json` with targeted rule suppression
```json
{
  "include": ["."],
  "exclude": ["**/__pycache__", ".git"],
  "pythonVersion": "3.12",
  "pythonPlatform": "Linux",
  "extraPaths": [
    "/home/ray/.local/lib/python3.12/site-packages",
    "/usr/lib/python3/dist-packages"
  ],
  "typeCheckingMode": "standard",
  "useLibraryCodeForTypes": true,
  "reportMissingTypeStubs": false,
  "reportAttributeAccessIssue": "none",
  "reportArgumentType": "none",
  "reportOptionalMemberAccess": "none",
  "reportUnusedImport": "information",
  "reportUnusedParameter": "information"
}
```
**Why it worked:** This suppresses **only** the PySide6/GIO-specific noise while keeping real syntax errors, undefined names, and import resolution active.

### 4. Full OpenCode restart after config changes
**Why it worked:** OpenCode reads `opencode.json` strictly at boot. The LSP process must be completely flushed and respawned to pick up new configurations.

---

## Key Discoveries

| Discovery | Details |
|-----------|---------|
| **OpenCode LSP Schema** | If you define an LSP entry in `opencode.json`, you **MUST** provide a `command` array. Partial configs crash the app. |
| **Config Precedence** | `pyrightconfig.json` > `opencode.json` for analysis settings. Use `opencode.json` only for `command` overrides. |
| **Agent Tool Isolation** | The LSP diagnostics shown in the agent's `edit`/`write` tool run in a cached/isolated environment. They may not reflect the live workspace state. |
| **CLI Timeout Bug** | `opencode debug lsp diagnostics` has a 3-second timeout. It returns `{}` for large projects even when errors exist. |
| **PySide6 Limitation** | No static analyzer can resolve PySide6's dynamic C-extensions without explicit `.pyi` stubs. Suppression is the only practical solution. |
| **Zombie Processes** | `pkill` doesn't fully terminate OpenCode's LSP. Full app restart is required. |
| **Basedpyright vs Pyright** | Basedpyright is more tolerant of dynamic patterns but shares the same fundamental C-extension limitation. |

---

## Quick Setup Checklist (For New Projects)

1. **Install basedpyright:**
   ```bash
   pip install --user --break-system-packages basedpyright
   ```

2. **Create `opencode.json` in project root:**
   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "lsp": {
       "pyright": {
         "command": ["/home/ray/.local/bin/basedpyright-langserver", "--stdio"]
       }
     }
   }
   ```

3. **Create `pyrightconfig.json` in project root:**
   ```json
   {
     "include": ["."],
     "exclude": ["**/__pycache__", ".git"],
     "pythonVersion": "3.12",
     "pythonPlatform": "Linux",
     "extraPaths": [
       "/home/ray/.local/lib/python3.12/site-packages",
       "/usr/lib/python3/dist-packages"
     ],
     "typeCheckingMode": "standard",
     "useLibraryCodeForTypes": true,
     "reportMissingTypeStubs": false,
     "reportAttributeAccessIssue": "none",
     "reportArgumentType": "none",
     "reportOptionalMemberAccess": "none",
     "reportUnusedImport": "information",
     "reportUnusedParameter": "information"
   }
   ```

4. **Restart OpenCode completely.**

5. **Verify LSP is active:**
   ```bash
   ps aux | grep langserver | grep -v grep
   # Should show: basedpyright-langserver --stdio
   ```

6. **Test with intentional syntax error:**
   Remove a `:` from any function definition. The LSP should report exactly one error: `Expected ":"`. Zero false positives.

---

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| `ConfigInvalidError: Invalid input lsp` | You're missing the `command` array in `opencode.json`. Add it. |
| CLI returns `{}` for diagnostics | This is the 3-second timeout bug. Use `opencode debug lsp diagnostics --log-level DEBUG` or make a small edit to trigger the agent tool's LSP. |
| False positives still appear after restart | Kill all langserver processes: `pkill -f "langserver"`, then restart OpenCode. |
| `basedpyright-langserver: command not found` | Install it: `pip install --user --break-system-packages basedpyright` |
| LSP not picking up `pyrightconfig.json` | Ensure it's in the **project root** (same directory as `opencode.json`). |

---

## Notes for Future Reference

- **Do NOT use `opencode.json` for `initialization` blocks** — They are highly sensitive to schema validation and often crash the app.
- **Do NOT rely on CLI diagnostics for large projects** — The 3-second timeout makes them unreliable.
- **Do NOT try to write custom `.pyi` stubs for PySide6** — It has thousands of classes. Suppression is the only practical approach.
- **Always restart OpenCode after changing `opencode.json`** — It reads config strictly at boot.
- **The agent tool's LSP checker may show stale errors** — Trust the CLI `opencode debug lsp diagnostics` output over the tool payload for final verification.
