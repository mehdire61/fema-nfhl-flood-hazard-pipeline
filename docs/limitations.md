# Limitations

This project is designed for reproducible portfolio-scale FEMA NFHL workflows. It is not an official FEMA product, engineering model, insurance determination, permitting tool, or substitute for local floodplain management review.

## Data Availability

FEMA NFHL data varies by community, county, state, and update cycle. Some areas may have complete modern geospatial data, while others may have missing or sparse attributes.

## BFE Coverage

`S_BFE` may be sparse, incomplete, or absent. This project maps and validates BFE features where available, but does not use them to create derived depth surfaces.

Validation distinguishes FEMA numeric missing/not-applicable codes from zero and other negative elevations. A numeric elevation passing these checks does not establish its units, datum, applicability, or engineering accuracy. Optional polygon `STATIC_BFE` values need not be populated for every flood zone.

## Classification And Area Summaries

Zone X without a recognized explicit subtype remains unresolved. It is not labeled minimal hazard or FEMA Zone D. Source metadata may establish a legacy convention that requires separate interpretation; the pipeline does not infer that convention from missing attributes alone.

Within each administrative ID and raw zone/subtype, overlapping polygons are unioned. Conflicting IDs or cross-category area overlaps cause an explicit error and require source review. The summary does not choose which category is correct. Distinct administrative units may overlap and their reported areas are not automatically additive. Geometry repair is reported and preserves polygon components, but cannot establish the intended survey boundary.

Area reprojection inserts existing exact shared vertices before transformation; this requires a temporary vertex index and adds runtime/memory cost for large inputs. Edges retain the pipeline's straight-segment interpretation in the flood layer's source CRS. This is not geodesic densification, correction of misaligned datasets, or handling of projection discontinuities/dateline crossings. Choose compatible source data and an appropriate local equal-area CRS.

## Case-Study Scale

Full-state workflows can be useful for downloading and cataloging, but they are often too large for interactive maps and vector overlays. This project recommends clipping to a county or smaller study area before analysis. The Alameda County example is a manageable portfolio case study, not a claim that one county workflow generalizes automatically to every FEMA study area.

## Regulatory Context

FEMA flood polygons are regulatory and hazard mapping products, not event simulations. They should not be interpreted as a simulated water extent for a specific storm or return-period hydrograph.

## No Flood-Depth Modeling

This project does not calculate flood depths. It does not perform BFE interpolation, DEM sampling, hydraulic routing, vertical datum correction, or event-based inundation modeling.

## Appropriate Use

Use this repository to demonstrate reproducible data engineering, validation, mapping, and transparent scientific assumptions. Do not use its outputs for insurance rating, property determinations, permitting, engineering design, emergency decisions, or official flood determinations.

