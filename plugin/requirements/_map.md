---
generated: 2026-09-06
engine: 2026-09-06.15
nodes: 11
edges: 3
design OOP: 0/100 (0/2 source files without a design candidate)
---

# Requirement Map

## Specification Hierarchy

_The spec hierarchy: system needs -> architecture requirements (`satisfies:`), each box showing how many code-level requirements sit under it. The code level itself is counted, not drawn._

```mermaid
graph TD
  ARCH_EXCALIDRAW_030[ARCH-EXCALIDRAW-030<br/>2 code]
  ARCH_EXCALIDRAW_031[ARCH-EXCALIDRAW-031<br/>2 code]
  ARCH_EXCALIDRAW_032[ARCH-EXCALIDRAW-032<br/>1 code]
  ARCH_EXCALIDRAW_033[ARCH-EXCALIDRAW-033<br/>1 code]
  SYS_DIAGRAM_001[[SYS-DIAGRAM-001]]
  SYS_DIAGRAM_001 --> ARCH_EXCALIDRAW_030
  SYS_DIAGRAM_001 --> ARCH_EXCALIDRAW_031
  SYS_DIAGRAM_001 --> ARCH_EXCALIDRAW_032
  SYS_DIAGRAM_001 --> ARCH_EXCALIDRAW_033
  style SYS_DIAGRAM_001 stroke-width:3px
```

## System Map

_Capabilities grouped by area; thick border = bus; arrows = `depends_on`. Edges into the bus/hubs are hidden (the Dependency Map shows area-level coupling)._

```mermaid
graph LR
  subgraph sg_ARCH["ARCH"]
    ARCH_EXCALIDRAW_030["Excalidraw scene builder — core API<br><small>ARCH-EXCALIDRAW-030</small>"]
    ARCH_EXCALIDRAW_031["Excalidraw quality gates<br><small>ARCH-EXCALIDRAW-031</small>"]
    ARCH_EXCALIDRAW_032["Excalidraw builder CLI verbs<br><small>ARCH-EXCALIDRAW-032</small>"]
    ARCH_EXCALIDRAW_033["Explanatory output — a diagram a reader with no context can decode<br><small>ARCH-EXCALIDRAW-033</small>"]
  end
  subgraph sg_REQ["REQ"]
    REQ_EXCALIDRAW_844["Shape, layout, and annotation vocabulary<br><small>REQ-EXCALIDRAW-844</small>"]
    REQ_EXCALIDRAW_845["Connectors and the save() contract<br><small>REQ-EXCALIDRAW-845</small>"]
    REQ_EXCALIDRAW_846["Named gates: crossing, legend, and overflow checks<br><small>REQ-EXCALIDRAW-846</small>"]
    REQ_EXCALIDRAW_847["Text-overlap, label-fit gates, and the two hard gates<br><small>REQ-EXCALIDRAW-847</small>"]
    REQ_EXCALIDRAW_848["Smoke test, render and discover verbs<br><small>REQ-EXCALIDRAW-848</small>"]
    REQ_EXCALIDRAW_849["Colour and term keys: legend() and glossary()<br><small>REQ-EXCALIDRAW-849</small>"]
  end
  subgraph sg_misc["misc"]
    SYS_DIAGRAM_001["Stakeholder need — a picture of the system, without a drawing session<br><small>SYS-DIAGRAM-001</small>"]
  end
  ARCH_EXCALIDRAW_031 --> ARCH_EXCALIDRAW_030
  ARCH_EXCALIDRAW_032 --> ARCH_EXCALIDRAW_030
  ARCH_EXCALIDRAW_033 --> ARCH_EXCALIDRAW_030
```

## Requirement-to-Code

_Each system/architecture requirement → its code; arrow label = role (`implements` / `tested-by`). Red = confirmed but no code linked (a gap); grey = baseline/draft, not linked yet (expected). Code-level requirements are omitted here (see the viewer)._

```mermaid
graph LR
  ARCH_EXCALIDRAW_030["Excalidraw scene builder — core API<br><small>ARCH-EXCALIDRAW-030</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_2["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:2"]
  ARCH_EXCALIDRAW_030 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_2
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_2["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:2"]
  ARCH_EXCALIDRAW_030 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_2
  ARCH_EXCALIDRAW_031["Excalidraw quality gates<br><small>ARCH-EXCALIDRAW-031</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_3["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:3"]
  ARCH_EXCALIDRAW_031 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_3
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_3["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:3"]
  ARCH_EXCALIDRAW_031 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_3
  ARCH_EXCALIDRAW_032["Excalidraw builder CLI verbs<br><small>ARCH-EXCALIDRAW-032</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_4["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:4"]
  ARCH_EXCALIDRAW_032 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_4
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_4["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:4"]
  ARCH_EXCALIDRAW_032 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_4
  ARCH_EXCALIDRAW_033["Explanatory output — a diagram a reader with no context can decode<br><small>ARCH-EXCALIDRAW-033</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_5["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:5"]
  ARCH_EXCALIDRAW_033 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_5
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_5_669["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:5-669"]
  ARCH_EXCALIDRAW_033 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_5_669
  SYS_DIAGRAM_001["Stakeholder need — a picture of the system, without a drawing session<br><small>SYS-DIAGRAM-001</small>"]
  style SYS_DIAGRAM_001 fill:#fee,stroke:#c66
```

## Dependency Map

_Area-level coupling: one box per area (N caps), arrow A->B = some capability in A depends on one in B. The System Map has the per-capability detail._

```mermaid
graph LR
  a_ARCH["ARCH<br><small>4 caps</small>"]
  a_REQ["REQ<br><small>6 caps</small>"]
  a_misc["misc<br><small>1 caps</small>"]
```

## Risk & Unknowns

_Requirements needing attention: red = unimplemented (confirmed, no code); orange = unreviewed (promote after review); yellow = untested (implemented but no tested-by — set `test_exempt` to silence), or unverified-intent (open verify-intent question)._

```mermaid
graph LR
  ok["No risk signals detected"]
```
