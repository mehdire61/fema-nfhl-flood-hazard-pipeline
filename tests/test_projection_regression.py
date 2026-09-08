"""Independent synthetic regression, not an observed FEMA-data defect.

Run from the checkout being reviewed, with that checkout installed/importable:
    python -m pytest /path/to/test_projection_regression.py -q

Baseline 25b1a896 accepts this valid geographic polygon partition. The reviewed
correction fails after EPSG:5070 reprojection creates an artificial 5.11 m2
intersection. No source coordinates, thresholds, or installed code are changed.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from fema_nfhl.exposure import _project_with_shared_nodes, floodplain_area_summary


def test_valid_adjacent_geographic_polygons_survive_area_summary(tmp_path: Path) -> None:
    # The two boundaries are the same straight geographic line. The north
    # polygon simply carries one additional collinear vertex on that line.
    south = Polygon([
        (-122, 37), (-121.99, 37), (-121.99, 37.01),
        (-122, 37.01), (-122, 37),
    ])
    north = Polygon([
        (-122, 37.01), (-121.995, 37.01), (-121.99, 37.01),
        (-121.99, 37.02), (-122, 37.02), (-122, 37.01),
    ])
    assert south.is_valid and north.is_valid
    assert south.touches(north)
    assert south.intersection(north).area == 0
    flood = gpd.GeoDataFrame(
        {'FLD_ZONE': ['AE', 'X'], 'ZONE_SUBTY': [None, 'AREA OF MINIMAL FLOOD HAZARD'],
         'FLD_AR_ID': ['SYNTHETIC_SOUTH', 'SYNTHETIC_NORTH']},
        geometry=[south, north], crs='EPSG:4326',
    )
    admin = gpd.GeoDataFrame(
        {'GEOID': ['001'], 'NAME': ['Synthetic topology check']},
        geometry=[box(-122.001, 36.999, -121.989, 37.021)], crs='EPSG:4326',
    )
    flood_path, admin_path = tmp_path/'flood.geojson', tmp_path/'admin.geojson'
    flood.to_file(flood_path, driver='GeoJSON')
    admin.to_file(admin_path, driver='GeoJSON')
    output = floodplain_area_summary(flood_path, admin_path, tmp_path/'areas.csv')
    rows = pd.read_csv(output)
    assert len(rows) == 2
    assert set(rows['fld_zone']) == {'AE', 'X'}
    assert (rows['flood_area_sq_km'] > 0).all()
    # Acceptance alone is insufficient: independent projection of these source
    # polygons double-counts 5.11 m2. Compare with the projected source union,
    # whose exterior does not contain the artificial internal overlap.
    expected_m2 = gpd.GeoSeries([south.union(north)], crs=flood.crs).to_crs(5070).area.iloc[0]
    assert rows['flood_area_sq_km'].sum() * 1_000_000 == pytest.approx(expected_m2, rel=1e-12, abs=1e-6)


def _geographic_summary(tmp_path, geometries, zones, admin_geometry=None):
    flood = gpd.GeoDataFrame(
        {'FLD_ZONE': zones, 'ZONE_SUBTY': [None] * len(zones),
         'FLD_AR_ID': [f'SYNTHETIC_{index}' for index in range(len(zones))]},
        geometry=geometries, crs='EPSG:4326',
    )
    admin = gpd.GeoDataFrame(
        {'GEOID': ['001'], 'NAME': ['Synthetic topology check']},
        geometry=[admin_geometry if admin_geometry is not None else box(-122.001, 36.999, -121.969, 37.021)],
        crs=flood.crs,
    )
    flood_path, admin_path = tmp_path/'flood.geojson', tmp_path/'admin.geojson'
    flood.to_file(flood_path, driver='GeoJSON')
    admin.to_file(admin_path, driver='GeoJSON')
    return pd.read_csv(floodplain_area_summary(flood_path, admin_path, tmp_path/'areas.csv'))


def _projected_area(geometry):
    return gpd.GeoSeries([geometry], crs='EPSG:4326').to_crs(5070).area.iloc[0]


def test_opposite_boundary_segmentation_does_not_create_an_area_gap(tmp_path):
    south = Polygon([
        (-122, 37), (-121.99, 37), (-121.99, 37.01),
        (-121.995, 37.01), (-122, 37.01), (-122, 37),
    ])
    north = box(-122, 37.01, -121.99, 37.02)
    assert south.touches(north)
    expected_m2 = _projected_area(south.union(north))
    # Here separate projection loses area instead of creating an overlap.
    assert expected_m2 - (_projected_area(south) + _projected_area(north)) > 1

    rows = _geographic_summary(tmp_path, [south, north], ['AE', 'X'])

    assert len(rows) == 2
    assert rows['flood_area_sq_km'].sum() * 1_000_000 == pytest.approx(expected_m2, rel=1e-12, abs=1e-6)


def test_t_junction_preserves_partition_area_and_within_category_union(tmp_path):
    south = box(-122, 37, -121.98, 37.01)
    northwest = box(-122, 37.01, -121.99, 37.02)
    northeast = box(-121.99, 37.01, -121.98, 37.02)
    overlapping_south = box(-121.995, 37.005, -121.985, 37.01)
    expected_m2 = _projected_area(unary_union([south, northwest, northeast]))

    rows = _geographic_summary(
        tmp_path, [south, northwest, northeast, overlapping_south], ['AE', 'X', 'AH', 'AE'],
    )

    assert len(rows) == 3
    assert set(rows['fld_zone']) == {'AE', 'X', 'AH'}
    assert rows['flood_area_sq_km'].sum() * 1_000_000 == pytest.approx(expected_m2, rel=1e-12, abs=1e-6)


def test_shared_admin_boundary_uses_the_same_segmentation_for_area_and_percent(tmp_path):
    admin = box(-122, 37, -121.99, 37.01)
    flood = Polygon([
        (-122, 37), (-121.99, 37), (-121.99, 37.01),
        (-121.995, 37.01), (-122, 37.01), (-122, 37),
    ])
    assert admin.equals(flood)
    # The source union preserves the supplied midpoint on the common exterior.
    expected_m2 = _projected_area(admin.union(flood))

    rows = _geographic_summary(tmp_path, [flood], ['AE'], admin_geometry=admin)

    assert len(rows) == 1
    assert rows.loc[0, 'flood_area_sq_km'] * 1_000_000 == pytest.approx(expected_m2, rel=1e-12, abs=1e-6)
    assert rows.loc[0, 'admin_area_sq_km'] * 1_000_000 == pytest.approx(expected_m2, rel=1e-12, abs=1e-6)
    assert rows.loc[0, 'flood_area_percent'] == pytest.approx(100, rel=1e-12)


def test_hole_and_multipart_shared_boundaries_conserve_area(tmp_path):
    exterior = box(-122, 37, -121.98, 37.02)
    hole = box(-121.996, 37.004, -121.988, 37.012)
    surrounding = Polygon(exterior.exterior.coords, [hole.exterior.coords])
    filling = Polygon([
        (-121.996, 37.004), (-121.988, 37.004), (-121.988, 37.012),
        (-121.992, 37.012), (-121.996, 37.012), (-121.996, 37.004),
    ])
    islands = MultiPolygon([filling, box(-121.976, 37.004, -121.972, 37.008)])
    assert surrounding.is_valid and islands.is_valid
    assert surrounding.touches(islands)
    expected_m2 = _projected_area(surrounding.union(islands))

    rows = _geographic_summary(tmp_path, [surrounding, islands], ['X', 'AE'])

    assert len(rows) == 2
    assert rows['flood_area_sq_km'].sum() * 1_000_000 == pytest.approx(expected_m2, rel=1e-12, abs=1e-6)


def test_duplicate_records_do_not_hide_unequal_shared_edge_segmentation(tmp_path):
    south = box(-122, 37, -121.99, 37.01)
    north = Polygon([
        (-122, 37.01), (-121.995, 37.01), (-121.99, 37.01),
        (-121.99, 37.02), (-122, 37.02), (-122, 37.01),
    ])
    # Every long/short boundary segment appears twice, so duplicate edge counts
    # alone cannot establish that the shared boundary is already fully noded.
    rows = _geographic_summary(tmp_path, [south, north, south, north], ['AE', 'X', 'AE', 'X'])

    assert len(rows) == 2
    assert rows['flood_area_sq_km'].sum() * 1_000_000 == pytest.approx(
        _projected_area(south.union(north)), rel=1e-12, abs=1e-6,
    )


def test_projection_matches_explicit_source_nodes_without_changing_source_records():
    south = box(-122, 37, -121.99, 37.01)
    noded_south = Polygon([
        (-122, 37), (-121.99, 37), (-121.99, 37.01),
        (-121.995, 37.01), (-122, 37.01), (-122, 37),
    ])
    north = Polygon([
        (-122, 37.01), (-121.995, 37.01), (-121.99, 37.01),
        (-121.99, 37.02), (-122, 37.02), (-122, 37.01),
    ])
    assert noded_south.equals(south)
    flood = gpd.GeoDataFrame({'source_id': ['south', 'north']}, geometry=[south, north], crs=4326)
    admin = gpd.GeoDataFrame(geometry=[box(-122.001, 36.999, -121.989, 37.021)], crs=4326)
    original_wkb = flood.geometry.to_wkb().tolist(), admin.geometry.to_wkb().tolist()
    expected = gpd.GeoSeries([noded_south, north], crs=4326).to_crs(5070)

    projected_flood, projected_admin = _project_with_shared_nodes(flood, admin, expected.crs)

    assert projected_flood.geometry.geom_equals(expected).all()
    assert projected_admin.geometry.geom_equals(admin.to_crs(5070).geometry).all()
    assert projected_flood['source_id'].tolist() == ['south', 'north']
    assert (flood.geometry.to_wkb().tolist(), admin.geometry.to_wkb().tolist()) == original_wkb


@pytest.mark.parametrize('geometry_kind', ['multipart', 'touching_hole'])
def test_existing_vertex_in_another_part_or_ring_still_nodes_the_touched_edge(geometry_kind):
    exterior = box(-122, 37, -121.99, 37.01)
    noded_exterior = Polygon([
        (-122, 37), (-121.99, 37), (-121.99, 37.01),
        (-121.995, 37.01), (-122, 37.01), (-122, 37),
    ])
    point_latitude = 37.013 if geometry_kind == 'multipart' else 37.007
    triangle = Polygon([
        (-121.995, 37.01), (-121.993, point_latitude),
        (-121.997, point_latitude), (-121.995, 37.01),
    ])
    if geometry_kind == 'multipart':
        source = MultiPolygon([exterior, triangle])
        expected_source = MultiPolygon([noded_exterior, triangle])
    else:
        source = Polygon(exterior.exterior.coords, [triangle.exterior.coords])
        expected_source = Polygon(noded_exterior.exterior.coords, [triangle.exterior.coords])
    assert source.is_valid and expected_source.is_valid
    assert source.equals(expected_source)
    flood = gpd.GeoDataFrame(geometry=[source], crs=4326)
    admin = gpd.GeoDataFrame(geometry=[box(-122.001, 36.999, -121.989, 37.014)], crs=4326)
    expected = gpd.GeoSeries([expected_source], crs=4326).to_crs(5070)

    projected, _ = _project_with_shared_nodes(flood, admin, expected.crs)

    assert projected.geometry.is_valid.all()
    assert projected.geometry.geom_equals(expected).all()
    assert projected.geometry.area.iloc[0] == pytest.approx(expected.area.iloc[0], rel=1e-12, abs=1e-6)
