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

## Flood-Zone Interpretation

The grouped map categories keep explicit 0.2% Zone X designations separate from shallow 1% flooding (average depth under one foot), small-drainage-area 1% flooding (under one square mile), future conditions, and reduced hazard from levees. These Zone X distinctions do not promote features to SFHA. Original `FLD_ZONE`, `ZONE_SUBTY`, and `SFHA_TF` values remain intact in the detailed layers and raw attributes.

Only recognized complete X designations are classified; case, whitespace, hyphens, and PCT/PERCENT/% spelling are normalized for matching. Explicit minimal-hazard and legacy outside-the-0.2%-floodplain designations remain minimal. Blank, unfamiliar, or contradictory X subtypes become **Unresolved Zone X**, not minimal hazard and not FEMA Zone D. `SFHA_TF=F` alone cannot distinguish shaded from unshaded X. FEMA's conversion of standalone X in a documented legacy schema does not justify assuming that every modern or unknown-schema blank X is minimal.

## Role Of `S_BFE`

`S_BFE` stores base flood elevation information where available. This project validates its elevation field and any present polygon `STATIC_BFE` field, without changing source values. Numeric and string forms of `-9999` (null/not applicable) and `-8888` (intentionally unpopulated) receive distinct findings. True nulls/blanks, invalid text, and non-finite values are counted separately. Zero and other negative elevations are potentially valid datum-referenced elevations: the retained `bfe_zero_values` count is informational, not a missing-value warning. Optional `STATIC_BFE` null/not-applicable values are informational; they do not require a BFE in every polygon. Units, datum, applicability, and physical accuracy still require review. BFE lines remain contextual and are not used to derive flood depths.

## Interactive Map Design

The Folium map uses a compact, collapsible grouped legend for FEMA flood hazard categories and keeps detailed `FLD_ZONE` / `ZONE_SUBTY` overlays available in a collapsible layer control. Default feature tooltips use human-readable labels, convert source `SFHA_TF` values from `T`/`F` to `Yes`/`No`, format elevation and depth attributes with units where provided, and hide null, blank, `-9999`, and `-8888` placeholder values. Technical fields such as `STUDY_TYP` are retained in the raw audit section rather than shown in the main tooltip. Coordinate lookup uses the same category labels and value formatting. It lists distinct matching source records even if IDs conflict, suppresses duplicate appearances of the same feature across display layers, and notes multiple matches without assigning precedence.

Raw FEMA attributes are not shown by default. They are retained in an expandable "Raw FEMA attributes" section in feature popups so technical reviewers can audit source fields without making the main map read like a database export. The legend also includes a visible note that the map is a FEMA NFHL visualization prototype, not an official FEMA flood determination, and that BFE units and vertical datum must be verified before analysis.

The map also includes a point lookup control. Longitude/latitude coordinate lookup is evaluated locally in the browser against visible NFHL polygon features. Address lookup is optional and uses external geocoding services only after the user checks a privacy notice, because geocoding sends the typed address and possible normalized variants to OpenStreetMap Nominatim and, if needed, Esri ArcGIS World Geocoder. If a point is outside the loaded NFHL data extent, the map reports that a map for the relevant county/state package should be generated before interpreting the result. The point lookup is a visualization aid only and is not an official flood determination.

## County Case-Study Preparation

The recommended portfolio workflow is county-scale rather than full-state. The downloader can retrieve a larger FEMA NFHL package, but the analysis workflow should clip extracted layers to a county boundary, municipality, HUC, or small bounding box before mapping or vector overlay.

For the default case study, extracted NFHL layers are clipped to Alameda County, California, using county FIPS `06001`. This keeps validation reports readable and overlays computationally manageable. When a FEMA package is already county/community scoped, such as an Alameda `06001C_*.zip` package, the quickstart workflow can skip boundary clipping and run directly from the zip to catalog, validation, and HTML map outputs.

## CRS Handling

Vector layers must have CRS metadata. For mapping, vectors are reprojected to EPSG:4326 for Folium. For area summaries, administrative geometry is first aligned to the flood layer's source CRS. Existing vertices lying exactly inside another boundary segment are inserted into that boundary before both layers are reprojected to the equal-area CRS. This preserves differently segmented shared edges, including administrative edges, during vertex-based reprojection. The temporary noding preserves source polygon area/topology and does not rewrite input files. It is unnecessary when both input layers already use the requested area CRS.

The default equal-area CRS is EPSG:5070, which is suitable for many CONUS-scale summaries. For Alaska, Hawaii, territories, or local engineering work, choose a more appropriate equal-area CRS.

## Floodplain Area Summary

The exposure command unions administrative geometry by ID, intersects it with flood polygons, and unions the resulting geometry within each raw `FLD_ZONE` / `ZONE_SUBTY` group. Both numerator and denominator therefore count each location once within that reporting unit/category. Null zone/subtype groups remain explicit in the existing seven-column CSV. Boundary-touch categories retain their existing rows with zero area.

Repeated FEMA feature IDs (scoped by `DFIRM_ID` when present) must have consistent source attributes and geometry; storage-only `OBJECTID`/`FID`/`OID` differences are ignored. Conflicting source records or different administrative names sharing one ID produce an error rather than dropping records. Geometry fragments sharing an ID must be resolved in the source before summarizing.

Positive overlaps between different raw zone/subtype categories within one administrative ID stop the summary, naming the categories, ID, and overlap area. No classification precedence or additive total is invented. A tolerance of `1e-6` square metres (one square millimetre) covers numerical roundoff only; no snapping or sliver removal occurs. Distinct administrative IDs are reported independently, so their areas must not be summed without considering administrative overlaps.

An exact vertex spatial index identifies boundaries needing noding, using bounded batches of source segments. Already consistently segmented boundaries retain their geometry. A spatial index screens individual projected feature pairs once for two-dimensional interior intersections, including containment and equal geometries. Only category pairs flagged by that screen need the full dissolved intersection/area check within each administrative unit. Boundary-only contacts need no category intersection construction. This retains within-category unions, administrative unions, and detection of genuine conflicts, including their full unioned overlap area.

The existing overlay's invalid-polygon repair is explicit: `make_valid` emits a warning identifying affected source records. Repairs must preserve all components as valid polygons; null/empty geometry and repairs collapsing to lines or mixed collections require source correction. Source files are never rewritten. Areas use a projected equal-area CRS with axis units converted to square kilometres; EPSG:5070 remains the CONUS default. Full-state overlays can be slow; use a manageable study area.

## Scientific References

- [FEMA FIRM Database Technical Reference, November 2024](https://www.fema.gov/sites/default/files/documents/fema_rm-firm-database-technical-reference-nov-2024.pdf): section 7.3 (printed p.13), polygon topology (p.17), hazard fields (pp.45–46), and zone/subtype crosswalk (pp.48–51).
- [FEMA IS-273 FIRM legend](https://emilms.fema.gov/is_0273/groups/36.html): shaded/unshaded X, SFHA, and Zone D distinctions.
- [FEMA NFHL Guidance, November 2023](https://www.fema.gov/sites/default/files/documents/National_Flood_Hazard_Layer_Guidance_Nov_2023.pdf), p.22: legacy zone/subtype conversion conventions.
- [FEMA Levees Guidance, November 2023](https://www.fema.gov/sites/default/files/documents/fema_rm-levee_guidance_nov_2023.pdf), p.21: reduced-hazard Zone X labeling.
- [GeoPandas `to_crs`](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_crs.html): vertex transformation and straight-segment assumptions.
- [Shapely set operations](https://shapely.readthedocs.io/en/stable/manual.html#object.difference) and [DE-9IM relationship patterns](https://shapely.readthedocs.io/en/2.0.7/reference/shapely.relate_pattern.html): polygon/line noding and interior-intersection predicates that include containment.

## Why Flood Depth Is Excluded

This codebase intentionally excludes flood-depth generation. A BFE-minus-DEM prototype can be tempting, but it requires assumptions about vertical datum alignment, BFE coverage, interpolation, flow connectivity, levees, hydraulic structures, and DEM suitability. Those assumptions are too strong for the scope of this FEMA NFHL portfolio workflow.

The project therefore stays focused on defensible public-data workflows: ingestion, validation, mapping, transformation, and mapped floodplain exposure summaries.

## Known Limitations

The workflow does not perform hydraulic routing, event simulation, levee analysis, culvert/structure modeling, channel connectivity checks, engineering-grade vertical datum correction, or depth raster generation. It is a reproducible FEMA NFHL hazard/exposure workflow, not an official flood determination product.
