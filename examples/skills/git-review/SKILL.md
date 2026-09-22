---
name: git-review
description: "Inspect Git changes and review diffs for bugs, missing tests and accidental secrets. Git diff 코드 리뷰."
---

# Git diff review

Start with git status and the requested diff range. Do not discard, reset, stash, or overwrite user changes.
Read surrounding code for changed functions rather than inferring behavior from isolated diff lines.
Prioritize reproducible correctness and security findings. For each finding, identify location, failing conditions and an actionable fix.
Run relevant existing checks where authorized. State that passing local tests is not proof of a bug-free system.
Never commit API keys or publish private files. Publishing or pushing requires the user's authorization for the target repository.
