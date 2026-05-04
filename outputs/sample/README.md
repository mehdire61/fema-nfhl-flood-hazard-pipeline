# Sample Outputs

These files are intentionally small illustrative outputs for repository review. They are not generated from committed FEMA data, and the numeric values should not be used for analysis.

The samples show expected schemas for catalog, validation, mapped flood-hazard exposure, and preview artifacts while keeping large FEMA NFHL source data out of the repository. File paths inside the sample CSVs are examples.

Large source data and generated geospatial products are intentionally excluded from git by `.gitignore`.

Regenerate the sample exposure chart with:

```bash
python -m fema_nfhl.cli plot-exposure --summary-csv outputs/sample/floodplain_area_summary_sample.csv --output outputs/sample/floodplain_area_summary_sample.png --title "Alameda County Sample Floodplain Area By FEMA Zone"
```
