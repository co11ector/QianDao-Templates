# Private QianDao CI

The QianDao application (`co11ector/QianDao`) and the Cookie Extractor
(`co11ector/QianDao-Cookie-Extractor`) are private repositories. GitHub Actions
minutes on private repositories are metered; when the account allowance is zero,
GitHub rejects every job before the first step runs. The public template
repository is not metered, so `.github/workflows/private-gates.yml` runs the two
private repositories' gates there.

## Credentials

The bridge uses two GitHub deploy keys:

| Repository | Secret in `QianDao-Templates` | Permission |
| --- | --- | --- |
| `co11ector/QianDao` | `QIANDAO_READ_KEY` | read-only deploy key |
| `co11ector/QianDao-Cookie-Extractor` | `QIANDAO_EXT_READ_KEY` | read-only deploy key |

Each key belongs to exactly one repository. Neither key can push, create
releases, change settings, or call the REST API. No personal access token is
used by the workflow.

To rotate a key, add a new read-only deploy key with `gh repo deploy-key add`,
replace the matching secret with `gh secret set`, run the workflow, then remove
the old deploy key.

## Scheduling and result state

The workflow polls the private `main` branches every 15 minutes and can also be
started manually. The exact commit SHA is checked out for the gate run.

After every gate succeeds, a small Actions cache entry keyed by that SHA is
written. Later polls skip a commit that already passed. A failed commit is not
cached and is retried on the next poll. Manual dispatch accepts `force=true` to
rerun both repositories anyway.

## Visibility boundary

The source stays in the private repositories and is never committed to this
repository. However, workflow logs and run metadata for this public repository
are public. The workflow therefore:

- never uploads private build artifacts;
- never prints the deploy keys or other secrets;
- uses `--redact` for gitleaks findings;
- runs only from `master`/schedule/manual dispatch, not from pull requests, so
  repository secrets are not exposed to untrusted fork code.

A private-repository CI setup on self-hosted runners remains the only way to
keep test logs private. Do not add one to this workflow without revisiting the
visibility boundary.

## Gates

The main repository runs the same gates as its private workflow:

- dependency lock verification, complexity, Python compilation, Jinja
  compilation, and Python dependency audit;
- pytest on Python 3.11, 3.12, and 3.13;
- MariaDB schema migration tests;
- Compose configuration validation;
- front-end reproducible build, browser-bridge tests, and production audit;
- desktop, tablet, and mobile Playwright smoke tests;
- Docker image build and HTTP/SQLite smoke checks;
- full-history gitleaks scan with redaction.

The extension runs `npm ci`, `npm run check`, and
`npm audit --audit-level=high`.
