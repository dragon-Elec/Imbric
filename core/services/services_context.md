Identity: core/services — Stateless utility services: pre/post operation validation, and file search.

Index:
- search/ — SearchEngine implementations + QThread worker for background search.

---

### [FILE: validator.py] [DONE]
Role: Post-operation filesystem verifier. Runs async spot-checks after I/O completes to detect ghost successes.

/DNA/: `validate(job_id, op_type, src, result, success)` -> if enabled and success: `ValidationRunnable(op_type).run()` -> `_VALIDATORS[op_type](src, result)` -> if passed: em:validationPassed | else: print + em:validationFailed

- SrcDeps: core.backends.gio.helpers
- SysDeps: PySide6{QtCore}, gi.repository{Gio}

API:
  - OperationValidator(QObject):
    Signals: validationPassed(job_id, op_type), validationFailed(job_id, op_type, source, expected, actual)
    - validate(job_id, op_type, source, result_path, success) -> None
    - setEnabled(enabled: bool) -> None

!Caveat: `delete` op_type has no validator entry in `_VALIDATORS`; validation is silently skipped for deletes.
!Caveat: Validator uses `_make_gfile` directly — GIO-coupled, not backend-agnostic. Only works for local/GVfs paths.
