"""Create interactive Folium maps from FEMA NFHL layers."""

from __future__ import annotations

from dataclasses import dataclass
import html
import json
import logging
from pathlib import Path

from .catalog import find_source_by_layer, read_layer
from .utils import ensure_dir, require_optional


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HazardCategory:
    """Grouped FEMA flood hazard display category."""

    key: str
    label: str
    color: str
    explanation: str
    fill_opacity: float = 0.5


HAZARD_CATEGORIES = {
    "one_percent": HazardCategory(
        key="one_percent",
        label="1% Annual Chance Flood Hazard",
        color="#9b6be8",
        explanation="Mapped 1% annual chance / base-flood hazard areas.",
        fill_opacity=0.5,
    ),
    "regulatory_floodway": HazardCategory(
        key="regulatory_floodway",
        label="Regulatory Floodway",
        color="#5b2db4",
        explanation="Area reserved to convey the 1% annual chance base flood.",
        fill_opacity=0.65,
    ),
    "coastal_high_hazard": HazardCategory(
        key="coastal_high_hazard",
        label="Coastal High Hazard Area",
        color="#f59f45",
        explanation="V/VE coastal flood zone with wave-action hazard.",
        fill_opacity=0.58,
    ),
    "undetermined": HazardCategory(
        key="undetermined",
        label="Undetermined Flood Hazard",
        color="#f3dfb6",
        explanation="Zone D; flood hazard possible but not determined.",
        fill_opacity=0.52,
    ),
    "zero_two_percent": HazardCategory(
        key="zero_two_percent",
        label="0.2% Annual Chance Flood Hazard",
        color="#f6c46f",
        explanation="Moderate flood hazard, commonly shaded Zone X where mapped.",
        fill_opacity=0.52,
    ),
    "future_conditions": HazardCategory(
        key="future_conditions",
        label="Future Conditions 1% Flood Hazard",
        color="#f1a7a0",
        explanation="Future land-use/development-based 1% flood hazard; not necessarily climate-change-adjusted.",
        fill_opacity=0.52,
    ),
    "reduced_levee": HazardCategory(
        key="reduced_levee",
        label="Area with Reduced Risk Due to Levee",
        color="#c6a7d8",
        explanation="Levee-influenced area with reduced, not eliminated, flood risk.",
        fill_opacity=0.52,
    ),
    "levee_risk": HazardCategory(
        key="levee_risk",
        label="Area with Risk Due to Levee",
        color="#de7f58",
        explanation="Levee-influenced area where flood risk remains or is uncertain.",
        fill_opacity=0.56,
    ),
    "minimal": HazardCategory(
        key="minimal",
        label="Minimal Flood Hazard",
        color="#d7d7d7",
        explanation="Unshaded Zone X / minimal mapped flood hazard.",
        fill_opacity=0.18,
    ),
    "open_water": HazardCategory(
        key="open_water",
        label="Open Water",
        color="#6aaed6",
        explanation="Mapped open water feature; not a probability-based flood zone.",
        fill_opacity=0.35,
    ),
    "other": HazardCategory(
        key="other",
        label="Other NFHL / Mapping Status",
        color="#9c755f",
        explanation="Mapping-status or other NFHL records that are not flood probability zones.",
        fill_opacity=0.45,
    ),
}

CATEGORY_ORDER = [
    "one_percent",
    "regulatory_floodway",
    "coastal_high_hazard",
    "undetermined",
    "zero_two_percent",
    "future_conditions",
    "reduced_levee",
    "levee_risk",
    "minimal",
    "open_water",
    "other",
]

ZONE_COLORS = {
    "A": "#4e79a7",
    "AE": "#1f77b4",
    "AH": "#76b7b2",
    "AO": "#59a14f",
    "VE": "#e15759",
    "V": "#b07aa1",
    "X": "#bab0ab",
    "0.2 PCT ANNUAL CHANCE FLOOD HAZARD": "#f28e2b",
}

FLOOD_DISPLAY_FIELDS = ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "STATIC_BFE", "DEPTH", "LEN_UNIT", "V_DATUM", "SOURCE_CIT"]
BFE_DISPLAY_FIELDS = ["ELEV", "LEN_UNIT", "V_DATUM", "SOURCE_CIT"]
ADVANCED_FEMA_FIELDS = ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "STATIC_BFE", "DEPTH", "LEN_UNIT", "V_DATUM", "SOURCE_CIT", "STUDY_TYP"]
FIELD_ALIASES = {
    "FLD_ZONE": "Flood Zone",
    "ZONE_SUBTY": "Zone Subtype",
    "SFHA_TF": "Special Flood Hazard Area",
    "STATIC_BFE": "Static Base Flood Elevation",
    "ELEV": "Base Flood Elevation",
    "DEPTH": "Flood Depth",
    "LEN_UNIT": "Units",
    "V_DATUM": "Vertical Datum",
    "SOURCE_CIT": "FEMA Source Citation",
    "STUDY_TYP": "Study Type",
}


def create_interactive_map(input_path: str | Path, output_html: str | Path) -> Path:
    """Create an interactive flood hazard map from extracted NFHL layers."""

    folium = require_optional("folium")
    flood_source = find_source_by_layer(input_path, ["S_FLD_HAZ_AR"])
    if flood_source is None:
        raise FileNotFoundError("Could not find S_FLD_HAZ_AR in extracted NFHL input.")

    flood = read_layer(flood_source)
    if flood.crs is None:
        raise ValueError("S_FLD_HAZ_AR has no CRS; cannot create web map safely.")
    flood_web = flood.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = flood_web.total_bounds
    center_y = float((miny + maxy) / 2)
    center_x = float((minx + maxx) / 2)
    fmap = folium.Map(location=[center_y, center_x], zoom_start=10, tiles=None)
    basemap = folium.TileLayer("CartoDB positron", name="Basemap: CARTO Positron", control=True).add_to(fmap)

    flood_web = flood_web.copy()
    flood_web["_nfhl_category"] = [
        categorize_flood_hazard(_prop_value(row, "FLD_ZONE"), _prop_value(row, "ZONE_SUBTY")).key
        for _, row in flood_web.iterrows()
    ]
    flood_web["_nfhl_detailed_label"] = [
        _detailed_label(_prop_value(row, "FLD_ZONE"), _prop_value(row, "ZONE_SUBTY")) for _, row in flood_web.iterrows()
    ]
    flood_data = _compact_geojson(
        flood_web,
        fields=[*ADVANCED_FEMA_FIELDS, "FLD_AR_ID", "DFIRM_ID"],
        extra_fields=["_nfhl_category", "_nfhl_detailed_label"],
    )
    grouped_layer_specs = _grouped_layer_specs(flood_web)
    detailed_layer_specs = _detailed_layer_specs(flood_web)

    bfe_source = find_source_by_layer(input_path, ["S_BFE"])
    bfe_data = {"type": "FeatureCollection", "features": []}
    if bfe_source is not None:
        bfe = read_layer(bfe_source)
        if bfe.crs:
            bfe_web = bfe.to_crs("EPSG:4326")
            bfe_data = _compact_geojson(bfe_web, fields=BFE_DISPLAY_FIELDS, extra_fields=[])
        else:
            LOGGER.warning("S_BFE has no CRS and was skipped in the web map.")

    fmap.get_root().script.add_child(
        folium.Element(
            _optimized_layers_script(
                map_name=fmap.get_name(),
                basemap_name=basemap.get_name(),
                flood_data=flood_data,
                bfe_data=bfe_data,
                grouped_layer_specs=grouped_layer_specs,
                detailed_layer_specs=detailed_layer_specs,
            )
        )
    )
    fmap.get_root().html.add_child(folium.Element(_legend_html()))
    _add_location_finder(folium, fmap, bounds=(minx, miny, maxx, maxy))
    output_html = Path(output_html)
    ensure_dir(output_html.parent)
    fmap.save(output_html)
    LOGGER.info("Wrote %s", output_html)
    return output_html


def _polygon_style(feature: dict) -> dict[str, object]:
    zone = str(feature.get("properties", {}).get("FLD_ZONE", "")).upper()
    color = ZONE_COLORS.get(zone, "#9c755f")
    return {"fillColor": color, "color": color, "weight": 1, "fillOpacity": 0.45}


def categorize_flood_hazard(fld_zone: object, zone_subty: object) -> HazardCategory:
    """Classify FEMA FLD_ZONE/ZONE_SUBTY into grouped map-legend categories."""

    zone = _normalize(fld_zone)
    subtype = _normalize(zone_subty)
    if _is_area_not_included(zone):
        return HAZARD_CATEGORIES["other"]
    if _is_regulatory_floodway(subtype):
        return HAZARD_CATEGORIES["regulatory_floodway"]
    if zone in {"V", "VE"}:
        return HAZARD_CATEGORIES["coastal_high_hazard"]
    if "FUTURE CONDITION" in subtype or "FUTURE CONDITON" in subtype:
        return HAZARD_CATEGORIES["future_conditions"]
    if "REDUCED FLOOD RISK DUE TO LEVEE" in subtype or "REDUCED FLOOD HAZARD DUE TO" in subtype:
        return HAZARD_CATEGORIES["reduced_levee"]
    if "FLOOD RISK DUE TO LEVEE" in subtype or "UNDETERMINED FLOOD HAZARD DUE TO NON" in subtype:
        return HAZARD_CATEGORIES["levee_risk"]
    if zone == "D":
        return HAZARD_CATEGORIES["undetermined"]
    if zone == "X" and (
        "0.2 PCT" in subtype
        or "0.2 PERCENT" in subtype
        or "1 PCT DEPTH LESS THAN 1 FOOT" in subtype
        or "1 PERCENT DEPTH LESS THAN 1 FOOT" in subtype
        or "1 PCT DRAINAGE AREA LESS THAN 1 SQUARE MILE" in subtype
        or "1 PERCENT DRAINAGE AREA LESS THAN 1 SQUARE MILE" in subtype
    ):
        return HAZARD_CATEGORIES["zero_two_percent"]
    if zone == "X" or "MINIMAL FLOOD HAZARD" in subtype:
        return HAZARD_CATEGORIES["minimal"]
    if zone == "OPEN WATER":
        return HAZARD_CATEGORIES["open_water"]
    if zone in {"A", "AE", "AH", "AO", "AR", "A99"}:
        return HAZARD_CATEGORIES["one_percent"]
    return HAZARD_CATEGORIES["other"]


def _category_style(category: HazardCategory) -> dict[str, object]:
    return {
        "fillColor": category.color,
        "color": category.color,
        "weight": 1,
        "fillOpacity": category.fill_opacity,
    }


def _compact_geojson(gdf, *, fields: list[str], extra_fields: list[str]) -> dict:
    """Return GeoJSON with only map-visible attributes and geometry."""

    columns: list[str] = []
    for field in [*fields, *extra_fields]:
        actual = _actual_column(gdf.columns, field)
        if actual and actual not in columns:
            columns.append(actual)
    compact = gdf[[*columns, gdf.geometry.name]].copy()
    return json.loads(compact.to_json(drop_id=True))


def _grouped_layer_specs(gdf) -> list[dict[str, object]]:
    """Build grouped hazard layer metadata without duplicating feature geometry."""

    present = set(gdf["_nfhl_category"].dropna().astype(str))
    specs: list[dict[str, object]] = []
    for category_key in CATEGORY_ORDER:
        if category_key not in present:
            continue
        category = HAZARD_CATEGORIES[category_key]
        specs.append(
            {
                "name": f"Grouped: {category.label}",
                "category": category_key,
                "style": _category_style(category),
                "show": category_key != "minimal",
            }
        )
    return specs


def _detailed_layer_specs(gdf) -> list[dict[str, object]]:
    """Build detailed zone/subtype layer metadata without duplicating feature geometry."""

    label_names: dict[str, str] = {}
    for _, row in gdf.iterrows():
        label = _detailed_label(_prop_value(row, "FLD_ZONE"), _prop_value(row, "ZONE_SUBTY"))
        if label:
            label_names[label] = _detailed_layer_name(_prop_value(row, "FLD_ZONE"), _prop_value(row, "ZONE_SUBTY"))

    specs = [
        {"name": name, "label": label, "show": False}
        for label, name in sorted(label_names.items(), key=lambda item: item[1])
    ]
    specs.append({"name": "Detailed: all FEMA flood hazard polygons", "label": None, "show": False})
    return specs


def _optimized_layers_script(
    *,
    map_name: str,
    basemap_name: str,
    flood_data: dict,
    bfe_data: dict,
    grouped_layer_specs: list[dict[str, object]],
    detailed_layer_specs: list[dict[str, object]],
) -> str:
    """Create Leaflet layers from one trimmed feature store in browser JavaScript."""

    category_labels = {key: category.label for key, category in HAZARD_CATEGORIES.items()}
    zone_colors = dict(ZONE_COLORS)
    script = r"""
    (function() {
      function installNfhlOptimizedLayers() {
      if (typeof L === "undefined" || typeof __MAP_NAME__ === "undefined" || typeof __BASEMAP_NAME__ === "undefined") {
        setTimeout(installNfhlOptimizedLayers, 50);
        return;
      }
      const map = __MAP_NAME__;
      const basemapLayer = __BASEMAP_NAME__;
      const floodData = __FLOOD_DATA__;
      const bfeData = __BFE_DATA__;
      const groupedLayerSpecs = __GROUPED_LAYER_SPECS__;
      const detailedLayerSpecs = __DETAILED_LAYER_SPECS__;
      const categoryLabels = __CATEGORY_LABELS__;
      const zoneColors = __ZONE_COLORS__;
      const fieldAliases = __FIELD_ALIASES__;
      const advancedFemaFields = __ADVANCED_FEMA_FIELDS__;
      const bfeDisplayFields = __BFE_DISPLAY_FIELDS__;

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
      }

      function validValue(value) {
        if (value === null || value === undefined) {
          return false;
        }
        const text = String(value).trim();
        if (!text || ["nan", "none", "null", "<null>"].indexOf(text.toLowerCase()) !== -1) {
          return false;
        }
        return Number(text) !== -9999;
      }

      function yesNo(value) {
        const text = value === null || value === undefined ? "" : String(value).trim().toUpperCase();
        if (text === "T") {
          return "Yes";
        }
        if (text === "F") {
          return "No";
        }
        return null;
      }

      function normalizeValue(value) {
        if (!validValue(value)) {
          return "";
        }
        return String(value).trim().toUpperCase();
      }

      function isAreaNotIncluded(value) {
        const zone = normalizeValue(value);
        return zone === "AREA NOT INCLUDED" || zone === "ANI";
      }

      function displayFloodZone(value) {
        const zone = normalizeValue(value);
        if (zone === "AREA NOT INCLUDED" || zone === "ANI") {
          return "Area Not Included";
        }
        if (zone === "OPEN WATER") {
          return "Open Water";
        }
        return validValue(value) ? String(value) : "";
      }

      function formatElevation(value, unit) {
        if (!validValue(value)) {
          return null;
        }
        const unitText = validValue(unit) ? String(unit).trim() : "";
        const unitLookup = {"FEET": "ft", "FOOT": "ft", "FT": "ft", "METERS": "m", "METER": "m", "M": "m"};
        const unitLabel = unitLookup[unitText.toUpperCase()] || unitText;
        const numeric = Number(value);
        const valueText = Number.isFinite(numeric) ? String(Number(numeric.toPrecision(12))) : String(value);
        return (valueText + " " + unitLabel).trim();
      }

      function rawDisplayValue(value) {
        if (value === null || value === undefined) {
          return "null";
        }
        const text = String(value).trim();
        return text || "null";
      }

      function rowsHtml(rows, advancedRows, compact) {
        const rowHtml = rows.map(function(row) {
          return "<tr>" +
            '<th style="text-align:left;vertical-align:top;padding:2px 8px 2px 0;color:#374151;">' + escapeHtml(row[0]) + "</th>" +
            '<td style="text-align:left;vertical-align:top;padding:2px 0;color:#111827;">' + escapeHtml(row[1]) + "</td>" +
            "</tr>";
        }).join("");
        let advancedHtml = "";
        if (advancedRows && advancedRows.length) {
          const advancedRowHtml = advancedRows.map(function(row) {
            return "<tr>" +
              '<th style="text-align:left;vertical-align:top;padding:2px 8px 2px 0;color:#4b5563;">' + escapeHtml(row[0]) + "</th>" +
              '<td style="text-align:left;vertical-align:top;padding:2px 0;color:#374151;">' + escapeHtml(row[1]) + "</td>" +
              "</tr>";
          }).join("");
          advancedHtml = '<details style="margin-top:8px;">' +
            '<summary style="cursor:pointer;color:#1f2937;font-weight:600;">Raw FEMA attributes</summary>' +
            '<table style="border-collapse:collapse;margin-top:4px;font-size:11px;">' + advancedRowHtml + "</table>" +
            "</details>";
        }
        const width = compact ? "300px" : "380px";
        return '<div style="font-family:Arial, sans-serif;font-size:12px;line-height:1.25;max-width:' + width + ';">' +
          '<table style="border-collapse:collapse;">' + rowHtml + "</table>" + advancedHtml + "</div>";
      }

      function shouldNoteMissingDepthOrBfe(props, staticBfe, depth) {
        if (staticBfe || depth) {
          return false;
        }
        const zone = normalizeValue(props.FLD_ZONE);
        const category = props._nfhl_category || "";
        return ["one_percent", "coastal_high_hazard", "regulatory_floodway"].indexOf(category) !== -1 ||
          ["A", "AE", "AH", "AO", "AR", "A99", "V", "VE"].indexOf(zone) !== -1;
      }

      function floodRows(props) {
        const rows = [];
        const zone = props.FLD_ZONE;
        const subtype = props.ZONE_SUBTY;
        if (isAreaNotIncluded(zone)) {
          rows.push([fieldAliases.FLD_ZONE, "Area Not Included"]);
          rows.push(["Interpretation", "No FEMA flood hazard data is shown for this area in the current NFHL/FIRM dataset."]);
          if (validValue(props.SOURCE_CIT)) {
            rows.push([fieldAliases.SOURCE_CIT, String(props.SOURCE_CIT)]);
          }
          return rows;
        }
        const categoryLabel = categoryLabels[props._nfhl_category] || "Other NFHL / Mapping Status";
        const zoneLabel = displayFloodZone(zone);
        if (zoneLabel) {
          rows.push([fieldAliases.FLD_ZONE, zoneLabel]);
        }
        rows.push(["Flood Hazard Category", categoryLabel]);
        if (validValue(subtype)) {
          rows.push([fieldAliases.ZONE_SUBTY, String(subtype)]);
        }
        const sfha = yesNo(props.SFHA_TF);
        if (sfha) {
          rows.push([fieldAliases.SFHA_TF, sfha]);
        }
        const staticBfe = formatElevation(props.STATIC_BFE, props.LEN_UNIT);
        const depth = formatElevation(props.DEPTH, props.LEN_UNIT);
        if (staticBfe) {
          rows.push([fieldAliases.STATIC_BFE, staticBfe]);
        }
        if (depth) {
          rows.push([fieldAliases.DEPTH, depth]);
        }
        if (shouldNoteMissingDepthOrBfe(props, staticBfe, depth)) {
          rows.push(["Depth/BFE", "Not provided in this NFHL feature"]);
        }
        if (validValue(props.V_DATUM)) {
          rows.push([fieldAliases.V_DATUM, String(props.V_DATUM)]);
        }
        if (validValue(props.SOURCE_CIT)) {
          rows.push([fieldAliases.SOURCE_CIT, String(props.SOURCE_CIT)]);
        }
        return rows;
      }

      function advancedRows(props, fields) {
        return fields.filter(function(field) {
          return Object.prototype.hasOwnProperty.call(props, field);
        }).map(function(field) {
          return [field, rawDisplayValue(props[field])];
        });
      }

      function floodTooltipHtml(props) {
        return rowsHtml(floodRows(props), null, true);
      }

      function floodPopupHtml(props) {
        return rowsHtml(floodRows(props), advancedRows(props, advancedFemaFields), false);
      }

      function bfeRows(props) {
        const rows = [];
        const elev = formatElevation(props.ELEV, props.LEN_UNIT);
        if (elev) {
          rows.push([fieldAliases.ELEV, elev]);
        }
        if (validValue(props.V_DATUM)) {
          rows.push([fieldAliases.V_DATUM, String(props.V_DATUM)]);
        }
        if (validValue(props.SOURCE_CIT)) {
          rows.push([fieldAliases.SOURCE_CIT, String(props.SOURCE_CIT)]);
        }
        return rows.length ? rows : [["BFE Lines", "No display attributes provided"]];
      }

      function bfeTooltipHtml(props) {
        return rowsHtml(bfeRows(props), null, true);
      }

      function bfePopupHtml(props) {
        return rowsHtml(bfeRows(props), advancedRows(props, bfeDisplayFields), false);
      }

      function polygonStyle(feature) {
        const props = feature.properties || {};
        const zone = normalizeValue(props.FLD_ZONE);
        const color = zoneColors[zone] || "#9c755f";
        return {fillColor: color, color: color, weight: 1, fillOpacity: 0.45};
      }

      function onEachFloodFeature(feature, layer) {
        layer.bindTooltip(function() {
          return floodTooltipHtml(feature.properties || {});
        }, {sticky: true, maxWidth: 320});
        layer.bindPopup(function() {
          return floodPopupHtml(feature.properties || {});
        }, {maxWidth: 420});
      }

      function onEachBfeFeature(feature, layer) {
        layer.bindTooltip(function() {
          return bfeTooltipHtml(feature.properties || {});
        }, {sticky: true, maxWidth: 280});
        layer.bindPopup(function() {
          return bfePopupHtml(feature.properties || {});
        }, {maxWidth: 380});
      }

      function addLazyGeoJson(layerGroup, data, options) {
        if (layerGroup._nfhlLoaded) {
          return;
        }
        L.geoJSON(data, options).eachLayer(function(layer) {
          layerGroup.addLayer(layer);
        });
        layerGroup._nfhlLoaded = true;
      }

      const overlays = {};
      groupedLayerSpecs.forEach(function(spec) {
        const layerGroup = L.layerGroup();
        layerGroup._nfhlLoader = function() {
          addLazyGeoJson(layerGroup, floodData, {
            filter: function(feature) {
              return feature.properties && feature.properties._nfhl_category === spec.category;
            },
            style: function() {
              return spec.style;
            },
            onEachFeature: onEachFloodFeature
          });
        };
        overlays[spec.name] = layerGroup;
        if (spec.show) {
          layerGroup._nfhlLoader();
          layerGroup.addTo(map);
        }
      });

      detailedLayerSpecs.forEach(function(spec) {
        const layerGroup = L.layerGroup();
        layerGroup._nfhlLoader = function() {
          addLazyGeoJson(layerGroup, floodData, {
            filter: function(feature) {
              return spec.label === null || (feature.properties && feature.properties._nfhl_detailed_label === spec.label);
            },
            style: polygonStyle,
            onEachFeature: onEachFloodFeature
          });
        };
        overlays[spec.name] = layerGroup;
        if (spec.show) {
          layerGroup._nfhlLoader();
          layerGroup.addTo(map);
        }
      });

      if (bfeData.features && bfeData.features.length) {
        const bfeLayer = L.layerGroup();
        bfeLayer._nfhlLoader = function() {
          addLazyGeoJson(bfeLayer, bfeData, {
            style: function() {
              return {color: "#d7191c", weight: 2};
            },
            onEachFeature: onEachBfeFeature
          });
        };
        bfeLayer._nfhlLoader();
        bfeLayer.addTo(map);
        overlays["Base Flood Elevation (BFE) lines"] = bfeLayer;
      }

      map.on("overlayadd", function(event) {
        if (event.layer && event.layer._nfhlLoader) {
          event.layer._nfhlLoader();
        }
      });

      L.control.layers({"Basemap: CARTO Positron": basemapLayer}, overlays, {collapsed: true}).addTo(map);
      window.nfhlBuildFloodTooltipHtml = floodTooltipHtml;
      }
      installNfhlOptimizedLayers();
    })();
    """
    replacements = {
        "__MAP_NAME__": map_name,
        "__BASEMAP_NAME__": basemap_name,
        "__FLOOD_DATA__": _json_for_script(flood_data),
        "__BFE_DATA__": _json_for_script(bfe_data),
        "__GROUPED_LAYER_SPECS__": _json_for_script(grouped_layer_specs),
        "__DETAILED_LAYER_SPECS__": _json_for_script(detailed_layer_specs),
        "__CATEGORY_LABELS__": _json_for_script(category_labels),
        "__ZONE_COLORS__": _json_for_script(zone_colors),
        "__FIELD_ALIASES__": _json_for_script(FIELD_ALIASES),
        "__ADVANCED_FEMA_FIELDS__": _json_for_script(ADVANCED_FEMA_FIELDS),
        "__BFE_DISPLAY_FIELDS__": _json_for_script(BFE_DISPLAY_FIELDS),
    }
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    return script


def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _feature_tooltip(folium, *, max_width: int):
    return folium.GeoJsonTooltip(
        fields=["_nfhl_tooltip_html"],
        labels=False,
        sticky=True,
        style=f"max-width: {max_width}px;",
    )


def _feature_popup(folium, *, max_width: int):
    return folium.GeoJsonPopup(fields=["_nfhl_popup_html"], labels=False, max_width=max_width)


def _add_location_finder(folium, fmap, *, bounds: tuple[float, float, float, float]) -> None:
    root = fmap.get_root()
    root.header.add_child(folium.Element(_location_finder_css()))
    root.script.add_child(folium.Element(_location_finder_script(fmap.get_name(), bounds)))


def _location_finder_css() -> str:
    return """
    <style>
      .nfhl-location-control {
        background: rgba(255,255,255,.94);
        border: 1px solid #9ca3af;
        border-radius: 2px;
        box-shadow: 0 1px 5px rgba(0,0,0,.28);
        color: #111827;
        font: 12px/1.3 Arial, sans-serif;
        max-width: 310px;
      }
      .nfhl-location-control details {
        padding: 9px 10px;
      }
      .nfhl-location-control summary {
        cursor: pointer;
        font-weight: 700;
        list-style: none;
      }
      .nfhl-location-control summary::-webkit-details-marker {
        display: none;
      }
      .nfhl-location-control summary::after {
        content: " \\25BE";
        color: #6b7280;
        font-size: 11px;
        font-weight: 400;
      }
      .nfhl-location-control details:not([open]) summary::after {
        content: " \\25B8";
      }
      .nfhl-location-body {
        margin-top: 8px;
      }
      .nfhl-location-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px;
      }
      .nfhl-location-control label {
        color: #374151;
        display: block;
        font-size: 11px;
        margin: 6px 0 2px;
      }
      .nfhl-location-control input[type="text"] {
        border: 1px solid #cbd5e1;
        border-radius: 2px;
        box-sizing: border-box;
        font: 12px Arial, sans-serif;
        padding: 4px 5px;
        width: 100%;
      }
      .nfhl-location-control button {
        background: #1f2937;
        border: 0;
        border-radius: 2px;
        color: white;
        cursor: pointer;
        font: 600 12px Arial, sans-serif;
        margin-top: 7px;
        padding: 5px 8px;
      }
      .nfhl-location-control button.secondary {
        background: #4b5563;
      }
      .nfhl-location-note {
        color: #4b5563;
        font-size: 11px;
        margin-top: 5px;
      }
      .nfhl-location-warning {
        background: #fff7ed;
        border-left: 3px solid #f97316;
        color: #7c2d12;
        font-size: 11px;
        margin-top: 7px;
        padding: 5px 6px;
      }
      .nfhl-geocode-consent {
        align-items: flex-start;
        display: flex;
        gap: 5px;
        margin-top: 6px;
      }
      .nfhl-geocode-consent input {
        margin-top: 2px;
      }
      .nfhl-location-result {
        border-top: 1px solid #e5e7eb;
        color: #111827;
        margin-top: 9px;
        max-height: 210px;
        overflow-y: auto;
        padding-top: 7px;
      }
      .nfhl-location-result .nfhl-result-title {
        font-weight: 700;
        margin-bottom: 4px;
      }
    </style>
    """


def _location_finder_script(map_name: str, bounds: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bounds
    script = r"""
    (function() {
      function installNfhlLocationFinder() {
      const map = __MAP_NAME__;
      const markerLayer = L.layerGroup().addTo(map);
      const nfhlDataBounds = {
        minLng: __MINX__,
        minLat: __MINY__,
        maxLng: __MAXX__,
        maxLat: __MAXY__
      };

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
      }

      function toNumber(value) {
        const parsed = Number(String(value).trim());
        return Number.isFinite(parsed) ? parsed : null;
      }

      function pointWithinLoadedNfhlBounds(lng, lat) {
        return lng >= nfhlDataBounds.minLng && lng <= nfhlDataBounds.maxLng &&
          lat >= nfhlDataBounds.minLat && lat <= nfhlDataBounds.maxLat;
      }

      function expandStreetAbbreviations(address) {
        return address
          .replace(/\bDr\.?\b/gi, "Drive")
          .replace(/\bRd\.?\b/gi, "Road")
          .replace(/\bSt\.?\b/gi, "Street")
          .replace(/\bAve\.?\b/gi, "Avenue")
          .replace(/\bBlvd\.?\b/gi, "Boulevard")
          .replace(/\bLn\.?\b/gi, "Lane")
          .replace(/\bCt\.?\b/gi, "Court")
          .replace(/\bPl\.?\b/gi, "Place")
          .replace(/\bPkwy\.?\b/gi, "Parkway")
          .replace(/\bHwy\.?\b/gi, "Highway")
          .replace(/\bTer\.?\b/gi, "Terrace");
      }

      function uniqueGeocodeVariants(variants) {
        const seen = new Set();
        return variants.filter(function(variant) {
          if (!variant.query || seen.has(variant.query)) {
            return false;
          }
          seen.add(variant.query);
          return true;
        });
      }

      function geocoderMatchLooksPrecise(match, variant) {
        if (variant.precision !== "address" || !variant.requiredHouseNumber) {
          return true;
        }
        const address = match.address || {};
        const searchable = [
          match.display_name,
          match.name,
          match.address,
          address.house_number,
          address.road
        ].join(" ").toLowerCase();
        return searchable.indexOf(String(variant.requiredHouseNumber).toLowerCase()) !== -1;
      }

      function addressQueryVariants(address) {
        const trimmed = address.trim();
        const expanded = expandStreetAbbreviations(trimmed);
        const withoutZip = trimmed.replace(/\s+\d{5}(?:-\d{4})?\s*$/, "");
        const zipMatch = trimmed.match(/\b\d{5}(?:-\d{4})?\b/);
        const houseNumberMatch = trimmed.match(/^\s*(\d+[a-zA-Z]?)/);
        const houseNumber = houseNumberMatch ? houseNumberMatch[1] : "";
        const commaParts = trimmed.split(",").map(function(part) {
          return part.trim();
        }).filter(Boolean);
        const placeParts = commaParts.length > 1 ? commaParts.slice(1).join(", ") : "";
        const placeWithoutZip = placeParts.replace(/\s+\d{5}(?:-\d{4})?\s*$/, "");
        return {
          address: uniqueGeocodeVariants([
            {query: trimmed, precision: "address", requiredHouseNumber: houseNumber},
            {query: expanded, precision: "address", requiredHouseNumber: houseNumber},
            {query: trimmed + ", United States", precision: "address", requiredHouseNumber: houseNumber},
            {query: expanded + ", United States", precision: "address", requiredHouseNumber: houseNumber},
            {query: withoutZip, precision: "address", requiredHouseNumber: houseNumber},
            {query: expandStreetAbbreviations(withoutZip), precision: "address", requiredHouseNumber: houseNumber}
          ]),
          approximate: uniqueGeocodeVariants([
            {query: placeWithoutZip, precision: "approximate"},
            {query: placeWithoutZip ? placeWithoutZip + ", United States" : "", precision: "approximate"},
            {query: zipMatch ? zipMatch[0] : "", precision: "approximate"}
          ])
        };
      }

      function geocodeAddressVariantsNominatim(variants, index) {
        if (index >= variants.length) {
          return Promise.resolve({match: null, query: null, provider: "OpenStreetMap Nominatim"});
        }
        const variant = variants[index];
        const query = variant.query;
        const url = "https://nominatim.openstreetmap.org/search?format=json&limit=3&addressdetails=1&countrycodes=us&q=" +
          encodeURIComponent(query);
        return fetch(url, {headers: {"Accept": "application/json"}})
          .then(function(response) {
            if (!response.ok) {
              throw new Error("Geocoder request failed");
            }
            return response.json();
          })
          .then(function(data) {
            const preciseMatch = data.find(function(candidate) {
              return geocoderMatchLooksPrecise(candidate, variant);
            });
            if (preciseMatch) {
              return {match: preciseMatch, query: query, provider: "OpenStreetMap Nominatim", precision: variant.precision};
            }
            return geocodeAddressVariantsNominatim(variants, index + 1);
          });
      }

      function geocodeAddressVariants(variants) {
        const addressVariants = variants.address || [];
        const approximateVariants = variants.approximate || [];
        return geocodeAddressVariantsNominatim(addressVariants, 0)
          .then(function(result) {
            if (result.match) {
              return result;
            }
            return geocodeAddressVariantsArcgis(addressVariants, 0);
          })
          .catch(function() {
            return geocodeAddressVariantsArcgis(addressVariants, 0);
          })
          .then(function(result) {
            if (result.match || !approximateVariants.length) {
              return result;
            }
            return geocodeAddressVariantsNominatim(approximateVariants, 0)
              .then(function(approximateResult) {
                if (approximateResult.match) {
                  return approximateResult;
                }
                return geocodeAddressVariantsArcgis(approximateVariants, 0);
              })
              .catch(function() {
                return geocodeAddressVariantsArcgis(approximateVariants, 0);
              });
          });
      }

      function jsonpRequest(url, callbackParam) {
        return new Promise(function(resolve, reject) {
          const callbackName = "nfhlGeocodeCallback_" + Date.now() + "_" + Math.floor(Math.random() * 1000000);
          const separator = url.indexOf("?") === -1 ? "?" : "&";
          const script = document.createElement("script");
          let completed = false;
          const cleanup = function() {
            completed = true;
            if (script.parentNode) {
              script.parentNode.removeChild(script);
            }
            try {
              delete window[callbackName];
            } catch (error) {
              window[callbackName] = undefined;
            }
          };
          const timeout = setTimeout(function() {
            if (!completed) {
              cleanup();
              reject(new Error("Geocoder request timed out"));
            }
          }, 12000);
          window[callbackName] = function(data) {
            clearTimeout(timeout);
            cleanup();
            resolve(data);
          };
          script.onerror = function() {
            clearTimeout(timeout);
            cleanup();
            reject(new Error("Geocoder request failed"));
          };
          script.src = url + separator + encodeURIComponent(callbackParam) + "=" + encodeURIComponent(callbackName);
          document.head.appendChild(script);
        });
      }

      function geocodeAddressVariantsArcgis(variants, index) {
        if (index >= variants.length) {
          return Promise.resolve({match: null, query: null, provider: "Esri ArcGIS World Geocoder"});
        }
        const variant = variants[index];
        const query = variant.query;
        const url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates" +
          "?f=json&outFields=Match_addr,Addr_type,Score&countryCode=USA&maxLocations=3&SingleLine=" + encodeURIComponent(query);
        return jsonpRequest(url, "callback")
          .then(function(data) {
            const candidate = (data.candidates || []).find(function(item) {
              return item.location && geocoderMatchLooksPrecise({
                display_name: item.address,
                address: item.attributes && item.attributes.Match_addr
              }, variant);
            });
            if (candidate) {
              return {
                match: {
                  lat: candidate.location.y,
                  lon: candidate.location.x,
                  display_name: candidate.address || query
                },
                query: query,
                provider: "Esri ArcGIS World Geocoder",
                precision: variant.precision
              };
            }
            return geocodeAddressVariantsArcgis(variants, index + 1);
          });
      }

      function ringContainsPoint(ring, lng, lat) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const xi = ring[i][0], yi = ring[i][1];
          const xj = ring[j][0], yj = ring[j][1];
          const intersects = ((yi > lat) !== (yj > lat)) &&
            (lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi);
          if (intersects) {
            inside = !inside;
          }
        }
        return inside;
      }

      function polygonContainsPoint(polygon, lng, lat) {
        if (!polygon || polygon.length === 0 || !ringContainsPoint(polygon[0], lng, lat)) {
          return false;
        }
        for (let i = 1; i < polygon.length; i++) {
          if (ringContainsPoint(polygon[i], lng, lat)) {
            return false;
          }
        }
        return true;
      }

      function featureContainsPoint(feature, lng, lat) {
        if (!feature || !feature.geometry) {
          return false;
        }
        const geometry = feature.geometry;
        if (geometry.type === "Polygon") {
          return polygonContainsPoint(geometry.coordinates, lng, lat);
        }
        if (geometry.type === "MultiPolygon") {
          return geometry.coordinates.some(function(polygon) {
            return polygonContainsPoint(polygon, lng, lat);
          });
        }
        return false;
      }

      function collectFeatureLayers(layer, out) {
        if (layer && layer.feature && layer.feature.properties && layer.feature.properties.FLD_ZONE) {
          out.push(layer);
        }
        if (layer && typeof layer.eachLayer === "function") {
          layer.eachLayer(function(child) {
            collectFeatureLayers(child, out);
          });
        }
      }

      function findContainingFeatures(lng, lat) {
        const layers = [];
        map.eachLayer(function(layer) {
          collectFeatureLayers(layer, layers);
        });
        const seen = new Set();
        const matches = [];
        layers.forEach(function(layer) {
          const feature = layer.feature;
          const props = feature.properties || {};
          const id = props.FLD_AR_ID || props._leaflet_id || JSON.stringify(feature.geometry && feature.geometry.bbox || props);
          if (seen.has(id)) {
            return;
          }
          if (featureContainsPoint(feature, lng, lat)) {
            seen.add(id);
            matches.push(feature);
          }
        });
        return matches;
      }

      function renderLocationResult(resultEl, matches, lng, lat) {
        const outsideBounds = !pointWithinLoadedNfhlBounds(lng, lat);
        if (!matches.length) {
          if (outsideBounds) {
            resultEl.innerHTML = [
              '<div class="nfhl-result-title">Outside loaded NFHL map extent</div>',
              '<div>The point was located, but it is outside the extent of the NFHL data loaded in this HTML map.</div>',
              '<div class="nfhl-location-note">Generate a map for the relevant county/state package before interpreting this location against NFHL polygons.</div>'
            ].join("");
          } else {
            resultEl.innerHTML = [
              '<div class="nfhl-result-title">NFHL relationship</div>',
              '<div>No visible NFHL flood hazard polygon contains this point.</div>',
              '<div class="nfhl-location-note">This does not mean no flood risk, and it is not an official FEMA flood determination.</div>'
            ].join("");
          }
          return;
        }
        const rows = matches.slice(0, 3).map(function(feature) {
          const props = feature.properties || {};
          return (window.nfhlBuildFloodTooltipHtml ? window.nfhlBuildFloodTooltipHtml(props) : null) || (
            '<table><tr><th>Flood Zone</th><td>' + escapeHtml(props.FLD_ZONE || "Unknown") + '</td></tr></table>'
          );
        }).join("");
        const extra = matches.length > 3
          ? '<div class="nfhl-location-note">Additional overlapping NFHL polygons found: ' + (matches.length - 3) + '</div>'
          : '';
        resultEl.innerHTML = '<div class="nfhl-result-title">NFHL relationship</div>' + rows + extra;
      }

      function locatePoint(lat, lng, label, resultEl) {
        markerLayer.clearLayers();
        L.marker([lat, lng], {title: label}).addTo(markerLayer).bindPopup(escapeHtml(label)).openPopup();
        map.setView([lat, lng], Math.max(map.getZoom(), 14));
        const matches = findContainingFeatures(lng, lat);
        renderLocationResult(resultEl, matches, lng, lat);
      }

      const LocationControl = L.Control.extend({
        options: {position: "topleft"},
        onAdd: function() {
          const container = L.DomUtil.create("div", "nfhl-location-control leaflet-control");
          container.innerHTML = [
            '<details>',
            '<summary>Find Location</summary>',
            '<div class="nfhl-location-body">',
            '<div class="nfhl-location-grid">',
            '<div><label for="nfhl-lon">Longitude / X</label><input id="nfhl-lon" type="text" placeholder="-77.15"></div>',
            '<div><label for="nfhl-lat">Latitude / Y</label><input id="nfhl-lat" type="text" placeholder="39.08"></div>',
            '</div>',
            '<button type="button" id="nfhl-coordinate-button">Locate coordinates</button>',
            '<div class="nfhl-location-note">Coordinates are interpreted as WGS84 longitude/latitude (EPSG:4326) and are evaluated locally in this map.</div>',
            '<label for="nfhl-address">Address lookup</label>',
            '<input id="nfhl-address" type="text" placeholder="Street address or place name">',
            '<label class="nfhl-geocode-consent"><input id="nfhl-geocode-consent" type="checkbox"> <span>Address lookup sends the typed address, and possible normalized variants, to external geocoding services: OpenStreetMap Nominatim and, if needed, Esri ArcGIS World Geocoder.</span></label>',
            '<button type="button" class="secondary" id="nfhl-address-button">Search address</button>',
            '<div id="nfhl-location-result" class="nfhl-location-result"><div class="nfhl-location-note">Enter coordinates or search an address to compare a point with visible NFHL polygons.</div></div>',
            '</div>',
            '</details>'
          ].join("");
          L.DomEvent.disableClickPropagation(container);
          L.DomEvent.disableScrollPropagation(container);
          setTimeout(function() {
            const lonInput = container.querySelector("#nfhl-lon");
            const latInput = container.querySelector("#nfhl-lat");
            const addressInput = container.querySelector("#nfhl-address");
            const consentInput = container.querySelector("#nfhl-geocode-consent");
            const resultEl = container.querySelector("#nfhl-location-result");
            container.querySelector("#nfhl-coordinate-button").addEventListener("click", function() {
              const lng = toNumber(lonInput.value);
              const lat = toNumber(latInput.value);
              if (lng === null || lat === null || lng < -180 || lng > 180 || lat < -90 || lat > 90) {
                resultEl.innerHTML = '<div class="nfhl-result-title">Invalid coordinates</div><div>Enter WGS84 longitude between -180 and 180 and latitude between -90 and 90.</div>';
                return;
              }
              locatePoint(lat, lng, "Selected coordinates", resultEl);
            });
            container.querySelector("#nfhl-address-button").addEventListener("click", function() {
              const address = addressInput.value.trim();
              if (!address) {
                resultEl.innerHTML = '<div class="nfhl-result-title">Address required</div><div>Enter an address or place name first.</div>';
                return;
              }
              if (!consentInput.checked) {
                resultEl.innerHTML = '<div class="nfhl-result-title">Address lookup privacy notice</div><div>Check the consent box before geocoding. The typed address may be sent to OpenStreetMap Nominatim and, if needed, Esri ArcGIS World Geocoder.</div>';
                return;
              }
              const variants = addressQueryVariants(address);
              resultEl.innerHTML = '<div class="nfhl-result-title">Searching address...</div><div class="nfhl-location-note">Trying street-address matches first; city/ZIP fallback is marked approximate.</div>';
              geocodeAddressVariants(variants)
              .then(function(result) {
                if (!result.match) {
                  resultEl.innerHTML = [
                    '<div class="nfhl-result-title">No address match found</div>',
                    '<div>OpenStreetMap and Esri did not return a usable match. Try a simpler place string, such as city/state, ZIP code, or coordinates from another geocoder.</div>'
                  ].join("");
                  return;
                }
                const match = result.match;
                const label = match.display_name || "Address match";
                locatePoint(Number(match.lat), Number(match.lon), label, resultEl);
                if (result.precision === "approximate") {
                  const warning = document.createElement("div");
                  warning.className = "nfhl-location-warning";
                  warning.textContent = "Approximate location only: the typed street address was not resolved, so this marker may represent a city or ZIP centroid rather than the property.";
                  resultEl.appendChild(warning);
                }
                const note = document.createElement("div");
                note.className = "nfhl-location-note";
                note.textContent = (result.precision === "approximate" ? "Approximate geocode by " : "Geocoded by ") + result.provider + " with query: " + result.query;
                resultEl.appendChild(note);
              })
              .catch(function(error) {
                resultEl.innerHTML = '<div class="nfhl-result-title">Address lookup failed</div><div>' + escapeHtml(error.message) + '</div>';
              });
            });
          }, 0);
          return container;
        }
      });

      map.addControl(new LocationControl());
      }

      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", installNfhlLocationFinder);
      } else {
        setTimeout(installNfhlLocationFinder, 0);
      }
    })();
    """
    return (
        script.replace("__MAP_NAME__", map_name)
        .replace("__MINX__", f"{minx:.12f}")
        .replace("__MINY__", f"{miny:.12f}")
        .replace("__MAXX__", f"{maxx:.12f}")
        .replace("__MAXY__", f"{maxy:.12f}")
    )


def valid_value(value: object) -> bool:
    """Return False for null, placeholder, blank, and NaN FEMA attribute values."""

    if value is None:
        return False
    try:
        if value != value:  # NaN does not equal itself.
            return False
    except TypeError:
        pass
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "<null>"}:
        return False
    try:
        if float(text) == -9999:
            return False
    except ValueError:
        pass
    return True


def yes_no(value: object) -> str | None:
    """Convert FEMA T/F flags to user-facing Yes/No values."""

    text = str(value).strip().upper() if value is not None else ""
    if text == "T":
        return "Yes"
    if text == "F":
        return "No"
    return None


def format_elevation(value: object, unit: object) -> str | None:
    """Format FEMA elevation/depth values while hiding placeholders."""

    if not valid_value(value):
        return None
    unit_text = str(unit).strip() if valid_value(unit) else ""
    unit_label = {"FEET": "ft", "FOOT": "ft", "FT": "ft", "METERS": "m", "METER": "m", "M": "m"}.get(
        unit_text.upper(),
        unit_text,
    )
    try:
        value_text = f"{float(value):g}"
    except (TypeError, ValueError):
        value_text = html.escape(str(value))
    return f"{value_text} {unit_label}".strip()


def build_flood_popup_rows(props) -> list[tuple[str, str]]:
    """Build cleaned, human-readable rows for an NFHL S_FLD_HAZ_AR feature."""

    rows: list[tuple[str, str]] = []
    zone = _prop_value(props, "FLD_ZONE")
    subtype = _prop_value(props, "ZONE_SUBTY")
    unit = _prop_value(props, "LEN_UNIT")
    category = categorize_flood_hazard(zone, subtype)

    if _is_area_not_included(_normalize(zone)):
        rows.append((FIELD_ALIASES["FLD_ZONE"], "Area Not Included"))
        rows.append(("Interpretation", "No FEMA flood hazard data is shown for this area in the current NFHL/FIRM dataset."))
        if valid_value(_prop_value(props, "SOURCE_CIT")):
            rows.append((FIELD_ALIASES["SOURCE_CIT"], str(_prop_value(props, "SOURCE_CIT"))))
        return rows

    if valid_value(zone):
        rows.append((FIELD_ALIASES["FLD_ZONE"], _display_zone_value(zone)))
    rows.append(("Flood Hazard Category", category.label))
    if valid_value(subtype):
        rows.append((FIELD_ALIASES["ZONE_SUBTY"], str(subtype)))

    sfha = yes_no(_prop_value(props, "SFHA_TF"))
    if sfha:
        rows.append((FIELD_ALIASES["SFHA_TF"], sfha))

    static_bfe = format_elevation(_prop_value(props, "STATIC_BFE"), unit)
    depth = format_elevation(_prop_value(props, "DEPTH"), unit)
    if static_bfe:
        rows.append((FIELD_ALIASES["STATIC_BFE"], static_bfe))
    if depth:
        rows.append((FIELD_ALIASES["DEPTH"], depth))
    if _should_note_missing_depth_or_bfe(zone, category, static_bfe, depth):
        rows.append(("Depth/BFE", "Not provided in this NFHL feature"))

    if valid_value(_prop_value(props, "V_DATUM")):
        rows.append((FIELD_ALIASES["V_DATUM"], str(_prop_value(props, "V_DATUM"))))
    if valid_value(_prop_value(props, "SOURCE_CIT")):
        rows.append((FIELD_ALIASES["SOURCE_CIT"], str(_prop_value(props, "SOURCE_CIT"))))
    return rows


def _flood_tooltip_html(row) -> str:
    rows = build_flood_popup_rows(row)
    return _rows_html(rows, advanced_rows=None, compact=True)


def _flood_popup_html(row) -> str:
    rows = build_flood_popup_rows(row)
    advanced_rows = _advanced_rows(row, ADVANCED_FEMA_FIELDS)
    return _rows_html(rows, advanced_rows=advanced_rows, compact=False)


def _bfe_tooltip_html(row) -> str:
    return _rows_html(_bfe_rows(row), advanced_rows=None, compact=True)


def _bfe_popup_html(row) -> str:
    return _rows_html(_bfe_rows(row), advanced_rows=_advanced_rows(row, BFE_DISPLAY_FIELDS), compact=False)


def _bfe_rows(row) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    elev = format_elevation(_prop_value(row, "ELEV"), _prop_value(row, "LEN_UNIT"))
    if elev:
        rows.append((FIELD_ALIASES["ELEV"], elev))
    if valid_value(_prop_value(row, "V_DATUM")):
        rows.append((FIELD_ALIASES["V_DATUM"], str(_prop_value(row, "V_DATUM"))))
    if valid_value(_prop_value(row, "SOURCE_CIT")):
        rows.append((FIELD_ALIASES["SOURCE_CIT"], str(_prop_value(row, "SOURCE_CIT"))))
    return rows or [("BFE Lines", "No display attributes provided")]


def _rows_html(
    rows: list[tuple[str, str]],
    *,
    advanced_rows: list[tuple[str, str]] | None,
    compact: bool,
) -> str:
    row_html = "".join(
        "<tr>"
        f'<th style="text-align:left;vertical-align:top;padding:2px 8px 2px 0;color:#374151;">{html.escape(label)}</th>'
        f'<td style="text-align:left;vertical-align:top;padding:2px 0;color:#111827;">{html.escape(value)}</td>'
        "</tr>"
        for label, value in rows
    )
    advanced_html = ""
    if advanced_rows:
        advanced_row_html = "".join(
            "<tr>"
            f'<th style="text-align:left;vertical-align:top;padding:2px 8px 2px 0;color:#4b5563;">{html.escape(label)}</th>'
            f'<td style="text-align:left;vertical-align:top;padding:2px 0;color:#374151;">{html.escape(value)}</td>'
            "</tr>"
            for label, value in advanced_rows
        )
        advanced_html = f"""
        <details style="margin-top:8px;">
          <summary style="cursor:pointer;color:#1f2937;font-weight:600;">Raw FEMA attributes</summary>
          <table style="border-collapse:collapse;margin-top:4px;font-size:11px;">{advanced_row_html}</table>
        </details>
        """
    width = "300px" if compact else "380px"
    return f"""
    <div style="font-family:Arial, sans-serif;font-size:12px;line-height:1.25;max-width:{width};">
      <table style="border-collapse:collapse;">{row_html}</table>
      {advanced_html}
    </div>
    """


def _advanced_rows(row, fields: list[str]) -> list[tuple[str, str]]:
    rows = []
    for field in fields:
        if _actual_column(row.index, field) is None:
            continue
        rows.append((field, _raw_display_value(_prop_value(row, field))))
    return rows


def _raw_display_value(value: object) -> str:
    if value is None:
        return "null"
    try:
        if value != value:
            return "null"
    except TypeError:
        pass
    text = str(value).strip()
    return text if text else "null"


def _should_note_missing_depth_or_bfe(
    zone: object,
    category: HazardCategory,
    static_bfe: str | None,
    depth: str | None,
) -> bool:
    if static_bfe or depth:
        return False
    zone_text = _normalize(zone)
    return category.key in {"one_percent", "coastal_high_hazard", "regulatory_floodway"} or zone_text in {
        "A",
        "AE",
        "AH",
        "AO",
        "AR",
        "A99",
        "V",
        "VE",
    }


def _prop_value(props, name: str):
    keys = props.index if hasattr(props, "index") else props.keys()
    actual = _actual_column(keys, name)
    return props.get(actual) if actual else None


def _detailed_zone_subsets(gdf) -> list[tuple[str, object]]:
    fld_zone = _actual_column(gdf.columns, "FLD_ZONE")
    zone_subty = _actual_column(gdf.columns, "ZONE_SUBTY")
    if fld_zone is None:
        return []

    labels: list[tuple[str, object]] = []
    grouped = gdf.groupby([fld_zone, zone_subty], dropna=False) if zone_subty else gdf.groupby(fld_zone, dropna=False)
    for key, subset in grouped:
        if zone_subty:
            zone, subtype = key
        else:
            zone, subtype = key, ""
        label = _detailed_label(zone, subtype)
        labels.append((label, subset))
    return sorted(labels, key=lambda item: item[0])


def _detailed_label(zone: object, subtype: object) -> str:
    zone_text = _display_zone_value(zone)
    subtype_text = _display_subtype_value(subtype)
    return zone_text if not subtype_text else f"{zone_text} - {subtype_text}"


def _detailed_layer_name(zone: object, subtype: object) -> str:
    zone_text = _display_zone_value(zone)
    subtype_text = _display_subtype_value(subtype)
    if _is_area_not_included(_normalize(zone)) and not subtype_text:
        return "Detailed FLD_ZONE: Area Not Included / no mapped flood hazard data"
    if subtype_text:
        return f"Detailed ZONE_SUBTY: {zone_text} - {subtype_text}"
    return f"Detailed FLD_ZONE: {zone_text}"


def _display_zone_value(value: object) -> str:
    normalized = _normalize(value) if valid_value(value) else ""
    if _is_area_not_included(normalized):
        return "Area Not Included"
    if normalized == "OPEN WATER":
        return "Open Water"
    return normalized or "Missing FLD_ZONE"


def _display_subtype_value(value: object) -> str:
    return _normalize(value) if valid_value(value) else ""


def _available_fields(gdf, candidates: list[str]) -> list[str]:
    columns = {column.upper(): column for column in gdf.columns}
    return [columns[name] for name in candidates if name in columns]


def _actual_column(columns, name: str) -> str | None:
    matches = {column.upper(): column for column in columns}
    return matches.get(name.upper())


def _normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<null>"}:
        return ""
    return text.upper()


def _is_area_not_included(zone: str) -> bool:
    return zone in {"AREA NOT INCLUDED", "ANI"}


def _is_regulatory_floodway(subtype: str) -> bool:
    return any(
        phrase in subtype
        for phrase in [
            "FLOODWAY",
            "COMMUNITY ENCROACHMENT",
            "ADMINISTRATIVE FLOODWAY",
            "FLOWAGE EASEMENT",
            "NARROW FLOODWAY",
            "STATE ENCROACHMENT",
        ]
    )


def _legend_html() -> str:
    category_items = "\n".join(
        f"""
        <div class="nfhl-legend-row">
          <span class="nfhl-swatch" style="background:{html.escape(category.color)}"></span>
          <div>
            <div class="nfhl-label">{html.escape(category.label)}</div>
            <div class="nfhl-note">{html.escape(category.explanation)}</div>
          </div>
        </div>
        """
        for key in CATEGORY_ORDER
        if key != "other"
        for category in [HAZARD_CATEGORIES[key]]
    )
    return f"""
    <div style="
      position: fixed; bottom: 24px; left: 24px; z-index: 9999; background: rgba(255,255,255,.92);
      border: 1px solid #9ca3af; padding: 12px 14px; font-size: 12px; max-width: 390px;
      max-height: 70vh; overflow-y: auto; box-shadow: 0 2px 10px rgba(0,0,0,.24); line-height: 1.25;">
      <style>
        .nfhl-legend-panel > summary {{cursor: pointer; font-weight: 700; color: #111827; list-style: none;}}
        .nfhl-legend-panel > summary::-webkit-details-marker {{display: none;}}
        .nfhl-legend-panel > summary::after {{content: " \\25BE"; font-weight: 400; color: #6b7280; font-size: 11px;}}
        .nfhl-legend-panel:not([open]) > summary::after {{content: " \\25B8";}}
        .nfhl-legend-body {{margin-top: 7px;}}
        .nfhl-legend-row {{display: flex; gap: 7px; margin: 5px 0; align-items: flex-start;}}
        .nfhl-swatch {{display:inline-block; width: 15px; height: 12px; border: 1px solid rgba(17,24,39,.25); flex: 0 0 auto; margin-top: 1px;}}
        .nfhl-label {{font-weight: 600; color: #111827;}}
        .nfhl-note {{color: #4b5563; font-size: 11px;}}
        .nfhl-line {{display:inline-block; width: 20px; height: 0; border-top: 3px solid #d7191c; margin: 0 7px 3px 0;}}
        .nfhl-detail-note {{margin-top: 8px; color: #374151; font-size: 11px;}}
        .nfhl-about {{margin-top: 8px; color: #374151; font-size: 11px;}}
        .nfhl-about summary {{cursor: pointer; font-weight: 700; color: #111827;}}
        .nfhl-about div {{margin-top: 4px;}}
      </style>
      <details class="nfhl-legend-panel" open>
        <summary>Map Legend</summary>
        <div class="nfhl-legend-body">
          <div>{category_items}</div>
          <div class="nfhl-legend-row">
            <span class="nfhl-line"></span>
            <div>
              <div class="nfhl-label">BFE Lines</div>
              <div class="nfhl-note">Base Flood Elevation lines from the FEMA S_BFE layer where available.</div>
            </div>
          </div>
          <div class="nfhl-detail-note">Detailed FEMA zone/subtype layers remain available in the layer control.</div>
          <details class="nfhl-about">
            <summary>About / limitations</summary>
            <div>This is a FEMA NFHL visualization prototype, not an official FEMA flood determination. BFE units and vertical datum must be verified before analysis.</div>
          </details>
        </div>
      </details>
    </div>
    """
