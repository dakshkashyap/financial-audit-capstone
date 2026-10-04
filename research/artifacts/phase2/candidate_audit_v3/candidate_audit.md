# Candidate coverage audit

reference coverage against UNVALIDATED labels; oracle rows used only after blind cache was saved

| Coverage | Hits / 16 provisional citable labels |
|---|---:|
| public_union_displayed | 3/16 |
| public_union_unbounded | 3/16 |
| public_union_full_reference | 3/16 |
| anywhere_in_taxonomy | 6/16 |
| oracle_gold_row_exists | 16/16 |
| oracle_gold_row_displayed | 16/16 |
| oracle_gold_row_top8 | 2/16 |
| oracle_gold_row_top1 | 2/16 |
| oracle_gold_row_unbounded | 2/16 |
| oracle_gold_row_full_reference | 2/16 |
| oracle_gold_row_static | 1/16 |

## Row diagnostics

```json
{
  "row_count": 1113,
  "provenance_counts": {
    "taxonomy": 978,
    "section_fallback": 113,
    "none": 2,
    "parent_fallback": 17,
    "static_map": 3
  },
  "arc_role_counts": {
    "commonPracticeRef": 753,
    "disclosureRef": 4167,
    "exampleRef": 554,
    "legacyRef": 1000
  },
  "rows_with_camel_fallback": 17,
  "rows_with_duplicate_citation_arcs": 299,
  "rows_with_same_citation_multiple_roles": 173,
  "rows_with_general_and_industry_competition": 316,
  "rows_with_more_than_8_unbounded_candidates": 216,
  "valued_rows_hidden_by_40_row_cap": 0,
  "rows_with_equal_specificity_lexicographic_ties": 575
}
```

## Mechanical ranking diagnostics

```json
{
  "rows_graph_primary_differs_from_lexicographic_first": 525,
  "rows_selector_primary_differs_from_graph_primary": 494,
  "rows_taxonomy_ranked_order_changed_by_lexicographic_sort": 568,
  "rows_800_to_899_candidates_compete_with_below_800": 403,
  "rows_presentation_topic_primary_with_nonpresentation_alternative": 323,
  "deduplicated_candidates_that_lost_higher_priority_role": 49
}
```

## No explicit exact identifier anywhere in this reference taxonomy

- case_fd2292c43951c99d1f6f: ASC 606-10-25-23
- case_2edbf676d94e573cdd4e: ASC 730-10-25-1
- case_7dad7285f6966525d3b0: ASC 842-10-25-2
- case_6c6c786e0d9a5a2bcff8: ASC 606-10-25-23
- case_d1efe0af0cfd3eaa909d: ASC 606-10-25-23
- case_33a5c50b437c422eb1e1: ASC 470-10-45-11
- case_cc180e9e3a6186422bac: ASC 326-20-30-1
- case_197844f25e4b4b75fbe9: ASC 606-10-25-23
- case_a2f22d9fc55ca36d8411: ASC 330-10-35-1B
- case_87b8b6091e9cf2644c6e: ASC 606-10-25-23

## Limits

- Reference membership is neither paragraph applicability nor independent label validation.
- Full taxonomy means this 2023 reference linkbase, not the full Codification or a historical effective-date corpus.
- Gold-row coverage is an oracle diagnostic; the deployed system does not receive that row.
- CamelCase truncation is a name heuristic, not a verified taxonomy hierarchy.
- Counts include repeated company/statement rows across this 48-case development pilot.
- Absence means no explicit exact paragraph identifier in the reference metadata, not that the Codification lacks or rejects that paragraph.
- Taxonomy ranking prefers topics below 900, while the separate selector prefers below 800; neither threshold establishes case-specific applicability.
