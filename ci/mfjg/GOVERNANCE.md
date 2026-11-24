# MFJG fork governance

Binding rules for all `mfjg/*` branches of this fork. Owner decision record of
2026-11-12 (recorded on pull request #1), captured here so it survives
independently of any single PR.

## Parity-first

This repository's pull request #1 is the designated parity-evidence source
gating activation of the private TensorZero qualification carrier (recorded
in the private fleet ledger). Track: parity-first — synthetic baseline vs
ARM64 rebuilt candidate must reach parity before any private-infrastructure
activation; no parity means the qualification effort closes with a ledger
note and zero infrastructure spent.

## Portable source only

Binding rule for all `mfjg/*` branches: portable source only — never runner
labels, hostnames, group IDs, socket paths, or evidence artifacts. Evidence
receipts (archive hashes, capture dates, parity results) live outside the
repository, in the ledger or PR records.
