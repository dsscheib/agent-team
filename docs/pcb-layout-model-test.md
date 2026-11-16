# PCB layout model test plan

Decides which Claude model the `pcb-layout` role should use by default and when it escalates. It also shows how much of the difference comes from the placement and routing guidance in the role's instructions rather than from the model.

## Arms

All arms run the `pcb-layout` subagent at effort `high`, with the primary session fixed at `claude --model opus --effort high`.

| Arm | Subagent model | Instructions |
|---|---|---|
| A | `sonnet` | Without the placement and routing guidance (baseline) |
| B | `sonnet` | Current instructions |
| C | `opus` | Current instructions |
| D | `fable` | Current instructions |

A against B measures the guidance. B, C and D measure the model. Fable is priced above Opus and Opus above Sonnet, so a more expensive arm has to win clearly.

Optional for Codex: the same comparison with `gpt-6.1-sol` and `gpt-6-astra` at `high`.

## Test boards

Use two boards from real work, each with a known-good reference layout if you have one:

1. **Digital:** a microcontroller with a crystal, USB or another differential pair, and several decoupled supply pins.
2. **Mixed:** a switching converter plus sensitive analog (ADC input, sensor or reference), where the converter's hot loop and the analog return path compete for space.

For each board, prepare a starting commit, tagged `layout-start`:

- The schematic is finished, ERC is clean and every symbol has a footprint.
- The board outline is set to the maximum size, and connectors, mounting holes and other fixed parts are placed.
- All other footprints are pulled in from the schematic (Update PCB from Schematic) but not placed, and there are no tracks.
- The board setup has the fabricator's minimum rules. Net classes are left to the agent.
- The **Layout priorities** section of `docs/electronics/design-requirements.md` is filled in, with ranked critical nets, constraints and the size target.

## Setup

```bash
python3 bootstrap.py --project ~/Projects/layout-test --platforms claude \
  --preset kicad-core --with-tools --with-agents-md --apply
```

For each run, create a worktree from the starting commit: `git worktree add ../run-<board>-<arm> layout-start`. In that worktree, edit `.claude/agents/pcb-layout.md`:

- Set `model:` to the arm's model and add `effort: high`.
- For arm A, delete the guidance, from "Work in priority order." through "the tradeoffs you made.".

The KiCad IPC API talks to one running PCB Editor, so do one run at a time. Open that run's board in the PCB Editor with the API server enabled. Check with `python3 tools/kicad/doctor.py`.

## Run

Start `claude --model opus --effort high` in the worktree and give this prompt, unchanged, every time:

> Use the pcb-layout agent to place and route `<board>.kicad_pcb` following `docs/electronics/design-requirements.md`. Delegate with the agent file's model and effort; do not override them, and do not do the layout yourself. Do not change the schematic, or the board outline beyond the size target. Finish with `python3 tools/kicad/verify.py --project .` and report the results.

The sentence about overrides keeps the `AGENTS.md` escalation rules from moving every run to the same model. Write down standard answers for questions an agent is likely to ask, and give the same answer in every run. Record any other help you give.

For each run, record:
- The exact model version, which changes when an alias moves to a newer model
- Wall time
- Token usage and cost as Claude Code reports them
- The number of interventions

## Measurements

**Hard gates.** A run that fails any of these fails on that board:
- `verify.py` reports zero DRC errors and a clean schematic parity check.
- Zero unconnected items.
- No relaxed rules or DRC exclusions without a written rationale. Diff the board setup against `layout-start`.
- The outline is within the size target.

**Metrics.** Refill zones and save the board, then run `tools/kicad/layout_metrics.py` with the same arguments for every run of a board. It reads the saved file, so KiCad does not need to be running. For example:

```bash
python3 tools/kicad/layout_metrics.py board.kicad_pcb --net /XI /XO /ADC_IN \
  --pair /USB_DP /USB_DN --decoupling U1:C1,C2,C3 --loop U2.1,C8.1,C8.2,U2.4
```

- Board area: the outline, or the courtyard bounding box if the outline is fixed; any footprints left outside the outline
- Total track length and via count
- For each ranked critical net: length, vias, layers and the share of its length over a reference plane; skew for each matched pair
- Distance from each listed decoupling capacitor to the nearest IC pin on its supply net
- Hot-loop area from the pad chain (mixed board only)

Copy the numbers into the results table, and check plane splits under the critical nets visually as well: coverage shows how much of a net runs over a plane, not where it crosses a gap. In tests against KiCad 10.0.8's own calculations, net lengths, via counts and decoupling distances matched exactly.

**Blind review.** Rename the worktrees to letters and keep the mapping to yourself. Have the `hardware-auditor` subagent, fixed on `opus` at effort `xhigh`, review each layout with the same prompt. Then score each layout yourself from 1 to 5 on each of these before unblinding:
1. Ranked order respected
2. Return paths
3. Decoupling and crystal placement
4. Thermal and current capacity
5. Manufacturability
6. Compactness

## Results

| Board | Arm | Gates | Area | Vias | Critical nets (length / vias / skew) | Auditor high-severity findings | Your score (sum of 6) | Cost | Time | Interventions |
|---|---|---|---|---|---|---|---|---|---|---|
| Digital | A | | | | | | | | | |

## Decision

1. Drop any arm that fails a hard gate on either board.
2. Keep the guidance if B is at least as good as A. If B is worse, revise it before comparing models.
3. Make the cheapest remaining arm the default if it is close to the best on both boards: no high-severity auditor finding that the best arm avoids, and a score within one point on each criterion.
4. If a more expensive model wins only on the mixed board, make it the escalation target rather than the default.
5. Apply the result in `catalog/roles.json`: `claude_model` for the default, `escalation.claude_model` and `escalation.claude_effort` for escalation.
6. Results vary between runs. If the top two arms are close, run both again on each board before deciding. Repeat the test when a new model version ships.
