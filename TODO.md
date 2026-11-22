# TODO

## README diagrams

- **`layout_ratchet.png`: a routed edge crosses a sibling edge.** In
  `docs/ratchet_graph.json` the edge `base -> cmp` (`_baseline.json` ->
  "any count different?") is routed and its horizontal leg cuts the vertical leg
  of `cmp -> rose` ("up"). The `crossing` gate does not report it:
  `python -X utf8 plugin-full/skills/excalidraw-diagram/scripts/excalidraw_builder.py scene --from-json docs/ratchet_graph.json -o out/`
  prints no warning. The straight style drew the same crossing, so this is
  not a regression from `edge_style: "orthogonal"`. Two things to settle: why
  `check_arrow_crossings()` misses a routed path against a bus leg, and whether
  `pack()` can route this edge on the other side.

- **`repo_map.png` and `full_architecture.png` show stale counts.** The labels
  were written by hand:
  - `docs/make_repo_map.py:42-44`: "65 tests", "four worked generators",
    "11 promises".
  - `plugin-full/skills/excalidraw-diagram/examples/make_full_architecture.py:45-46`:
    "four generators", "14 promises"; `:98`: "80 tests".

  Today there are 9 `examples/make_*.py`, 44 requirements (`reqmap.py gate`)
  and 183 tests (`test_excalidraw` + `test_mcp_server`). The example is
  shipped, so changing it means a patch bump. Consider computing the counts at
  generation time instead of hard-coding them, so they cannot go stale again.
