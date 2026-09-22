# AgriFusion-IoT documentation

This directory contains the tracked documentation that a new maintainer can
use from a clean clone. Local worklogs, large datasets, generated reports and
hardware evidence remain separate from this public orientation layer.

## Read in this order

1. [System architecture](architecture.md)
2. [Repository hygiene](repository-hygiene.md)
3. [Backend pipeline](../Backend/README.md)
4. [Backend flow](../Backend/PIPELINE_FLOW.md)
5. [Benchmark workspace](../Backend/Benchmark/README.md)
6. [Firmware](../IoT_Node/README.md)
7. [Frontend dashboard](../Frontend/README.md)

## Source-of-truth rule

Documentation describes the implementation that exists in the repository.
When a result is only a proposal, experiment, hardware observation or local
artifact, it must be labelled as such instead of being presented as a
production guarantee.

The canonical telemetry-processing package is
`Backend/Navigation/Core`. The benchmark lane consumes the canonical Layer1
artifacts; it does not rewrite Layer0 evidence or Layer1 outputs in place.
