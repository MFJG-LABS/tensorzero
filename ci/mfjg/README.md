# MFJG fork qualification

This fork preserves upstream history and the deployed `2026.6.0` source at
`62eb8f63e8ec62018d70420dbf1a8c5d1c026315`. Develop on `mfjg/*` branches; keep
upstream `main` as the comparison point. `baseline.json` records the original
image digest and the seven function names and routing widths used for parity.
It contains no private runtime configuration or credentials.

Before changes are promoted, retain an image archive and its SHA-256 receipt
outside the repository. The initial archive was captured on 2026-11-01 with
SHA-256 `7375da0b4d98fe817033a80d5aa2238bb6934ed7483206b9c2b43e9243a47b21`.
`docker load --input <verified-archive>` can restore image availability; it
does not change a running deployment. Runtime rollback remains a separately
qualified owner operation.

## Synthetic contract gate

```sh
python3 -m unittest discover -s ci/mfjg -p 'test_*.py'
bash ci/mfjg/qualify-gateway.sh '<image>@sha256:<digest>' /new/receipt-directory
```

Both commands require Python 3.11 or newer. The second command needs a Docker
test host with capacity for its bounded synthetic containers and the exact
gateway/provider images already present. It creates its own internal network
and three resource-bounded disposable containers; it binds no host port and
passes no environment credentials. The generated configuration replaces all
real providers with an HTTP fixture, disables database observability and never
mounts production data. Cleanup is limited to the container/network IDs it
created; `cleanup.json` records whether removal succeeded. A synthetic request
cannot reach a cloud provider from that network.

The gate exercises chat and SSE streaming for all seven functions, ordered
fallbacks through each routing slot, usage, a tool call and JSON output. It
checks the actual provider request sequence, not just the final response.
This proves protocol behavior against a controlled provider. It does not
qualify live model quality, production secrets, effective context limits,
provider-specific behavior, cost accounting, or historical database ingestion.
No real-provider test should inherit credentials from an operator shell.

Run the same gate against the preserved image and the exact rebuilt candidate;
retain both image identities, logs and `parity.json`. Compare the receipts.
Neither a passing harness unit test nor an unexecuted workflow is rebuild
qualification.

## Build and release boundary

Synthetic rebuild qualification is carried by the private
[`MFJG-LABS/github-runners-config/.github/workflows/tensorzero-qualification.yml`](https://github.com/MFJG-LABS/github-runners-config/blob/main/.github/workflows/tensorzero-qualification.yml).
Its [operator requirements](https://github.com/MFJG-LABS/github-runners-config/blob/main/docs/tensorzero-qualification.md)
are private; public readers may not have access. The dormant public workflow
has been removed. The public fork keeps upstream `main` as its default and
MFJG development stays on `mfjg/*` branches.

The manual private carrier binds the exact reviewed source SHA and full
`refs/heads/mfjg/...` branch to its separately reviewed carrier SHA on private
`main`. It anonymously fetches the fixed public repository and fails if the
branch no longer resolves to that exact source. Review/admission references
are operator-supplied claims requiring independent verification. Source changes
do not activate execution: private default-branch workflow registration,
restricted runner-group access, a unique placement label, a qualified clean
one-job Linux ARM64 worker with its own disposable Docker daemon and enforced
resource limits, and existing owner authority remain separate prerequisites.

The carrier reuses this reviewed synthetic harness for the original image and
an exact-source candidate built with Cargo `--locked` and the performance
profile. It retains source/build identities, parity and bounded cleanup
receipts in the private run for 14 days; the owner must export accepted
evidence before expiry and supply external deregistration/daemon teardown
proof. A timeout, failed cleanup or missing evidence leaves qualification
incomplete. Dockerfile base tags and apt repositories remain mutable, so this
is source traceability without a bit-identical rebuild claim. The temporary
CI image is never pushed and is not a release. Before publishing a release,
update the workspace/package versions consistently to `2026.6.0-mfjg.N`, run the upstream required Rust
checks and the synthetic gate on the exact revision, and review the final diff.
Publish to `ghcr.io/mfjg-labs/tensorzero-gateway`; deployment must use its
registry digest. Never overwrite or publish under upstream TensorZero tags.
Pin and retain the build base-image identities in release provenance as well.

Keep existing ClickHouse `ModelInference` history intact. A gateway rebuild
does not authorize a schema migration, table rewrite, credential change or
fleet deployment. Historical ingestion compatibility needs a separate
disposable-database test before any database-affecting change.
