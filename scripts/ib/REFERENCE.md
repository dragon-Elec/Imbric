# ib — Imbric Build Utility Reference

## Entry

```bash
python scripts/ib.py <command> [args]
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
Auto-restart on crash (max 3 attempts, 5s delay).
`ib kill` targets: gradlew, GradleDaemon, KotlinCompileDaemon, com.imbric, compose.devtools.
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
| `ib test --tests X` | Specific class/method |
| `ib test --continue` | Don't stop on first failure |

### Build Utilities

| Command | Description |
|---------|-------------|
| `ib compile` | Compile Kotlin sources (fast check) |
| `ib compile --tests` | Also compile test sources |
| `ib compile --full` | Full build (all tasks except test) |
| `ib generate` | Regenerate GIO bindings (stops daemon first) |
| `ib clean` | Remove `build/` (stops daemon first) |
| `ib clean --deep` | Also remove `.gradle/caches` |
| `ib clean --bindings` | Only remove `build/native-gen` |
| `ib doctor` | Check JDK 25, JAVA_HOME, Gradle 9.6.1, GIR files, bindings |
| `ib exec <cmd...>` | Run any command with ib's output filter |
| `ib audit [file]` | Validate Kotlin public API against context docs |
| `ib history` | (stub — not implemented) |

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
| `ib lint --fix` | Auto-fix issues where possible |
| `ib lint --strict` | Fail on warnings |

## OutputFilter

Shared by `dev`, `hot`, `run`, `exec`, `compile`, `bench`, `lint`. Behavior:
- Task progress → `.` on stderr
- Noise (config cache, UP-TO-DATE, downloads) → suppressed
- Errors/exceptions → full block shown
- Warnings → collected, summary at end
- BUILD SUCCESSFUL/FAILED → shown with elapsed time

## ProcessManager

Pattern-matches via `pgrep -a -f`. Self-excludes current PID.
Kill order: SIGTERM first, SIGKILL survivors after 1s.
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
