# ib — Imbric Build Utility Reference

## Entry

```bash
python3 scripts/ib.py <command> [args]
```

All Gradle invocations use `./gradlew` with `--console=plain` for parseable output.
Output is filtered: noise suppressed, errors expanded, progress shown as dots.

## Commands

### Daemon

| Command | Gradle Target | Background |
|---------|--------------|------------|
| `ib dev` | `run --continuous` | yes (double-fork) |
| `ib hot` | `hotRun --auto --no-configuration-cache` | yes |
| `ib stop` | — | — |
| `ib status` | — | — |
| `ib log [-f] [-n N]` | — | — |
| `ib kill` | — | — |

Daemon PID: `.gradle/imbric-daemon.pid`
Daemon log: `.gradle/imbric-daemon.log`
Auto-restart on crash (max 3 attempts; any exit counts in continuous mode; backoff 5s/15s). Start failure exits 1.
Daemon SIGTERM handler terminates the Gradle child before exit (no orphans).
`ib kill` targets: gradlew, GradleDaemon, KotlinCompileDaemon, com.imbric, compose.devtools — immediate SIGKILL (no grace period); returned PIDs are deduped.
`ib status` shows process count + VmRSS memory per process.

### Run (foreground)

| Command | Gradle Target |
|---------|--------------|
| `ib run` | `run --console=plain` |
| `ib run --hot` | `hotRun --auto --no-configuration-cache --console=plain` |

Cleans orphaned app processes before start. Ctrl+C triggers graceful terminate + cleanup.

### Test

| Command | Description |
|---------|-------------|
| `ib test` | All tests, filtered output (dots = pass, full = fail) |
| `ib test --failed` | Re-runs only the test classes that failed in the previous run |
| `ib test --rerun` | Force test re-execution bypassing Gradle cache (`--rerun-tasks`) |
| `ib test --tests X` | Specific class/method |
| `ib test --continue` | Don't stop on first failure |

### Build Utilities

| Command | Description |
|---------|-------------|
| `ib compile` | Compile Kotlin sources (fast check) |
| `ib compile -w` | Compile and display grouped, compressed compiler warnings (`--warnings`) |
| `ib compile --rerun` | Force compile re-execution bypassing Gradle cache (`--rerun-tasks`) |
| `ib compile --tests` | Also compile test sources |
| `ib compile --full` | Full build (all tasks except test) |
| `ib generate` | Regenerate GIO bindings (stops daemon first) |
| `ib clean` | Remove `build/` (stops daemon first) |
| `ib clean --deep` | Also remove `.gradle/caches` |
| `ib clean --bindings` | Only remove `build/native-gen` |
| `ib doctor` | Check JDK 25, JAVA_HOME, Gradle 9.6.1, GIR files, bindings |
| `ib exec <cmd...>` | Run any command (raw output passthrough, no filtering) |
| `ib audit [file]` | Validate Kotlin public API against context docs |
| `ib history` | (stub — not implemented, exits 0) |

### Process Management

| Command | Description |
|---------|-------------|
| `ib status` | Show detailed process status with memory and uptime |
| `ib status --verbose` | Show full command lines |
| `ib processes` | Show all running Gradle/Kotlin/Imbric processes |
| `ib processes --kill` | Kill all processes after showing |
| `ib processes --kill --force` | Force kill (SIGKILL) |
| `ib memory` | Show memory usage of Gradle/Kotlin/Imbric processes |
| `ib memory --verbose` | Show detailed memory breakdown (RSS, PSS, shared, private, swap) |

### Development Tools

| Command | Description |
|---------|-------------|
| `ib bench` | Run benchmarks (default: GioListingBenchmark) |
| `ib bench --tests X` | Run specific benchmark class |
| `ib bench --all` | Run all benchmarks |
| `ib project` | Show project information (git, gradle, structure) |
| `ib project --deps` | Show dependency tree |
| `ib project --tasks` | Show available Gradle tasks |
| `ib lint` | Run code quality checks |
| `ib lint --fix` | (unsupported — prints a note; lint has no auto-fixer) |
| `ib lint --strict` | Fail on warnings |

## OutputFilter

Shared by `dev`, `hot`, `run`, `compile`, `bench`, `lint` (NOT `exec` — arbitrary commands pass through raw). Behavior:
- Task progress → `.` on stderr
- Noise (config cache, UP-TO-DATE, downloads) → suppressed
- Errors/exceptions → full block shown; stack frames compressed (framework frames collapsed to a skip count)
- GLib/GIO native warnings → deduplicated with occurrence counts
- `[PIPELINE]` lines → formatted timeline
- Warnings → collected, summary at end
- BUILD SUCCESSFUL/FAILED → swallowed; each command prints its own single summary line with elapsed time
- Error patterns are line-start anchored: a passing test named `testExceptionPath()` or a mid-line `error:` does not flip error mode

## ProcessManager

Pattern-matches via `pgrep -a -f`. Self-excludes current PID; never signals pid ≤ 1.
`ib kill` = immediate SIGKILL. `ib processes --kill` (no `--force`) = SIGTERM first, SIGKILL survivors after 1s. Returned PID lists are deduped (first-seen order).
Memory: reads `/proc/{pid}/status` VmRSS.

## Examples

```bash
# Quick compile check
ib compile

# Compile with tests
ib compile --tests

# Run specific test
ib test --tests "GioBackendTest"

# Run benchmarks
ib bench

# Check memory usage
ib memory --verbose

# Show project info
ib project --deps

# Run code quality checks
ib lint
```
