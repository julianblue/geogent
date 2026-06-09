/**
 * Browser-side client for agricultural fields/parcels (#29), used by the field
 * selection UX (#24). Hits the Next.js proxy under /api/proxy/fields, which
 * forwards to the auth-gated backend with the user's token.
 */

/** Mirrors the backend `FieldRead` schema (schemas/field.py). */
export type Field = {
  id: number;
  name: string;
  crop: string | null;
  season: string | null;
  geometry: GeoJSON.Geometry;
  created_at: string;
};

export type Bounds = { west: number; south: number; east: number; north: number };

/** Fetch fields whose geometry intersects the given lon/lat bounding box. */
export async function listFieldsInBbox(bounds: Bounds): Promise<Field[]> {
  const params = new URLSearchParams({
    min_lon: String(bounds.west),
    min_lat: String(bounds.south),
    max_lon: String(bounds.east),
    max_lat: String(bounds.north),
  });
  const res = await fetch(`/api/proxy/fields/in-bbox?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fields/in-bbox failed: ${res.status}`);
  return (await res.json()) as Field[];
}
