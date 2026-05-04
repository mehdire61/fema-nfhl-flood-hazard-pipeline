# Methodology

## FEMA NFHL Layers

The FEMA National Flood Hazard Layer (NFHL) contains regulatory and hazard mapping data used in floodplain management and flood insurance workflows. This project focuses on a small set of common layers:

- `S_FLD_HAZ_AR`: flood hazard polygons and zone attributes.
- `S_BFE`: base flood elevation lines or features, where available.
- `S_XS`: cross sections, useful context for flood studies.
- `S_WTR_LN`: water lines.
- `S_LOMR`: Letters of Map Revision.
- `L_COMMUNITY_INFO`: community metadata.

## Role Of `S_FLD_HAZ_AR`

`S_FLD_HAZ_AR` is the primary polygon layer for flood hazard mapping, validation, and exposure summaries. The workflow uses fields such as `FLD_ZONE`, `ZONE_SUBTY`, and `SFHA_TF` when present.

## Role Of `S_BFE`

`S_BFE` stores base flood elevation information where available. This project validates the presence and basic numeric quality of BFE attributes and displays BFE lines on maps as contextual FEMA NFHL information. It does not use BFE values to derive flood depths.

## Interactive Map Design

The Folium map uses a compact, collapsible grouped legend for FEMA flood hazard categories and keeps detailed `FLD_ZONE` / `ZONE_SUBTY` overlays available in a collapsible layer control. Default feature tooltips use human-readable labels, convert `SFHA_TF` values from `T`/`F` to `Yes`/`No`, format elevation and depth attributes with units where provided, and hide null, blank, and `-9999` placeholder values. Technical fields such as `STUDY_TYP` are retained in the raw audit section rather than shown in the main tooltip.

Raw FEMA attributes are not shown by default. They are retained in an expandable "Raw FEMA attributes" section in feature popups so technical reviewers can audit source fields without making the main map read like a database export. The legend also includes a visible note that the map is a FEMA NFHL visualization prototype, not an official FEMA flood determination, and that BFE units and vertical datum must be verified before analysis.

The map also includes a point lookup control. Longitude/latitude coordinate lookup is evaluated locally in the browser against visible NFHL polygon features. Address lookup is optional and uses external geocoding services only after the user checks a privacy notice, because geocoding sends the typed address and possible normalized variants to OpenStreetMap Nominatim and, if needed, Esri ArcGIS World Geocoder. If a point is outside the loaded NFHL data extent, the map reports that a map for the relevant county/state package should be generated before interpreting the result. The point lookup is a visualization aid only and is not an official flood determination.

## County Case-Study Preparation

The recommended portfolio workflow is county-scale rather than full-state. The downloader can retrieve a larger FEMA NFHL package, but the analysis workflow should clip extracted layers to a county boundary, municipality, HUC, or small bounding box before mapping or vector overlay.

For the default case study, extracted NFHL layers are clipped to Alameda County, California, using county FIPS `06001`. This keeps validation reports readable and overlays computationally manageable. When a FEMA package is already county/community scoped, such as an Alameda `06001C_*.zip` package, the quickstart workflow can skip boundary clipping and run directly from the zip to catalog, validation, and HTML map outputs.

## CRS Handling

Vector layers must have CRS metadata. For mapping, vectors are reprojected to EPSG:4326 for Folium. For area summaries, flood polygons and administrative boundaries are reprojected to an equal-area CRS before calculating area.

The default equal-area CRS is EPSG:5070, which is suitable for many CONUS-scale summaries. For Alaska, Hawaii, territories, or local engineering work, choose a more appropriate equal-area CRS.

## Floodplain Area Summary

The exposure command overlays flood hazard polygons with administrative boundaries, calculates intersection areas in square kilometers, and reports flood area percentages by admin unit, `FLD_ZONE`, and `ZONE_SUBTY`. Full-state overlays can be slow; clip inputs to a county, municipality, tract group, HUC, or bounding box for portfolio-scale workflows.

## Why Flood Depth Is Excluded

This codebase intentionally excludes flood-depth generation. A BFE-minus-DEM prototype can be tempting, but it requires assumptions about vertical datum alignment, BFE coverage, interpolation, flow connectivity, levees, hydraulic structures, and DEM suitability. Those assumptions are too strong for the scope of this FEMA NFHL portfolio workflow.

The project therefore stays focused on defensible public-data workflows: ingestion, validation, mapping, transformation, and mapped floodplain exposure summaries.

## Known Limitations

The workflow does not perform hydraulic routing, event simulation, levee analysis, culvert/structure modeling, channel connectivity checks, engineering-grade vertical datum correction, or depth raster generation. It is a reproducible FEMA NFHL hazard/exposure workflow, not an official flood determination product.
