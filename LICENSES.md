# Upstream data and licenses

| Source | Used for | License | Redistribution |
|---|---|---|---|
| TravelPlanner (Xie et al., ICML 2024), `osunlp/TravelPlanner` on Hugging Face | queries, per-query database slices, annotated reference plans | Dataset: CC BY 4.0 (dataset card). Code repo: MIT | Allowed with attribution. Raw files are downloaded by the scripts, not committed. Derived task files in `data/tasks/` carry query ids only and reference the original rows. |
| FlexTravelBench / Flex-TravelPlanner (Oh et al., 2025) | not used yet | to be checked | to be checked before any release that includes it |

Notes
- TravelPlanner accommodation records reuse listing titles from another city (for example "Brooklyn studio" listed in Detroit). This is an upstream artifact; names are used as identifiers only.
