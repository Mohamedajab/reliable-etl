# Processing flow

```mermaid
flowchart TD
  A[Daily CSV] --> B[SHA-256 fingerprint]
  B --> C{Succeeded hash exists?}
  C -->|yes| D[Skip safely]
  C -->|no| E[Create RUNNING audit]
  E --> F[Validate header and rows]
  F -->|valid, new ID| G[(transaction_fact)]
  F -->|invalid or duplicate| H[(rejected_record)]
  G --> I{Atomic commit}
  H --> I
  I -->|success| J[SUCCEEDED + counts]
  I -->|error| K[Rollback + FAILED]
```

File hashes prevent accidental replay of renamed files. The transaction ID remains the
business-level uniqueness control across different files. Both are needed: a hash alone
cannot catch the same transaction arriving in a corrected or consolidated extract.

