import type { Viewport } from "@/components/map/MapStateProvider";

/**
 * Convert the current map viewport's bbox to a WKT polygon (SRID 4326).
 * Returns `null` if bounds aren't available yet (map hasn't fired its first
 * `onLoad`); callers should refuse to run viewport-scoped queries in that
 * case rather than guess at a bbox.
 */
export function viewportToBboxWkt(viewport: Viewport): string | null {
  const b = viewport.bounds;
  if (!b) return null;
  return bboxToWkt(b.west, b.south, b.east, b.north);
}

export function bboxToWkt(west: number, south: number, east: number, north: number): string {
  return `POLYGON((${west} ${south},${east} ${south},${east} ${north},${west} ${north},${west} ${south}))`;
}

const WKT_NUM = "-?\\d+(?:\\.\\d+)?";
const POLYGON_RE = new RegExp(`POLYGON\\s*\\(\\(([^)]+)\\)\\)`, "i");

export function wktPolygonToCoordinates(wkt: string): number[][] | null {
  const match = wkt.match(POLYGON_RE);
  if (!match) return null;
  const coords: number[][] = [];
  for (const pair of match[1].split(",")) {
    const m = pair.trim().match(new RegExp(`^(${WKT_NUM})\\s+(${WKT_NUM})$`));
    if (!m) return null;
    coords.push([parseFloat(m[1]), parseFloat(m[2])]);
  }
  return coords;
}

export function wktPolygonToGeoJSON(wkt: string): GeoJSON.Polygon | null {
  const coords = wktPolygonToCoordinates(wkt);
  if (!coords) return null;
  return { type: "Polygon", coordinates: [coords] };
}

/**
 * Representative [lon, lat] point for a GeoJSON geometry — the mean of all its
 * vertex coordinates. Good enough to drop a feature/field into an aggregation
 * bin (#57); not a true area centroid. Returns `null` for empty/unsupported
 * geometries (e.g. GeometryCollection).
 */
export function geometryCentroid(geometry: GeoJSON.Geometry): [number, number] | null {
  let sumLon = 0;
  let sumLat = 0;
  let count = 0;
  const visit = (coords: unknown): void => {
    if (
      Array.isArray(coords) &&
      coords.length >= 2 &&
      typeof coords[0] === "number" &&
      typeof coords[1] === "number"
    ) {
      sumLon += coords[0];
      sumLat += coords[1];
      count += 1;
      return;
    }
    if (Array.isArray(coords)) for (const c of coords) visit(c);
  };
  if ("coordinates" in geometry) visit(geometry.coordinates);
  if (count === 0) return null;
  return [sumLon / count, sumLat / count];
}
