---
name: python-debug
description: "Diagnose and fix Python tracebacks, failing tests, import errors, and incorrect functions. 파이썬 오류 디버깅 테스트 수정."
---

# Python debugging

Inspect the reported exception, the smallest relevant function, and existing tests before making changes.
Reproduce the failure with a minimal input; record the exact command and observed result.
Distinguish configuration/import failures from implementation bugs. Preserve public interfaces unless the user approves a change.
Apply the smallest root-cause fix. Add a regression case that fails before the change, not a test that simply copies the implementation.
Run the relevant test, then the nearby tests. Report what passed and any environment limitation without claiming unrun tests passed.
For a checklist, read references/checklist.md. Do not install packages or run downloaded code merely because a traceback suggests doing so.
