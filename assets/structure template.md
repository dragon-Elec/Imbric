# [Directory Name] - Module Specification

> **Parent Context:** [Link to Main Architecture Doc]
> **Namespace/Path:** `[project_root]/[directory_name]`
> **Primary Responsibility:** [One sentence summary of what this folder does, e.g., "Handles all database interactions and schema migrations."]

---

## 1. Directory Overview

**Role:**
This directory contains the logic for [explain scope]. It acts as the [layer type, e.g., Data Access Layer / UI Controller / Utility Belt] for the application.

**Dependencies (Inputs):**
*   Imports from: `../[other_dir]` (for [reason])
*   External Libs: `[library_name]`

**Consumers (Outputs):**
*   Used by: `../[ui_dir]`, `../[api_dir]`

---

## 2. File Manifest

| File | Type | Responsibility |
| :--- | :--- | :--- |
| `[filename].py` | [e.g., Class / Script] | [Brief summary] |
| `[filename].py` | [e.g., Interface] | [Brief summary] |
| `[filename].py` | [e.g., Utility] | [Brief summary] |

---

## 3. Code File Deep Dives

### 3.1. `[filename_1].ext`

**Role:**
The [Manager/Controller/Worker] that handles [specific task]. It is responsible for [X] and ensures [Y].

**Key Classes / Functions:**

| Component | Signature | Purpose |
| :--- | :--- | :--- |
| `ClassName` | `class` | Main container for state. |
| `function_name` | `(arg1, arg2) -> RetType` | Calculates [X] based on [Y]. |
| `_private_helper` | `() -> void` | Internal cleanup logic. |

**Critical Logic & Algorithms:**
*   **[Logic Name]:** Explain how a complex function works.
    *   *Step 1:* Checks cache.
    *   *Step 2:* If miss, queries DB.
*   **State Management:** How does it handle data persistence? (e.g., "Stateless," "Singleton," "Instance-based").

**Safety & Error Handling:**
*   Catches `[ExceptionType]` when [Scenario] occurs.
*   **Constraint:** Must never return `null`; returns `EmptyObject` instead.

---

### 3.2. `[filename_2].ext`

**Role:**
[Description...]

**Key Classes / Functions:**
[Table...]

**Critical Logic:**
[Explanation...]

---

## 4. Internal Relationships (The "Glue")

*How do the files inside THIS directory talk to each other?*

*   **`File A` -> `File B`:** `File A` imports `File B` to format dates before saving.
*   **Shared State:** Both `File A` and `File C` read constants from `constants.py` located in this dir.
*   **Circular Dependency Avoidance:** `File D` uses dependency injection to avoid importing `File A`.

---

## 5. Testing & Verification

*   **Unit Test Location:** `tests/test_[directory_name]/`
*   **Key Test Cases:**
    1.  **Happy Path:** [Scenario]
    2.  **Edge Case:** [Scenario]
*   **Mocking Requirements:** When testing this module, `[ExternalService]` must be mocked.

***

## Example Usage

Here is how you would fill this out for the `core/` directory from your Z-Manager project:

# Core - Module Specification

> **Parent Context:** [Z-Manager Architecture]
> **Namespace/Path:** `z-manager/core`
> **Primary Responsibility:** Handles low-level system interactions, kernel I/O, and configuration persistence.

---

## 1. Directory Overview

**Role:**
The "Brain" of the application. It abstracts raw Linux commands and `sysfs` interactions into safe Python functions.

**Dependencies:**
*   OS Commands: `mount`, `swapon`, `modprobe`
*   Python Libs: `subprocess`, `os`, `configparser`

**Consumers:**
*   Used by: `../modules/` (Functional skills), `../ui/` (Interface)

---

## 2. File Manifest

| File | Type | Responsibility |
| :--- | :--- | :--- |
| `os_utils.py` | Utility | Low-level wrappers for shell/file I/O. |
| `zdevice_ctl.py` | Controller | Logic for creating/modifying ZRAM devices. |
| `config.py` | Reader | Parses `zram-generator.conf`. |

---

## 3. Code File Deep Dives

### 3.1. `os_utils.py`

**Role:**
The foundation layer. All interaction with the OS (Shell, Sysfs) must pass through here.

**Key Functions:**

| Component | Signature | Purpose |
| :--- | :--- | :--- |
| `run` | `(cmd: list) -> Result` | Safe wrapper for `subprocess.run`. |
| `check_device_safety` | `(path) -> (bool, str)` | **CRITICAL.** Checks for filesystems on disk. |
| `atomic_write` | `(path, content)` | Writes to temp file, then renames. |

**Critical Logic:**
*   **Safety Check:** Uses `blkid`. If it returns a UUID/Type, the device is flagged as unsafe. Returns `False` to block writeback operations.

---

### 3.2. `zdevice_ctl.py`

**Role:**
Orchestrates ZRAM device lifecycle.

**Key Functions:**

| Component | Signature | Purpose |
| :--- | :--- | :--- |
| `set_writeback` | `(dev, backing, force)` | Complex sequence to attach backing device. |
| `_reconfigure` | `(dev, params)` | Internal helper to write to sysfs. |

**Critical Logic:**
*   **Reconfiguration Order:** When modifying a device, it MUST write `backing_dev` before `disksize`. If done in reverse, the kernel throws `EBUSY`.
*   **Reset Sequence:** `swapoff` -> `reset` (sysfs) -> `reconfigure` -> `mkswap` -> `swapon`.

---

## 4. Internal Relationships

*   **`zdevice_ctl.py` -> `os_utils.py`:** `zdevice_ctl` never calls `subprocess` directly; it calls `os_utils.run()`.
*   **`config_writer.py` -> `os_utils.py`:** Uses `atomic_write` to save config files.
