---
id: REQ-DATAMODEL-916
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A keys-only table joining two: bridge or factless fact

## Description
> A table of only keys that joins two tables is either a bridge, a many-to-many link, or a
> factless fact, an event with nothing to measure. Structure alone cannot tell them apart, so
> the rules read what the table's name says and what it joins, and where they find nothing
> the answer stays a close call and says so.

Every bullet below is binding.
- A keys-only table that joins two tables is a factless fact when its name says an event, such as enrollment, attendance or booking.
- A keys-only table that joins two tables is a factless fact when one of the two is a date table, such as a calendar.
- A keys-only table that joins two tables is a bridge with more confidence when its name says a link, such as `map` or `xref`.
- With none of these hints the table stays a bridge at low confidence, and its reason names the factless fact as the alternative.
- Each hint is written into the reason, so the call can be checked.

## Cases
CASE-1 — no hint, a close call
  Given  a keys-only table joining two tables, named for neither an event nor a link
  When   `classify_tables()` is run
  Then   it is a bridge with a confidence below twenty percent

CASE-2 — an event's name
  Given  a keys-only table named `course_enrollment` joining two tables
  When   `classify_tables()` is run
  Then   it is a fact, and the reason says its name says an event

CASE-3 — a date table among the two
  Given  a keys-only table joining a student table and a calendar
  When   `classify_tables()` is run
  Then   it is a fact, and the reason names the calendar as a date table

CASE-4 — a link's name
  Given  the first table with `_map` added to its name
  When   `classify_tables()` is run
  Then   it is a bridge with more confidence than the first, and the reason says its name says a link

## Context
**Notes**
- Each hint adds three points, the weight of a name prefix. A hint therefore moves a close call to
  about twenty-five percent for a fact and fifty for a bridge, not to certainty.
- Three or more keys still decide a factless fact on structure alone, as before.

**Current implementation**
- `_tell_bridge_from_event()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/classify.py`.
- `TestClassify` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
