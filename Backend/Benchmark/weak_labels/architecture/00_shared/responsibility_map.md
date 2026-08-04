# Phần chung — Responsibility map

| Vùng | Core responsibility | Không chịu trách nhiệm |
|---|---|---|
| Layer1 | Load, normalize, canonicalize telemetry | Research labels |
| Phase A | Audit dữ liệu và candidate evidence | Freeze semantic contract |
| B1 | Phân tích Q×K và support để review | Chọn primary Q/K |
| B2 | Freeze Q/K, ontology, resolver, formulas | Tạo labels |
| Phase C | Tạo RuleFiring, Resolution, Assignment | Chọn lại semantic rules |
| Dataset Views | Tạo feature views | Định nghĩa label |
| Evaluation | Join label + feature + fold/purge | Tạo lại label |
