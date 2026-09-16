---
generated: 2026-09-16
engine: 2026-09-15.1
nodes: 17
edges: 5
design OOP: 100/100 (20/20 source files without a design candidate)
---

# Requirement Map

## System Map

_Capabilities grouped by area; thick border = bus; arrows = `depends_on`. Edges into the bus/hubs are hidden (the Dependency Map shows area-level coupling)._

```mermaid
graph LR
  subgraph sg_ARCH["ARCH"]
    ARCH_EXCALIDRAW_030["Excalidraw scene builder — core API<br><small>ARCH-EXCALIDRAW-030</small>"]
    ARCH_EXCALIDRAW_031["Excalidraw quality gates<br><small>ARCH-EXCALIDRAW-031</small>"]
    ARCH_EXCALIDRAW_032["Excalidraw builder entry points: CLI verbs and MCP tools<br><small>ARCH-EXCALIDRAW-032</small>"]
    ARCH_EXCALIDRAW_033["Explanatory output — a diagram a reader with no context can decode<br><small>ARCH-EXCALIDRAW-033</small>"]
    ARCH_EXCALIDRAW_034["Graph auto-layout — a diagram from ids and edges alone<br><small>ARCH-EXCALIDRAW-034</small>"]
    ARCH_RELEASE_035["A released version reaches the people who installed it<br><small>ARCH-RELEASE-035</small>"]
  end
  subgraph sg_REQ["REQ"]
    REQ_EXCALIDRAW_844["Shape, layout, and annotation vocabulary<br><small>REQ-EXCALIDRAW-844</small>"]
    REQ_EXCALIDRAW_845["Connectors and the save() contract<br><small>REQ-EXCALIDRAW-845</small>"]
    REQ_EXCALIDRAW_853["The three call values: at, paint and font<br><small>REQ-EXCALIDRAW-853</small>"]
    REQ_EXCALIDRAW_846["Named gates: crossing, legend, and overflow checks<br><small>REQ-EXCALIDRAW-846</small>"]
    REQ_EXCALIDRAW_847["Text-overlap, label-fit gates, and the two hard gates<br><small>REQ-EXCALIDRAW-847</small>"]
    REQ_EXCALIDRAW_848["Smoke test, render and discover verbs<br><small>REQ-EXCALIDRAW-848</small>"]
    REQ_EXCALIDRAW_850["The scene verb: a described graph becomes both files<br><small>REQ-EXCALIDRAW-850</small>"]
    REQ_EXCALIDRAW_852["The MCP server: the same entry points as tools<br><small>REQ-EXCALIDRAW-852</small>"]
    REQ_EXCALIDRAW_851["pack(): layering, ordering, and routing what will not go straight<br><small>REQ-EXCALIDRAW-851</small>"]
    REQ_EXCALIDRAW_849["Colour and term keys: legend() and glossary()<br><small>REQ-EXCALIDRAW-849</small>"]
  end
  subgraph sg_misc["misc"]
    SYS_DIAGRAM_001["Stakeholder need — a picture of the system, without a drawing session<br><small>SYS-DIAGRAM-001</small>"]
  end
  ARCH_EXCALIDRAW_031 --> ARCH_EXCALIDRAW_030
  ARCH_EXCALIDRAW_032 --> ARCH_EXCALIDRAW_030
  ARCH_EXCALIDRAW_033 --> ARCH_EXCALIDRAW_030
  ARCH_EXCALIDRAW_034 --> ARCH_EXCALIDRAW_030
  ARCH_EXCALIDRAW_034 --> ARCH_EXCALIDRAW_031
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
  ARCH_EXCALIDRAW_032["Excalidraw builder entry points: CLI verbs and MCP tools<br><small>ARCH-EXCALIDRAW-032</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_4["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:4"]
  ARCH_EXCALIDRAW_032 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_4
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_4["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:4"]
  ARCH_EXCALIDRAW_032 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_4
  f_plugin_skills_excalidraw_diagram_scripts_test_mcp_server_py_1["plugin/skills/excalidraw-diagram/scripts/test_mcp_server.py:1"]
  ARCH_EXCALIDRAW_032 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_mcp_server_py_1
  ARCH_EXCALIDRAW_033["Explanatory output — a diagram a reader with no context can decode<br><small>ARCH-EXCALIDRAW-033</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_5["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:5"]
  ARCH_EXCALIDRAW_033 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_5
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_6_792["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:6-792"]
  ARCH_EXCALIDRAW_033 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_6_792
  ARCH_EXCALIDRAW_034["Graph auto-layout — a diagram from ids and edges alone<br><small>ARCH-EXCALIDRAW-034</small>"]
  f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_6["plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py:6"]
  ARCH_EXCALIDRAW_034 -->|implements| f_plugin_skills_excalidraw_diagram_scripts_excalidraw_builder_py_6
  f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_5["plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py:5"]
  ARCH_EXCALIDRAW_034 -->|tested-by| f_plugin_skills_excalidraw_diagram_scripts_test_excalidraw_py_5
  ARCH_RELEASE_035["A released version reaches the people who installed it<br><small>ARCH-RELEASE-035</small>"]
  f_scripts_check_versions_py_2["scripts/check_versions.py:2"]
  ARCH_RELEASE_035 -->|implements| f_scripts_check_versions_py_2
  f_scripts_test_check_versions_py_2_33["scripts/test_check_versions.py:2-33"]
  ARCH_RELEASE_035 -->|tested-by| f_scripts_test_check_versions_py_2_33
  SYS_DIAGRAM_001["Stakeholder need — a picture of the system, without a drawing session<br><small>SYS-DIAGRAM-001</small>"]
  style SYS_DIAGRAM_001 fill:#fee,stroke:#c66
```

## Dependency Map

_Area-level coupling: one box per area (N caps), arrow A->B = some capability in A depends on one in B. The System Map has the per-capability detail._

```mermaid
graph LR
  a_ARCH["ARCH<br><small>6 caps</small>"]
  a_REQ["REQ<br><small>10 caps</small>"]
  a_misc["misc<br><small>1 caps</small>"]
```

## Risk & Unknowns

_Requirements needing attention: red = unimplemented (confirmed, no code); orange = unreviewed (promote after review); yellow = untested (implemented but no tested-by — set `test_exempt` to silence), or unverified-intent (open verify-intent question)._

```mermaid
graph LR
  ok["No risk signals detected"]
```
