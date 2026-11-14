# Worked examples: the shapes a diagram takes

Each case below is a mistake that makes a diagram unreadable, followed by the clearer
layout to use instead. Read the one that matches your subject before you plan. SKILL.md
carries the rules these examples illustrate; the coordinates here are starting points
for your grid table, not fixed values.

## Diagramming a repo's architecture (the canonical recipe)

Produce **ONE** scene of **stacked regions**. Each opens with a section title (free text,
24px, bold meaning) placed 80px below everything drawn so far. Include a region **only
when its condition holds**, in this order:

| Region | Include when… | Draw it as |
|---|---|---|
| **1. STRUCTURE** | always | role-coloured boxes in a row or grid, inside one frame |
| **2. WORKFLOW** | the repo has a pipeline, run order or algorithm | a left-to-right band of steps; decisions as diamonds; feedback routed under the band. One labelled lane per tool if the repo bundles several |
| **3. INTEGRATION** | external systems, CI, or a loop invoke it or connect to it | boxes plus labelled arrows: entry points, external systems, state |
| **4. MODES / VARIANTS** | it has modes, strategies or variants of one flow | one framed column per mode |
| **5. MODEL / RUNNERS** | parts run on different models, workers or runtimes | a group, then an arrow, then a runtime box |
| **6. DATA / SCHEMA** | it produces a core record or output shape | a record box plus satellite boxes for enums and annotations |

Then ONE legend (colour = role) and ONE glossary decode the whole poster.

**Colour discipline across regions:** the single legend must decode every region, so each
*distinct* meaning gets its own colour. Two regions must not reuse one colour for
different roles. With nine palette colours, merge only roles that are genuinely the same.

**Depth comes from structure, never from cramming.** Show the true flow with the fewest
nodes that tell it. When a region would need more than ~20 nodes, add another lane or
region; never shrink text.

## Tips

- **Short labels.** Two or three words per box; detail goes in a caption beneath.
- **One reading direction** per region.
- **Colour by role**, consistently, never decoratively.
- **Dashed arrows** for feedback, optional and skip paths; solid for the main flow.
- **Reflect reality.** Name the real files, scripts and functions.
- **Font and style.** `fontFamily: 2` with `roughness: 0` is the most readable default.
  Use `fontFamily: 1` with `roughness: 1` only when a sketchy whiteboard look is asked for.

## ❌ → ✅ variants

### 1 · Repo architecture

❌ One region of 30 boxes, one per file, arrows everywhere, no legend, no subtitle.
✅ The stacked regions above: role colours, one legend and one glossary, every
self-check clean.

### 2 · Pipeline / data flow

❌ Boxes at guessed x positions that drift into each other.
✅ A row on the column rule. All boxes in the band share one height; with width `w`,
`x[i+1] = x[i] + w + gap`, where `gap ≥ 80`, or the label width plus 76 for a labelled
arrow. Chain one arrow from each box to the next.

### 2b · Multi-tool repo workflow

❌ A repo that bundles three tools drawn as one pipeline, which hides two of them.
✅ One band per tool, each with a caption above it ("api: takes the request, writes the
record"), stacked 60px or more apart inside the WORKFLOW region. A single-tool repo keeps
one band.

### 3 · Parallel agents (the #1 spaghetti source)

❌ An arrow from the dispatcher to each of N workers and from each worker to the merge,
which makes 2N crossing lines.
✅ The workers in a grid (columns 40px apart, rows 40px apart) inside ONE frame with
24px padding and a caption ("9 parallel sub-agents"). Draw ONE arrow from the dispatcher
to the frame and ONE from the frame to the merge.

### 4 · Decision / branch

❌ A rectangle for the choice, with unlabelled branches.
✅ A diamond (it needs about 1.4× the width of a rectangle with the same text) with
labelled branches: `yes` solid, `no` dashed.

### 5 · Feedback loop

❌ A right-to-left arrow drawn straight back across the band, through every box between.
✅ An unbound dashed grey arrow with four points:
1. down from the bottom centre of the source;
2. along a line 70px below the band;
3. back to under the target;
4. up into the target's bottom centre.
Put its label on that bottom line.

### 6 · "Explain how X works"

❌ An insider's poster: file names in every box, jargon unexplained, colours with no key.
The diagram is accurate and teaches nothing.
✅ A teaching diagram read top to bottom:
- a 32px title;
- a subtitle that says what the thing is and how to read the diagram ("Read top to bottom.
  Every special word is explained in the Glossary at the bottom.");
- one region per idea (THE PROBLEM IT SOLVES, HOW YOU USE IT, WHAT'S INSIDE, WHERE IT RUNS),
  with everyday words in the boxes;
- a legend and a glossary that decode every colour and term.

### 7 · Timing / waveform

❌ Each level change drawn as a bound arrow between tiny boxes, giving hundreds of nodes.
✅ One unbound polyline per signal (`endArrowhead: null`), with points on a time grid you
compute: an origin `X0`, a slot width `W` and a band height. Where the level changes,
add a vertical edge at `X0 + i × W`. Draw bus values as boxes that abut on the grid.
Check yourself that every trace stays inside its band, because no self-check sees an
unbound line.

### 8 · Sequence, state and entity-relationship diagrams

- **Sequence:** a participant is a box; its lifeline is an unbound vertical line under
  it. A message is a horizontal unbound arrow between two lifelines (dashed for a reply).
  Messages run strictly downwards, about 58px apart.
- **State machine:** states are rounded boxes and transitions are labelled bound arrows.
  A transition back to an earlier state is routed under, as in variant 5. Every state is
  reachable, and every non-final state has a way out.
- **Entity-relationship:** an entity is a coloured header box over a body box listing its
  columns. A relationship is a bound arrow with no heads, labelled `1 x : N y`. Join a
  lower table at its header, or the line cuts through it.
