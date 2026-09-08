"""Floodplain exposure and area summaries."""

from __future__ import annotations

import logging
from pathlib import Path

from .utils import ensure_dir, require_optional, safe_percent

LOGGER = logging.getLogger(__name__)
DEFAULT_EQUAL_AREA_CRS = "EPSG:5070"
# Numerical roundoff only: one square millimetre, not a sliver-cleanup threshold.
OVERLAP_ROUNDOFF_SQ_M = 1e-6


def floodplain_area_summary(
    flood_layer: str | Path,
    admin_boundaries: str | Path,
    output_csv: str | Path,
    *,
    admin_id_field: str | None = None,
    admin_name_field: str | None = None,
    equal_area_crs: str = DEFAULT_EQUAL_AREA_CRS,
) -> Path:
    """Calculate unioned area per admin ID and raw FEMA zone/subtype.

    Conflicting source IDs or overlapping categories require source review;
    no category precedence is inferred. Separate admin IDs are independent.
    """

    gpd = require_optional("geopandas")
    flood = gpd.read_file(flood_layer)
    admin = gpd.read_file(admin_boundaries)
    if flood.crs is None or admin.crs is None:
        raise ValueError("Both flood and admin layers must have a CRS for area calculations.")

    crs = require_optional("pyproj").CRS.from_user_input(equal_area_crs)
    method = crs.coordinate_operation.method_name.lower() if crs.coordinate_operation else ""
    equal_area = "equal area" in method.replace("-", " ") or method in {"equal earth", "mollweide", "sinusoidal"}
    if not crs.is_projected or not equal_area:
        raise ValueError("Area calculations require a projected equal-area CRS (for example EPSG:5070 for CONUS).")
    # Projected axes need not be metres (e.g. a custom Albers CRS in US survey feet).
    square_metres_per_unit = crs.axis_info[0].unit_conversion_factor * crs.axis_info[1].unit_conversion_factor
    area_to_sq_km = square_metres_per_unit / 1_000_000

    _check_flood_ids(flood)
    flood = _prepare_polygons(flood, "flood")
    admin = _prepare_polygons(admin, "admin")
    flood, admin = _project_with_shared_nodes(flood, admin, crs)
    flood = _prepare_polygons(flood, "flood")
    admin = _prepare_polygons(admin, "admin")
    admin_id_field = admin_id_field or select_admin_field(admin.columns, ["GEOID", "GEOID20", "FIPS", "ID"])
    admin_name_field = admin_name_field or select_admin_field(admin.columns, ["NAME", "NAMELSAD", "COUNTY", "ADMIN_NAME"])

    if admin_id_field is None:
        admin["_admin_id"] = admin.index.astype(str)
        admin_id_field = "_admin_id"
    if admin_name_field is None:
        admin["_admin_name"] = admin[admin_id_field].astype(str)
        admin_name_field = "_admin_name"

    if admin[admin_id_field].isna().any() or admin[admin_id_field].astype(str).str.strip().eq("").any():
        raise ValueError("Administrative IDs must be nonempty; unresolved IDs cannot define reporting units.")
    name_counts = admin.groupby(admin_id_field, dropna=False)[admin_name_field].nunique(dropna=False)
    conflicting_ids = name_counts[name_counts > 1].index.tolist()
    if conflicting_ids:
        raise ValueError(f"Conflicting administrative names for IDs: {conflicting_ids!r}.")
    admin = gpd.GeoDataFrame(
        {"admin_id": admin[admin_id_field], "admin_name": admin[admin_name_field], "geometry": admin.geometry},
        crs=crs,
    ).dissolve(by="admin_id", dropna=False).reset_index()
    admin["admin_area_sq_km"] = admin.geometry.area * area_to_sq_km

    flood_zone = _actual_column(flood.columns, "FLD_ZONE")
    zone_subty = _actual_column(flood.columns, "ZONE_SUBTY")
    if flood_zone is None:
        flood["FLD_ZONE"] = "UNKNOWN"
        flood_zone = "FLD_ZONE"
    if zone_subty is None:
        flood["ZONE_SUBTY"] = ""
        zone_subty = "ZONE_SUBTY"
    flood["_category_id"] = flood.groupby([flood_zone, zone_subty], dropna=False).ngroup()

    LOGGER.warning("Large vector overlays can be slow; clip inputs to the study area where practical.")
    intersection = gpd.overlay(
        admin,
        flood[[flood_zone, zone_subty, "_category_id", "geometry"]].rename(
            columns={flood_zone: "fld_zone", zone_subty: "zone_subty"}
        ),
        how="intersection",
        keep_geom_type=False,
        make_valid=False,
    )
    if intersection.empty:
        rows = []
    else:
        category_pairs = _interior_category_pairs(flood)
        grouped = intersection.dissolve(
            by=["admin_id", "admin_name", "fld_zone", "zone_subty"],
            aggfunc={"admin_area_sq_km": "first", "_category_id": "first"},
            dropna=False,
        ).reset_index()
        for admin_id, unit in grouped.groupby("admin_id", dropna=False):
            unit = unit.reset_index(drop=True)
            for left, geometry in enumerate(unit.geometry):
                for right in range(left + 1, len(unit)):
                    pair = tuple(sorted(unit.iloc[[left, right]]["_category_id"].tolist()))
                    if pair not in category_pairs:
                        continue
                    overlap_sq_m = geometry.intersection(unit.geometry.iloc[right]).area * square_metres_per_unit
                    if overlap_sq_m > OVERLAP_ROUNDOFF_SQ_M:
                        categories = unit.iloc[[left, right]][["fld_zone", "zone_subty"]].values.tolist()
                        raise ValueError(
                            f"Cross-category overlap in admin ID {admin_id!r}: {overlap_sq_m:.12g} square metres "
                            f"between {categories!r}. Resolve source topology/classification before summarizing; "
                            "overlapping categories are not additive."
                        )
        grouped["flood_area_sq_km"] = grouped.geometry.area * area_to_sq_km
        grouped["flood_area_percent"] = [
            safe_percent(flood_area, admin_area)
            for flood_area, admin_area in zip(grouped["flood_area_sq_km"], grouped["admin_area_sq_km"])
        ]
        rows = grouped[
            [
                "admin_id",
                "admin_name",
                "fld_zone",
                "zone_subty",
                "flood_area_sq_km",
                "admin_area_sq_km",
                "flood_area_percent",
            ]
        ]

    output_csv = Path(output_csv)
    ensure_dir(output_csv.parent)
    if hasattr(rows, "to_csv"):
        rows.to_csv(output_csv, index=False)
    else:
        import pandas as pd

        pd.DataFrame(
            rows,
            columns=[
                "admin_id",
                "admin_name",
                "fld_zone",
                "zone_subty",
                "flood_area_sq_km",
                "admin_area_sq_km",
                "flood_area_percent",
            ],
        ).to_csv(output_csv, index=False)
    return output_csv


def _interior_category_pairs(flood):
    """Screen smaller source features once, before testing dissolved categories.

    Category unions can overlap only if a constituent feature pair overlaps.
    DE-9IM interior dimension 2 includes containment/equality and excludes
    boundary-only contacts. Full unioned overlap areas are still checked within
    each admin, so conflicts outside reporting units do not stop the summary.
    """

    categories = flood["_category_id"].to_numpy()
    geometries = flood.geometry.to_numpy()
    pairs = set()
    index = flood.sindex
    for left, geometry in enumerate(geometries):
        for right in index.query(geometry, predicate="intersects"):
            if right <= left or categories[left] == categories[right]:
                continue
            pair = tuple(sorted((categories[left], categories[right])))
            if pair not in pairs and geometry.relate_pattern(geometries[right], "2********"):
                pairs.add(pair)
    return pairs


def _project_with_shared_nodes(flood, admin, crs):
    """Node coincident source boundaries before transforming their vertices.

    Independently projecting differently segmented straight shared edges can
    create overlaps or gaps. Polygon-minus-line preserves the source polygon
    while GEOS nodes its boundary at the intersecting linework's vertices.
    Include admin edges so category areas and their denominator share nodes.
    """

    if flood.crs == crs and admin.crs == crs:
        return flood, admin
    gpd = require_optional("geopandas")
    np = require_optional("numpy")
    shapely = require_optional("shapely")
    admin = _prepare_polygons(admin.to_crs(flood.crs), "admin")
    geometries = list(flood.geometry) + list(admin.geometry)
    parts, part_owner = shapely.get_parts(geometries, return_index=True)
    rings, ring_part = shapely.get_rings(parts, return_index=True)
    coordinates, coordinate_ring = shapely.get_coordinates(rings, return_index=True)
    ring_owner = part_owner[ring_part]
    del parts, rings, part_owner, ring_part
    vertices = np.unique(coordinates, axis=0)
    tree = shapely.STRtree(shapely.points(vertices))
    affected = set()
    # Query short source segments in bounded batches. An exact interior vertex
    # match needs noding; matching endpoints and already shared edges do not.
    # Ring indices prevent creating a segment between separate rings/parts.
    for begin in range(0, len(coordinates) - 1, 4096):
        indices = np.arange(begin, min(begin + 4096, len(coordinates) - 1))
        indices = indices[coordinate_ring[indices] == coordinate_ring[indices + 1]]
        first, last = coordinates[indices], coordinates[indices + 1]
        segments = shapely.linestrings(np.stack([first, last], axis=1))
        segment_ids, vertex_ids = tree.query(segments, predicate="intersects")
        candidates = vertices[vertex_ids]
        interior = np.any(candidates != first[segment_ids], axis=1) & np.any(candidates != last[segment_ids], axis=1)
        affected.update(ring_owner[coordinate_ring[indices[segment_ids[interior]]]].tolist())
    del tree, vertices, coordinates, coordinate_ring, ring_owner
    if affected:
        boundaries = shapely.boundary(geometries)
        tree = shapely.STRtree(boundaries)
        for index in affected:
            neighbors = tree.query(boundaries[index], predicate="intersects")
            geometries[index] = geometries[index].difference(shapely.GeometryCollection(boundaries[neighbors]))
    projected = gpd.GeoSeries(geometries, crs=flood.crs).to_crs(crs)
    return (
        flood.set_geometry(projected.iloc[:len(flood)].values, crs=crs),
        admin.set_geometry(projected.iloc[len(flood):].values, crs=crs),
    )


def _check_flood_ids(flood) -> None:
    """Repeated FEMA IDs must describe the same source feature; never drop by ID."""

    feature_id = _actual_column(flood.columns, "FLD_AR_ID")
    if feature_id is None:
        return
    dfirm_id = _actual_column(flood.columns, "DFIRM_ID")
    id_fields = [dfirm_id, feature_id] if dfirm_id else [feature_id]
    identified = flood[flood[feature_id].notna() & flood[feature_id].astype(str).str.strip().ne("")]
    duplicates = identified[identified.duplicated(id_fields, keep=False)]
    attributes = [
        field for field in flood.columns
        if field != flood.geometry.name and str(field).upper() not in {"OBJECTID", "FID", "OID"}
    ]
    for identifier, records in duplicates.groupby(id_fields, dropna=False):
        first = records.geometry.iloc[0]
        same_geometry = first is not None and all(
            geometry is not None and (first.wkb == geometry.wkb or first.equals(geometry))
            for geometry in records.geometry
        )
        if len(records[attributes].drop_duplicates()) > 1 or not same_geometry:
            raise ValueError(
                f"Conflicting FEMA flood ID {identifier!r}: attributes or geometries differ. "
                "Resolve source records (including any geometry fragments) before summarizing."
            )


def _prepare_polygons(layer, label):
    """Expose the existing overlay repair behavior without discarding geometry parts."""

    polygon_types = {"Polygon", "MultiPolygon"}
    bad = layer.geometry.isna() | layer.geometry.is_empty | ~layer.geom_type.isin(polygon_types)
    if bad.any():
        raise ValueError(f"The {label} layer requires valid nonempty polygon geometry; rows {layer.index[bad].tolist()!r}.")
    invalid = ~layer.geometry.is_valid
    if invalid.any():
        repaired = layer.loc[invalid].geometry.make_valid()
        if (~repaired.is_valid | repaired.is_empty | ~repaired.geom_type.isin(polygon_types)).any():
            raise ValueError(
                f"The {label} layer could not be repaired to valid nonempty polygon geometry without "
                "discarding nonpolygon components; repair source geometry explicitly."
            )
        feature_id = _actual_column(layer.columns, "FLD_AR_ID")
        identifiers = layer.loc[invalid, feature_id].tolist() if feature_id else layer.index[invalid].tolist()
        LOGGER.warning(
            "Repaired %s invalid %s polygon(s) using make_valid; source IDs/rows: %s", invalid.sum(), label, identifiers
        )
        layer = layer.copy()
        layer.loc[invalid, layer.geometry.name] = repaired
    return layer


def select_admin_field(columns, candidates: list[str]) -> str | None:
    """Select a likely administrative identifier/name field."""

    lookup = {str(column).upper(): str(column) for column in columns}
    for candidate in candidates:
        if candidate.upper() in lookup:
            return lookup[candidate.upper()]
    return None


def _actual_column(columns, wanted: str) -> str | None:
    lookup = {str(column).upper(): str(column) for column in columns}
    return lookup.get(wanted.upper())

