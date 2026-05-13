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
