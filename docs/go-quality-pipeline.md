# Go Quality Pipeline — Agent Reference

> How to assess Go code quality using desloppify + Go toolchain together.

---

## 1. Design Decision: Desloppify Is Additive to Go Linting

Desloppify's Go plugin has 14 detectors covering concurrency, runtime safety, security, and code smells — issues that standard Go linters don't catch. The plugin does **not** reimplement checks already provided by `staticcheck`, `stylecheck`, `errorlint`, `revive`, or `gosec`.

**Desloppify's role:**
- Runtime safety detectors (nil map writes, unbuffered signals, time.Tick leaks, fire-and-forget goroutines)
- Security detectors (SQL injection, command injection, path traversal)
- Code smell detectors (panic in library code, dogsledding, too many params, yoda conditions, etc.)
- Architectural analysis (god packages/structs, dependency cycles, coupling, complexity signals, duplication)
- Cross-language health scoring with tier-weighted dimensions
- Persistent state tracking (open/fixed/wontfix/false_positive lifecycle)

**Go toolchain's role:**
- Naming conventions (`stylecheck`: initialisms, getter prefixes, receiver names, stutter, error var naming)
- Error handling style (`staticcheck`/`errorlint`: error string casing, wrapping, comparison, return position)
- Control flow (`staticcheck`/`revive`: unnecessary else, defer in loop)
- Weak crypto (`gosec`)
- Type-aware correctness (copylocks, struct tags, unreachable code, unchecked errors, dead code)
- Data-flow and context propagation analysis

**The agent orchestrates both.** Neither tool needs to subsume the other.

---

## 2. The Pipeline

When assessing Go code quality, run these steps in order:

### Step 1 — Desloppify scan

```bash
desloppify scan --path .
```

Runs all detectors + architectural analysis. Produces scored findings with state tracking.

### Step 2 — golangci-lint

```bash
golangci-lint run ./...
```

Runs `staticcheck`, `stylecheck`, `revive`, `gosec`, `errorlint`, and other linters in a single pass. Catches naming, error handling, control flow, weak crypto, and type-aware issues that desloppify doesn't cover.

If `golangci-lint` is not available, fall back to standalone tools:

```bash
staticcheck ./...    # type-aware checks
go vet ./...         # baseline correctness
```

### Step 3 — Desloppify action list

```bash
desloppify status
desloppify next
```

View the prioritized action list. `status` shows the health score and finding breakdown. `next` recommends the highest-impact item to fix.

---

## 3. What Only Desloppify Covers (Go)

| Detector | What it catches |
|---|---|
| `panic_in_lib` | `panic()` in non-main packages |
| `fire_and_forget_goroutine` | Goroutines without synchronization |
| `time_tick_leak` | `time.Tick` in non-main (leaks ticker) |
| `unbuffered_signal` | `signal.Notify` on unbuffered channel |
| `single_case_select` | `select` with one case (should be plain send/recv) |
| `nil_map_write` | Write to uninitialized map |
| `string_concat_loop` | String concatenation in loops (use `strings.Builder`) |
| `yoda_condition` | Reversed comparison operands |
| `dogsledding` | 3+ blank identifiers on LHS |
| `too_many_params` | Functions with >5 parameters |
| `todo_fixme` | TODO/FIXME/HACK comments |
| `sql_injection` | String interpolation in SQL queries |
| `command_injection` | Unsanitized input in `exec.Command` |
| `path_traversal` | Unsanitized path construction |

## 4. What Only Go Tooling Covers

| Check | Canonical tool |
|---|---|
| Error string casing/punctuation | `staticcheck` ST1005 |
| Error return position | `staticcheck` ST1008 |
| `%w` vs `%v` in `fmt.Errorf` | `staticcheck` / `errorlint` |
| `errors.Is` instead of `==` | `errorlint` |
| Unnecessary else after return | `revive` / `staticcheck` |
| Defer in loops | `staticcheck` / `revive` |
| Initialism casing (ID, URL, HTTP) | `stylecheck` ST1003 |
| Getter `Get` prefix | `stylecheck` / `revive` |
| Package naming conventions | `stylecheck` ST1000 |
| Receiver naming (`this`/`self`) | `stylecheck` ST1016 |
| Weak crypto (MD5/SHA1/DES/RC4) | `gosec` G501/G303 |
| Unchecked errors | `errcheck` / `staticcheck` |
| Dead / unreachable code | `staticcheck` U1000 |
