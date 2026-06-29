# Context Benchmark

## Purpose

`context_benchmark/` la family giu lai cho context-aware benchmark va runtime artifacts.

Tree nay khong con la lane train active chinh cho benchmark real-only, nhung van duoc giu vi:

- runtime FT diagnosis hien tai van uu tien artifact tu day
- simulator sizing helpers van dung config va split contract cua family nay
- mot so report/scientific artifact tooling van can de doi chieu historical augmented runs

## Current status

- khong con la family train active chinh
- flow train active `real-only` da chuyen sang `tabular_benchmark/`
- tree nay la nhanh retained/auxiliary, khong phai legacy da chet hoan toan

## Input / Output

- real labeled input mac dinh: `Backend/Benchmark/benchmark_dataset/dataset/benchmark_input_labeled.csv`
- synthetic input mac dinh: `synthetic_benchmark_gap_aware.csv` tu simulator
- training/build artifacts van nam duoi `Backend/Benchmark/context_benchmark/artifacts/**`

Historical run cu duoc giu nguyen tren dia. Refactor naming hien tai khong xoa hoac migrate cac run cu.

## Limits

- nhieu script trong tree nay van phan anh logic augmented cu
- chi nen rebuild khi can runtime consumer hoac doi chieu nghien cuu
- neu muc tieu la benchmark real-only active, uu tien `tabular_benchmark/`
