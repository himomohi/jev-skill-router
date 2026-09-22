---
name: csv-profile
description: "Profile CSV files locally: missing values, duplicate rows, columns, encodings and data quality. CSV 결측 중복 데이터 품질 검사."
---

# CSV profiling

Read the file locally; do not upload its rows to an external service. Confirm its delimiter and encoding.
Use the bundled scripts/profile_csv.py through the host's normal command runner after checking its source. The router itself never runs it.
Example: python scripts/profile_csv.py /absolute/path/to/input.csv
The script reports headers, row count, missing cell counts and duplicate row count. It does not modify the input file.
For large or sensitive datasets, inspect the file size and access permissions first. The included script stores distinct rows in memory, so do not use it for huge files without adapting it.
Summarize data quality separately from domain-specific correctness; counts alone cannot validate business meaning.
