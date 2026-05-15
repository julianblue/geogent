// Earth Search v1 (Element 84) — open STAC API over the Sentinel-2 L2A AWS
// Open Data archive. Emits permissive CORS and supports HTTP range reads,
// so the browser can pull individual band COGs straight from S3 with no
// server in between.
const EARTH_SEARCH_ROOT = "https://earth-search.aws.element84.com/v1";
const EARTH_SEARCH = `${EARTH_SEARCH_ROOT}/search`;
const SENTINEL2_COLLECTION = "sentinel-2-l2a";

export type Bbox = [number, number, number, number]; // [west, south, east, north]

/**
 * Subset of Sentinel-2 L2A band asset URLs that we expose to the renderer.
 * Earth Search names assets by spectral band so the keys here are stable
 * across scenes (`red`, `green`, `blue` are the 10 m visible bands).
 */
export type Sentinel2BandHrefs = {
  red: string; // B04 — 10 m
  green: string; // B03 — 10 m
  blue: string; // B02 — 10 m
  nir: string; // B08 — 10 m
  swir16: string; // B11 — 20 m
  swir22: string; // B12 — 20 m
};

export type Sentinel2Item = {
  id: string;
  datetime: string;
  cloudCover: number;
  bands: Sentinel2BandHrefs;
  bbox: Bbox;
};

type StacAsset = { href: string; type?: string };
type StacFeature = {
  id: string;
  bbox: Bbox;
  properties: {
    datetime: string;
    "eo:cloud_cover"?: number;
  };
  assets: Partial<Record<keyof Sentinel2BandHrefs | "visual", StacAsset>>;
};

type StacResponse = { features?: StacFeature[] };

const REQUIRED_BAND_KEYS: (keyof Sentinel2BandHrefs)[] = [
  "red",
  "green",
  "blue",
  "nir",
  "swir16",
  "swir22",
];

// The COG variants of each band on Earth Search v1 are served as Cloud-Optimized
// GeoTIFFs. JP2000 (the older `*-jp2` siblings) is NOT supported by
// @developmentseed/geotiff and would fail at decode — we reject it explicitly
// here so the failure mode is a clear error rather than a silent black tile.
const COG_MIME_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized";

function featureToItem(feature: StacFeature): Sentinel2Item {
  const bands = {} as Sentinel2BandHrefs;
  for (const key of REQUIRED_BAND_KEYS) {
    const asset = feature.assets[key];
    if (!asset?.href) {
      throw new Error(`Earth Search item ${feature.id} is missing band ${key}`);
    }
    // Guard against the JP2 sibling assets sneaking in — they're served on the
    // same collection under `${band}-jp2` keys, and the GeoTIFF reader can't
    // decode them.
    if (asset.type && asset.type !== COG_MIME_TYPE) {
      throw new Error(
        `Earth Search item ${feature.id} band ${key} is not a COG (got ${asset.type})`,
      );
    }
    bands[key] = asset.href;
  }
  return {
    id: feature.id,
    datetime: feature.properties.datetime,
    cloudCover: feature.properties["eo:cloud_cover"] ?? 0,
    bands,
    bbox: feature.bbox,
  };
}

/**
 * Find the most recent low-cloud Sentinel-2 L2A scene intersecting `bbox`.
 * Returns null when no scene matches the cloud filter or when the matched
 * scene is missing the bands we need to render composites.
 */
export async function findLatestSentinel2(bbox: Bbox): Promise<Sentinel2Item | null> {
  const res = await fetch(EARTH_SEARCH, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      collections: [SENTINEL2_COLLECTION],
      bbox,
      query: { "eo:cloud_cover": { lt: 20 } },
      sortby: [{ field: "properties.datetime", direction: "desc" }],
      limit: 1,
    }),
  });
  if (!res.ok) throw new Error(`Earth Search responded ${res.status}`);

  const data = (await res.json()) as StacResponse;
  const feature = data.features?.[0];
  if (!feature) return null;
  return featureToItem(feature);
}

/**
 * Resolve a Sentinel-2 L2A scene by its STAC item id. Used by the agent's
 * `show_sentinel2_scene` tool when it already discovered an item via
 * stac_search and wants to render it directly without re-querying by bbox.
 */
export async function fetchSentinel2ById(itemId: string): Promise<Sentinel2Item | null> {
  const url = `${EARTH_SEARCH_ROOT}/collections/${SENTINEL2_COLLECTION}/items/${encodeURIComponent(itemId)}`;
  const res = await fetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Earth Search responded ${res.status}`);
  const feature = (await res.json()) as StacFeature;
  return featureToItem(feature);
}
