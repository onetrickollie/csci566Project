# Upstream data and licenses

| Source | Used for | License | Redistribution |
|---|---|---|---|
| TravelPlanner (Xie et al., ICML 2024), `osunlp/TravelPlanner` on Hugging Face | queries, per-query database slices, annotated reference plans | Dataset: CC BY 4.0 (dataset card). Code repo: MIT | Allowed with attribution. Raw files are downloaded by the scripts, not committed. Derived task files in `data/tasks/` carry query ids only and reference the original rows. |
| FlexTravelBench / Flex-TravelPlanner (Oh et al., 2025) | not used yet | to be checked | to be checked before any release that includes it |

Notes
- TravelPlanner accommodation records reuse listing titles from another city (for example "Brooklyn studio" listed in Detroit). This is an upstream artifact; names are used as identifiers only.
- Entity names are matched **exactly**. The upstream TravelPlanner evaluator resolves names by substring, so in one source query (`validation-0008`) it reads "Pizza Hut" as "Pizza Hut Delivery" and prices that meal at 76 instead of 61. Both evaluators accept the affected plans. We keep exact matching on purpose rather than aliasing two different restaurants; expect small cost differences when comparing against upstream.
- Names that pandas printed with a literal `\n` are restored to a real newline (24 records), matching upstream's structured records. The demos display it as " / ".
