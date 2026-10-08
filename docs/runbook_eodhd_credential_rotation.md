# Runbook — rotating the EODHD API key

**Why:** the key was written in plaintext to `backend.log` and has appeared in
a working transcript. Redaction stops recurrence; **only rotation invalidates
the copy that already leaked.**

**Acceptance boundary, narrow and single:**

> The new credential is accepted only when a real EODHD-backed production code
> path authenticates and returns structurally valid current data, after the
> sanctioned backend restart.

A `200`, a green `systemctl`, and a successful `py_compile` all pass with a
dead key. None of them is the proof.

**Standing rules for every step below**

- **Never** echo the key — not to the terminal, a log, shell history, or the
  evidence record. Where two values must be compared, compare them
  **in-process** and emit only booleans. Do not print or persist a
  fingerprint either: a truncated hash is derived credential material, and it
  is not needed to establish the property.
- **Replace** the existing `.env` definition. Never append a second one: with
  duplicate keys the winner depends on the loader, and the two loaders here
  are different (see step 3).
- Restart **only** through `./deploy.sh --backend`. Do not introduce
  `systemctl restart` as a second way to change production state. This is
  classified as a **config-only operational restart**, and `deploy.sh
  --backend` is exactly that path — no pull, no build.

---

## Ordering — install first, revoke after the proof

**Default (preferred): issue → install → restart → prove → revoke.**

Revoking before the new key is proven turns a typo in the replacement into an
avoidable source outage: every EODHD producer fails, with no working
credential to fall back to. Installing first keeps a known-good key live until
the replacement has authenticated.

    0  issue new key (do NOT revoke yet)
    1  locate the .env file
    2  replace the existing value
    3  restart via ./deploy.sh --backend, prove the process is serving
    4  prove both loaders agree AND the AXJO.INDX call returns real data
    5  revoke the old key
    6  record provider-side revocation evidence
    7  confirm no fresh unredacted api_token= logging
    8  sanitise historical logs

**If EODHD's rotation necessarily invalidates the old key the moment a new one
is issued**, this ordering is not available. Then revoke-on-issue at step 0,
accept a short fail-closed window, and record that it was deliberate rather
than an accident — a producer failing in that window is expected, not a
defect, and should not be chased.

Decide which applies **before** touching anything, and write it into the
evidence record.

## Step 0 — provider side

1. Issue a new key in the EODHD dashboard.
2. **Do not revoke the old key yet** — that is step 5, after the proof.
   (Unless the provider forces revoke-on-issue; see the ordering note above.)

---

## Step 1 — locate the file, without printing anything from it

```bash
cd /opt/asx-screener && for f in backend/.env .env; do [ -f "$f" ] && echo "$f: $(grep -c '^EODHD_API_KEY=' "$f") definition(s)"; done
```

Expect exactly one file with exactly `1`. Two definitions in one file, or the
key present in both files, must be resolved before continuing — the two
loaders read different paths and would disagree.

Confirm the interpreter and working directory the service actually uses,
rather than assuming them:

```bash
systemctl show asx-backend -p ExecStart -p WorkingDirectory
```

`WorkingDirectory` is what pydantic's relative `env_file = ".env"` resolves
against. If it is not the directory holding the file found above, the two
loaders are reading different files — stop and resolve that before rotating.

**Measured 9 Oct 2026 on the production host:**

    backend/.env                1 definition
    .env (repo root)            exists, 0 definitions
    WorkingDirectory            /opt/asx-screener/backend
    ExecStart                   /opt/asx-screener/asx-venv/bin/uvicorn

Both loaders therefore resolve to `/opt/asx-screener/backend/.env`, and the
interpreter is `/opt/asx-screener/asx-venv/bin/python` — **not** `backend/venv`,
which an earlier draft of this runbook assumed.

This does not make the step 4 equality check redundant. It proves the paths
agree on disk; step 4 proves the **restarted process** actually loaded the
edited value. Those are different claims, and only the second one fails when a
restart silently serves stale config.

---

## Step 2 — replace the value atomically

Prompted, never on the command line, never in history:

```bash
cd /opt/asx-screener && read -s -p "New EODHD key: " NEWKEY && echo && NEWKEY="$NEWKEY" python3 - <<'PY'
import os, pathlib, tempfile
key = os.environ["NEWKEY"]
p = pathlib.Path("backend/.env")          # adjust to the file found in step 1
lines = p.read_text().splitlines(keepends=True)
hits = [i for i, l in enumerate(lines) if l.startswith("EODHD_API_KEY=")]
assert len(hits) == 1, f"expected exactly one definition, found {len(hits)}"
lines[hits[0]] = f"EODHD_API_KEY={key}\n"
fd, tmp = tempfile.mkstemp(dir=str(p.parent))
with os.fdopen(fd, "w") as fh:
    fh.writelines(lines)
os.chmod(tmp, p.stat().st_mode)           # keep the original permissions
os.replace(tmp, p)                        # atomic within the filesystem
print("replaced in place, one definition, permissions preserved")
PY
unset NEWKEY
```

`os.replace` is atomic, so a reader never sees a truncated file, and the
original mode is carried over — a `.env` that lands world-readable is a new
leak. The `assert` refuses to guess if the file is not in the expected shape.

Confirm the write without revealing it:

```bash
cd /opt/asx-screener && echo "definitions: $(grep -c '^EODHD_API_KEY=' backend/.env)" && echo "non-empty:   $(grep -q '^EODHD_API_KEY=.\+' backend/.env && echo yes || echo NO)" && stat -c '%a %U:%G' backend/.env
```

---

## Step 3 — restart through the sanctioned path, then prove it came back

```bash
cd /opt/asx-screener && ./deploy.sh --backend
```

Process health is a precondition for the boundary proof, not the proof:

```bash
curl -fsS https://asxscreener.com.au/openapi.json | python3 -c 'import sys,json;print("running version:", json.load(sys.stdin)["info"]["version"])'
```

That reads the live FastAPI app object, so it proves the process is serving —
a file on disk cannot satisfy it. Expect the current release version.

---

## Step 4 — the boundary proof

Uses the **production module, the production function, and the production
credential loading**. No hand-built HTTP request, and no manually embedded
token.

The call is `compute.engine.asx_indices._fetch_eodhd_constituents`, chosen
because it is the smallest existing EODHD path that is:

- **one symbol, one GET** — cheap and deterministic
- **read-only** — a pure function returning a `set[str]`; it writes nothing,
  so credential verification never becomes a bulk data mutation
- **semantically assertable** — the ASX 200 has a known size and known
  members, so the response can be checked for meaning rather than status

Run it with the interpreter from step 1:

```bash
cd /opt/asx-screener/backend && /opt/asx-screener/asx-venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, "/opt/asx-screener/backend")
from compute.engine.asx_indices import _fetch_eodhd_constituents, EODHD_API_KEY
from app.core.config import settings

# Compared in-process; only booleans leave this script. No fingerprint is
# printed -- a truncated hash is still derived credential material, and the
# property to establish is "both present and equal", not "which value".
env_key, set_key = EODHD_API_KEY or "", settings.EODHD_API_KEY or ""
print(f"asx_indices_loader_present={bool(env_key)}".lower())
print(f"settings_loader_present={bool(set_key)}".lower())
print(f"loader_values_match={env_key == set_key}".lower())

codes = asyncio.run(_fetch_eodhd_constituents("AXJO.INDX"))
have  = {c for c in ("BHP", "CBA", "CSL") if c in codes}
print(f"constituents={len(codes)}")
print(f"known_members_found={sorted(have)}")

ok = bool(env_key) and env_key == set_key and 150 <= len(codes) <= 250 \
     and len(have) == 3
print("BOUNDARY_PROOF=" + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
PY
```

**Why each assertion is there**

| Assertion | What it rules out |
|---|---|
| `loader_values_match` and both present | the two loaders read different files, or one resolved to nothing. `asx_indices` reads `backend/.env` via `load_dotenv` at import; `settings` reads a path relative to the process CWD. Proving one leaves the other unproven |
| `150 <= len <= 250` | an empty or truncated payload. A refusal often returns valid JSON with no components — which `codes_from_components` turns into an empty set, not an error |
| three known members present | a structurally valid response for the wrong instrument, or a cached placeholder |
| exit status | makes the proof scriptable and keeps "it looked fine" out of the record |

A `FAIL` on `loader_values_match` means the restart did not pick up the file
you edited. Do not proceed.

### What this proof does and does not certify

State this precisely, because it is easy to assert more than was tested:

- **Tested over the network:** the `asx_indices` path — `os.environ` loading
  at import, the production client, a real authenticated EODHD request, and
  semantically valid current data.
- **Tested in-process only:** that the `settings` path resolved *the same
  credential*. It was not exercised against EODHD.
- **Not tested at all:** the behaviour of each individual `settings`-based
  consumer (`commodities`, and anything else reading
  `settings.EODHD_API_KEY`).

This is **sufficient for credential rotation**, because those consumers simply
read `settings.EODHD_API_KEY` and pass it to the provider — if the value is
identical to the one just proven to authenticate, the credential is not what
would break them.

It is **not a behavioural certification of every EODHD consumer.** If a
`settings`-based consumer later fails, this runbook's PASS is not evidence
that its credential is sound for that path; it is evidence that the value it
reads is the same one `asx_indices` authenticated with.

---

## Step 5 — confirm the proof did not re-leak the key

The proof writes to stdout, not `backend.log`, but the restart re-runs the
code path that leaked in the first place. Check by **counting**, so no secret
is handled:

```bash
cd /opt/asx-screener/logs && total=$(grep -c 'api_token=' backend.log); red=$(grep -cE 'api_token=(\*{3,}|REDACTED|\[REDACTED\])' backend.log); echo "api_token occurrences: $total   redacted: $red"
```

`total == red` is the pass. Any gap means an unredacted token is being written
*now*, and the redaction work is incomplete — stop and fix that before step 6,
or you will sanitise a log that immediately refills.

---

## Step 5 — revoke the old key, and record it

Only now, with the replacement proven to authenticate and return real data.

1. Revoke the old key in the EODHD dashboard.
2. Capture evidence: a dashboard record showing the old key revoked and the
   new one active, **with both values masked**.

> **Negative control.** The requirement is that the retired credential no
> longer authenticates. Replaying it would mean handling the leaked secret
> again, which is what this exercise exists to end — so provider-side
> revocation evidence *is* the control. Record it as the control, not as an
> untested assumption.

---

## Step 6 — sanitise the historical plaintext copy

**Only after steps 4 and 5 pass.** Until the new key is proven, the old log is
the evidence of what leaked; destroy it earlier and you lose the record while
possibly still depending on the old credential.

Rotate or purge every file holding the retired key, including rotated and
compressed copies (`backend.log.1`, `backend.log.*.gz`), and any off-box
backup or log shipper that received them. A purge that misses the archives
has not removed the credential.

---

## Evidence to retain (all non-secret)

| # | Evidence |
|---|---|
| — | Which ordering applied, and why (install-first, or forced revoke-on-issue) |
| 0 | New key issued; old key still live at this point |
| 1 | File inventory: exactly one definition, in one file |
| 2 | Post-write check: one definition, non-empty, permissions unchanged |
| 3 | `deploy.sh --backend` output and the live `openapi.json` version |
| 4 | Boundary proof output: the three booleans, constituent count, known members, `BOUNDARY_PROOF=PASS` |
| 5 | Provider record: old key revoked, new key active, both masked |
| 7 | Redaction counts showing `total == redacted` |
| 8 | List of files sanitised, including archives and off-box copies |

Every item is non-secret by construction. The boundary proof emits booleans
rather than fingerprints, so the record can show that the two loaders resolved
to the same credential without containing the credential **or anything derived
from it**.

Record alongside item 4 the scope limit stated in step 4: the network proof
exercised the `asx_indices` path; the `settings` path was proven equal
in-process, not exercised.

---

## Known fragility this exposes

Two loaders reading two paths for one secret is the same shape as the
incident where three jobs died in 1ms because `DATABASE_URL` arrived only via
another module's import-time `load_dotenv`. Step 4 asserts they agree, which
detects the divergence but does not remove it.

Collapsing both onto `settings` is the real fix. It is **out of scope for a
credential rotation** — changing config loading during a rotation would mean
two variables moving at once, and a failure could not be attributed. Raise it
as its own task.
