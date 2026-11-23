# TODO

## README diagrams

- **`repo_map.png` still raises two gate warnings.**
  `python -X utf8 docs/make_repo_map.py out/` prints both:
  - `[orthogonal]`: the dashed `triggers` connector from `pull request` to the
    CI frame is diagonal.
  - `[focus]`: 7 accent-coloured shapes (the limit is 2) and 5 role fills (the
    limit is 4). The `gate` role paints all five CI jobs plus the test box and
    the `save()` decision.
