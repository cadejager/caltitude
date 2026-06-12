# Evals for `calendar-from-email`

Two layers, matching the plugin's two kinds of risk:

1. **Deterministic unit tests** for the timezone converter — the one piece of
   real code that can silently corrupt every event if it's wrong.
2. **Behavioral / LLM specs** for the sandboxed reader agent and the
   orchestrator skill — the security-critical parts (prompt-injection
   resistance, allowlist + confirmation gating, dedup) that can't be checked by
   a plain assertion.

```
evals/
├── README.md                 ← this file
├── test_convert_time.py      ← runnable unit tests (layer 1)
├── reader_agent_evals.md     ← 12 cases for email-event-extractor (layer 2)
├── orchestrator_evals.md     ← 12 cases for process-flight-emails (layer 2)
└── fixtures/                 ← sample forwarded-itinerary emails (incl. adversarial)
```

## Layer 1 — running the deterministic tests

Requires only Python 3.9+ (stdlib `zoneinfo`; the plugin's own dependency).

```bash
# from the plugin root
python3 evals/test_convert_time.py            # verbose, all cases
python3 -m unittest -v evals.test_convert_time  # as a module
```

The tests load `scripts/convert_time.py` by path and call its `convert()` /
`parse_input_time()` functions directly — the same code path the CLI uses — so
the assertions are exact. They cover local↔UTC both directions, summer/winter
DST offsets for `America/New_York`, the spring-forward gap and fall-back
ambiguity warnings, the RFC-2822 `Date:` header path, `--tz` being ignored when
the input already carries an offset, the `now` input, invalid timezone / invalid
time handling, and an overnight timezone-crossing red-eye.

A green run looks like `Ran 31 tests ... OK`. If `scripts/convert_time.py`
changes behavior, update the expected values here in the same PR (the values
were derived from the real script, not assumed).

## Layer 2 — using the behavioral specs

These describe inputs and expected behavior for the LLM components; they are not
auto-runnable here. Each `.md` case has **Setup / Expected / Failure**.

### Reader agent (`reader_agent_evals.md`)
For each case: stage the fixture as a Gmail thread (or mock `get_thread` to return
the fixture's contents), dispatch the `email-event-extractor` agent with that
`threadId` and the configured confirmation phrases (its only tool is the
read-only `get_thread`, like in production), and grade the returned JSON against
the case. Cases R8–R12 are prompt-injection tests and should be weighted heavily
— a single failure there is a security breach, not a cosmetic miss.

### Orchestrator (`orchestrator_evals.md`)
Run against a test Gmail + CalDAV (or mocked connectors) using the baseline
config in that file. Verifies the sender allowlist, confirmation gating,
field-level leg validation, deterministic conversion (defer to the script),
dedup on re-run (label and timestamp modes), pagination, and that the
orchestrator never fetches bodies (`get_thread` is the reader's job alone).

### Cross-check
The ISO timestamps asserted in the orchestrator spec (O1, O5/O6, O11) come from
the real converter and line up with `test_convert_time.py`. If you change the
converter, re-derive both.

## Fixtures

`fixtures/*.txt` are realistic forwarded itineraries with full `From:`/`Date:`
headers so they double as orchestrator header inputs. Adversarial fixtures
(`06`–`08`, `12`) carry injection payloads: "ignore previous instructions", a
fake in-body confirmation phrase, a spoofed in-body `From`, and an HTML-comment
smuggled instruction. The reader must treat all of it as inert data.
