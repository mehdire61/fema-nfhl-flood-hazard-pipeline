# Limitations

This project is designed for reproducible portfolio-scale FEMA NFHL workflows. It is not an official FEMA product, engineering model, insurance determination, permitting tool, or substitute for local floodplain management review.

## Data Availability

FEMA NFHL data varies by community, county, state, and update cycle. Some areas may have complete modern geospatial data, while others may have missing or sparse attributes.

## BFE Coverage

`S_BFE` may be sparse, incomplete, or absent. This project maps and validates BFE features where available, but does not use them to create derived depth surfaces.

## Case-Study Scale

Full-state workflows can be useful for downloading and cataloging, but they are often too large for interactive maps and vector overlays. This project recommends clipping to a county or smaller study area before analysis. The Alameda County example is a manageable portfolio case study, not a claim that one county workflow generalizes automatically to every FEMA study area.

## Regulatory Context

FEMA flood polygons are regulatory and hazard mapping products, not event simulations. They should not be interpreted as a simulated water extent for a specific storm or return-period hydrograph.

## No Flood-Depth Modeling

This project does not calculate flood depths. It does not perform BFE interpolation, DEM sampling, hydraulic routing, vertical datum correction, or event-based inundation modeling.

## Appropriate Use

Use this repository to demonstrate reproducible data engineering, validation, mapping, and transparent scientific assumptions. Do not use its outputs for insurance rating, property determinations, permitting, engineering design, emergency decisions, or official flood determinations.

