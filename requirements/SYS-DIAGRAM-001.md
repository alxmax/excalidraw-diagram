---
id: SYS-DIAGRAM-001
status: confirmed
level: system
layer: need
owner: Alex
priority: must-have
milestone: v1.0.0
---

# Stakeholder need — a picture of the system, without a drawing session

## Description
> The diagram that would explain a system is the one nobody makes. Drawing it by hand
> costs an afternoon and is stale the week after; generating it from a tool that owns the
> layout gives you a picture you cannot edit, which is worse, because the one thing a
> reviewer wants to do with a diagram is move a box. So the person who understands the
> system describes it in a sentence and gets back something that opens in a browser AND
> stays hand-editable — otherwise the diagram is a build artifact rather than a document.
>
> AUTHORED BY A HUMAN, not derived. This need did not travel with the requirements that
> satisfy it: they satisfied `SYS-VISUAL-106` in requirement-manager, whose scope was
> "see the requirement graph at a glance", and that is a different need from this one.
> Nothing in the source could have told the engine what this says — a need is named, not
> inferred (ADR-0030 rule 3 in the repository these came from).

Every bullet below is binding.
- A description of a system, flow or architecture yields both an editable scene file and a
  viewer that opens with no install and no network.
- The scene remains editable in a general-purpose editor after generation. A diagram that
  can only be regenerated is a build output, not a document.
- Producing a diagram requires no dependency beyond a Python interpreter, so the skill runs
  wherever the project already runs.

## Cases
CASE-1 — a described system becomes an openable, editable picture
  Given  a description of a system with its parts and the links between them
  When   the skill runs
  Then   both a `.excalidraw` scene and a self-contained `.html` viewer exist, the viewer
         opens by double-click, and the scene imports into excalidraw.com with every
         element still selectable and movable

CASE-2 — the picture is legible, not merely valid
  Given  a generated scene
  When   its layout is checked
  Then   no two shapes overlap and no connector crosses another, because a scene whose JSON
         parses and whose boxes sit on top of each other is a failure the format cannot
         report

CASE-3 — no toolchain is required
  Given  a machine with a Python interpreter and nothing else installed
  When   the skill runs
  Then   it produces both outputs without fetching a package, starting a service, or
         needing an API key
