# HalterCheck
Projeto de mestrado que investiga IMUs acopladas a dois halteres sincronizados para analisar amplitude, cadência e assimetria na elevação lateral bilateral.

HalterCheck/
├── README.md
├── LICENSE
├── CITATION.cff
├── .gitignore
├── pyproject.toml
│
├── research/
│   ├── research-question.md
│   ├── hypotheses.md
│   ├── objectives.md
│   ├── observability-matrix.md
│   ├── protocols/
│   │   ├── self-collection.md
│   │   ├── safety.md
│   │   ├── synchronization.md
│   │   └── session-protocol.md
│   └── decisions/
│       └── methodological-decisions.md
│
├── bibliography/
│   ├── references.bib
│   ├── literature-matrix.csv
│   └── notes/
│
├── thesis/
│   ├── templufla_main.tex
│   ├── templufla.cls
│   ├── abntex2cite.sty
│   ├── abntex2-alf.bst
│   ├── refbib.bib
│   ├── TEMPLATE_SOURCE.md
│   │
│   ├── secoes/
│   │   ├── introducao.tex
│   │   ├── fundamentacao.tex
│   │   ├── trabalhos-relacionados.tex
│   │   ├── metodologia.tex
│   │   ├── arquitetura-implementacao.tex
│   │   ├── resultados.tex
│   │   ├── discussao.tex
│   │   └── conclusao.tex
│   │
│   ├── glossarios/
│   ├── imgs/
│   ├── anexos/
│   ├── apendices/
│   └── linguas/
│
├── hardware/
│   ├── bom/
│   ├── schematics/
│   ├── assembly/
│   ├── datasheets/
│   └── tests/
│
├── firmware/
│   └── esp32-node/
│       ├── platformio.ini
│       ├── include/
│       │   └── config.example.h
│       ├── src/
│       └── test/
│
├── configs/
│   ├── acquisition.example.yaml
│   ├── experiment.example.yaml
│   └── processing.example.yaml
│
├── src/
│   └── haltercheck/
│       ├── acquisition/
│       ├── synchronization/
│       ├── preprocessing/
│       ├── segmentation/
│       ├── features/
│       ├── models/
│       ├── evaluation/
│       └── visualization/
│
├── notebooks/
│   ├── 00-audit/
│   ├── 01-preprocessing/
│   ├── 02-synchronization/
│   ├── 03-segmentation/
│   ├── 04-features/
│   ├── 05-modeling/
│   └── 06-results/
│
├── experiments/
│   ├── pilots/
│   ├── sessions/
│   └── manifests/
│
├── data/
│   ├── README.md
│   ├── sample/
│   ├── raw/
│   ├── interim/
│   └── processed/
│
├── results/
│   ├── figures/
│   ├── tables/
│   ├── metrics/
│   └── reports/
│
├── scripts/
│   ├── acquire.py
│   ├── validate-session.py
│   ├── run-pipeline.py
│   └── build-results.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── .github/
    ├── workflows/
    ├── ISSUE_TEMPLATE/
    └── pull_request_template.md