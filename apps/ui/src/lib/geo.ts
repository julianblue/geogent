import type { Viewport } from "@/components/map/MapStateProvider";

export function viewportToBboxWkt(viewport: Viewport): string {
  const b = viewport.bounds;
  if (!b) {
    const half = 360 / Math.pow(2, viewport.zoom);
    return bboxToWkt(
      viewport.longitude - half,
      viewport.latitude - half / 2,
      viewport.longitude + half,
      viewport.latitude + half / 2,
    );
  }
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
