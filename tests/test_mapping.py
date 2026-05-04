from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from fema_nfhl.mapping import build_flood_popup_rows, categorize_flood_hazard, create_interactive_map


def test_categorize_flood_hazard_matches_nfhl_grouped_legend() -> None:
    assert categorize_flood_hazard("AE", "").key == "one_percent"
    assert categorize_flood_hazard("AE", "FLOODWAY").key == "regulatory_floodway"
    assert categorize_flood_hazard("VE", "").key == "coastal_high_hazard"
    assert categorize_flood_hazard("D", "").key == "undetermined"
    assert categorize_flood_hazard("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD").key == "zero_two_percent"
    assert categorize_flood_hazard("X", "1 PCT FUTURE CONDITIONS").key == "future_conditions"
    assert categorize_flood_hazard("X", "AREA WITH REDUCED FLOOD RISK DUE TO LEVEE").key == "reduced_levee"
    assert categorize_flood_hazard("D", "AREA WITH FLOOD RISK DUE TO LEVEE").key == "levee_risk"
    assert categorize_flood_hazard("X", "AREA OF MINIMAL FLOOD HAZARD").key == "minimal"
    assert categorize_flood_hazard("OPEN WATER", "").key == "open_water"
    assert categorize_flood_hazard("AREA NOT INCLUDED", "").key == "other"
    assert categorize_flood_hazard("ANI", "").key == "other"


def test_build_flood_popup_rows_hides_placeholders_and_formats_values() -> None:
    rows = build_flood_popup_rows(
        {
            "FLD_ZONE": "AO",
            "ZONE_SUBTY": "",
            "SFHA_TF": "T",
            "STATIC_BFE": -9999.0,
            "DEPTH": 1.0,
            "LEN_UNIT": "Feet",
            "V_DATUM": None,
            "SOURCE_CIT": "06001C_FIRM12",
            "STUDY_TYP": "NP",
        }
    )

    assert ("Flood Zone", "AO") in rows
    assert ("Special Flood Hazard Area", "Yes") in rows
    assert ("Flood Depth", "1 ft") in rows
    assert ("FEMA Source Citation", "06001C_FIRM12") in rows
    assert not any(label == "Study Type" for label, _ in rows)
    assert not any(label == "Static Base Flood Elevation" for label, _ in rows)
    assert not any(value in {"-9999", "-9999.0", "None"} for _, value in rows)


def test_build_flood_popup_rows_notes_missing_depth_or_bfe_for_sfha() -> None:
    rows = build_flood_popup_rows(
        {
            "FLD_ZONE": "A",
            "ZONE_SUBTY": "",
            "SFHA_TF": "T",
            "STATIC_BFE": "-9999",
            "DEPTH": "-9999",
            "SOURCE_CIT": "06001C_STUDY4",
        }
    )

    assert ("Flood Zone", "A") in rows
    assert ("Depth/BFE", "Not provided in this NFHL feature") in rows
    assert ("FEMA Source Citation", "06001C_STUDY4") in rows


def test_build_flood_popup_rows_interprets_area_not_included_as_mapping_status() -> None:
    rows = build_flood_popup_rows(
        {
            "FLD_ZONE": "AREA NOT INCLUDED",
            "ZONE_SUBTY": "",
            "SFHA_TF": "T",
            "STATIC_BFE": "-9999",
            "DEPTH": "-9999",
            "SOURCE_CIT": "06001C_FIRM",
        }
    )

    assert ("Flood Zone", "Area Not Included") in rows
    assert (
        "Interpretation",
        "No FEMA flood hazard data is shown for this area in the current NFHL/FIRM dataset.",
    ) in rows
    assert ("FEMA Source Citation", "06001C_FIRM") in rows
    assert not any(label == "Flood Hazard Category" for label, _ in rows)
    assert not any(label == "Special Flood Hazard Area" for label, _ in rows)


def test_create_interactive_map_writes_grouped_and_detailed_layers(tmp_path) -> None:
    flood = gpd.GeoDataFrame(
        {
            "FLD_ZONE": ["AE", "X", "VE", "AREA NOT INCLUDED"],
            "ZONE_SUBTY": ["FLOODWAY", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "", ""],
            "SFHA_TF": ["T", "F", "T", "F"],
            "STATIC_BFE": [10.0, -9999.0, -9999.0, -9999.0],
            "DEPTH": [-9999.0, -9999.0, -9999.0, -9999.0],
            "LEN_UNIT": ["Feet", "", "", ""],
            "V_DATUM": ["NAVD88", "", "", ""],
            "SOURCE_CIT": ["06001C_STUDY11", "06001C_FIRM12", "06001C_STUDY11", "06001C_FIRM"],
        },
        geometry=[
            Polygon([(-122.3, 37.7), (-122.29, 37.7), (-122.29, 37.71), (-122.3, 37.71)]),
            Polygon([(-122.28, 37.7), (-122.27, 37.7), (-122.27, 37.71), (-122.28, 37.71)]),
            Polygon([(-122.26, 37.7), (-122.25, 37.7), (-122.25, 37.71), (-122.26, 37.71)]),
            Polygon([(-122.24, 37.7), (-122.23, 37.7), (-122.23, 37.71), (-122.24, 37.71)]),
        ],
        crs="EPSG:4326",
    )
    bfe = gpd.GeoDataFrame(
        {"ELEV": [10.0], "V_DATUM": ["NAVD88"]},
        geometry=[LineString([(-122.3, 37.705), (-122.25, 37.705)])],
        crs="EPSG:4326",
    )
    flood.to_file(tmp_path / "S_FLD_HAZ_AR.shp")
    bfe.to_file(tmp_path / "S_BFE.shp")

    output_html = create_interactive_map(tmp_path, tmp_path / "map.html")
    html = output_html.read_text(encoding="utf-8")

    assert "Map Legend" in html
    assert "Grouped: Regulatory Floodway" in html
    assert "Grouped: 0.2% Annual Chance Flood Hazard" in html
    assert "Grouped: Coastal High Hazard Area" in html
    assert "Grouped: Other NFHL / Mapping Status" in html
    assert "Other NFHL Flood Hazard Category" not in html
    assert "Detailed ZONE_SUBTY: AE - FLOODWAY" in html
    assert "Detailed ZONE_SUBTY: X - 0.2 PCT ANNUAL CHANCE FLOOD HAZARD" in html
    assert "Detailed FLD_ZONE: VE" in html
    assert "Detailed FLD_ZONE: Area Not Included / no mapped flood hazard data" in html
    assert "No FEMA flood hazard data is shown for this area in the current NFHL/FIRM dataset." in html
    assert "Unspecified" not in html
    assert "Base Flood Elevation (BFE) lines" in html
    assert "Mapped 1% annual chance / base-flood hazard areas" in html
    assert "Base Flood Elevation lines from the FEMA S_BFE layer where available" in html
    assert "nfhl-legend-panel" in html
    assert "max-height: 70vh" in html
    assert "overflow-y: auto" in html
    assert "\\25BE" in html
    assert "\\25B8" in html
    assert "Static Base Flood Elevation" in html
    assert "floodTooltipHtml" in html
    assert "floodPopupHtml" in html
    assert "addLazyGeoJson" in html
    assert "groupedLayerSpecs" in html
    assert "_nfhl_tooltip_html" not in html
    assert "_nfhl_popup_html" not in html
    assert "Raw FEMA attributes" in html
    assert "Advanced FEMA attributes" not in html
    assert "Basemap: CARTO Positron" in html
    assert "commonly shaded Zone X where mapped" in html
    assert "not an official FEMA flood determination" in html
    assert "Find Location" in html
    assert "Longitude / X" in html
    assert "Latitude / Y" in html
    assert "Coordinates are interpreted as WGS84 longitude/latitude" in html
    assert "OpenStreetMap Nominatim" in html
    assert "Esri ArcGIS World Geocoder" in html
    assert "geocodeAddressVariantsArcgis" in html
    assert "jsonpRequest" in html
    assert "findAddressCandidates" in html
    assert "Address lookup sends the typed address" in html
    assert "point with visible NFHL polygons" in html
    assert "featureContainsPoint" in html
    assert "NFHL relationship" in html
    assert "addressQueryVariants" in html
    assert "expandStreetAbbreviations" in html
    assert "geocodeAddressVariantsNominatim" in html
    assert "uniqueGeocodeVariants" in html
    assert "geocoderMatchLooksPrecise" in html
    assert "requiredHouseNumber" in html
    assert "placeWithoutZip" in html
    assert "zipMatch" in html
    assert "addressdetails=1" in html
    assert "maxLocations=3" in html
    assert "Trying street-address matches first; city/ZIP fallback is marked approximate" in html
    assert "Approximate location only" in html
    assert "Approximate geocode by" in html
    assert "OpenStreetMap and Esri did not return a usable match" in html
    assert "Outside loaded NFHL map extent" in html
    assert "Generate a map for the relevant county/state package" in html
    assert "countrycodes=us" in html
