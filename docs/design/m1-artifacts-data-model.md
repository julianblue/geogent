# M1 design: the `artifacts` registry & service interface

> Implements the ADR 0002 "heavy datasets are content-addressed server-side
> artifacts" rule for milestone M1. Read alongside
> [`../adr/0002-satellite-data-cubes-management-zones.md`](../adr/0002-satellite-data-cubes-management-zones.md)
> and the de-risking spike `apps/backend/spikes/cube_zones/DECISION.md`.

## What this is

One table + one service that generalize the two patterns already in
`models/raster_job.py`:

- `RasterJob` — a **lifecycle** (`status` / `params` / `result` / `error`).
- `RasterStatCache` — an **immutable, hash-keyed** result.

An **artifact** is both at once, plus a pointer to a heavy payload that lives in
object storage, not the DB:

```
content-addressed (recipe_hash)  +  lifecycle (status)  +  payload in object store
        = reuse for free                 = async builds        = agent never sees pixels
```

Every cube, temporal-feature layer, terrain layer, and zone map is an artifact.
The agent receives a **handle + compact summary**; the UI receives **render
URLs**; neither ever receives the cube.

## Data model

`models/artifact.py`:

```python
class Artifact(Base):
    """A materialized heavy dataset (cube / feature layer / terrain / zone map).

    Content-addressed by ``recipe_hash`` (identical recipe -> reuse), with a
    job lifecycle in ``status`` and the heavy payload in object storage,
    referenced by ``assets``. Only ``summary`` is ever returned to the agent.
    """

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4 hex; the handle
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # ArtifactKind
    recipe_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # dedup key
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # JobStatus
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)  # principle #5

    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # provenance/repro
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # -> agent
    assets: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)  # -> UI
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Content-addressing: one row per (owner, recipe). Scoped by owner so one
        # user's cache can't be probed/served to another (fail-closed, #50).
        UniqueConstraint("owner", "recipe_hash", name="uq_artifacts_owner_recipe"),
        Index("ix_artifacts_status", "status"),
    )
```

Key choices, each tracing to an existing pattern:

- **`id` (handle) vs `recipe_hash` (dedup key) are distinct.** `id` is the
  opaque handle the agent passes between tools and the UI persists in the thread
  snapshot (#20). `recipe_hash` is the cache key. Same split as a primary key vs
  `RasterStatCache.cache_key`, but separated so a stable handle survives even if
  hashing changes.
- **`assets` point to object storage, never inline.** This is the one hard
  departure from `RasterJob.result` (which inlines JSONB). Cubes/COGs are
  MB–GB; they cannot sit in Postgres and must not reach the model. Each asset:
  `{"role": "stability", "key": "<id>/stability.tif", "uri": "s3://…",
"media_type": "image/tiff; application=geo", "bands": ["productivity","cv"]}`.
- **`summary` is the only thing the agent reads back** — compact, model-friendly
  facts (shape, band stats, scenes used). See per-kind summaries below.
- **`recipe` is the full normalized request** — intrinsic provenance ("47
  scenes, 2021–24, NDVI, SCL-masked, reprojected to EPSG:32611@10m, k=4").

## Content-addressing: the recipe hash

The hash must be **canonical** so logically-identical requests collide, and
**versioned** so an algorithm change busts the cache.

```python
def recipe_hash(recipe: ArtifactRecipe) -> str:
    # model_dump with sorted keys; geometry normalized to WKB hex (vertex-order
    # and float-repr stable); dates to ISO; includes recipe.recipe_version.
    canonical = json.dumps(recipe.canonical_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
```

Mirrors `RasterService._cache_key` (WKB hex + `|`-join + sha256), generalized to
a whole recipe. Each recipe carries `recipe_version: int` — bumping it on a
math/algorithm change invalidates every dependent hash without a migration.

**Lineage / DAG.** Derived recipes embed the parent **artifact id** (and thus
its recipe transitively), so a `zone_map` recipe references its
`temporal_features` and `terrain` artifact ids. Re-deriving the cube produces a
new id → new child hashes → zones rebuild. Provenance and cache-invalidation fall
out of the same structure.

## Recipes (Pydantic discriminated union)

`schemas/artifact.py` — one recipe per `ArtifactKind`, discriminated on `kind`:

```python
class ArtifactKind(str, Enum):
    cube = "cube"
    temporal_features = "temporal_features"
    terrain = "terrain"
    zone_map = "zone_map"

class TargetGrid(BaseModel):           # the canonical grid the spike proved we need in M1
    epsg: int
    resolution_m: float = 10.0
    bounds: tuple[float, float, float, float]   # in the target CRS

class CubeRecipe(BaseModel):
    kind: Literal[ArtifactKind.cube] = ArtifactKind.cube
    recipe_version: int = 1
    field_id: int | None = None
    geometry_wkt: str | None = None              # field_id XOR geometry
    seasons: list[DateRange]                      # one or more season windows
    indices: list[IndexName] = [IndexName.ndvi]
    max_cloud_cover: float = Field(20, ge=0, le=100)
    scl_mask: bool = True                         # per-pixel cloud masking (M1 gap #2)
    target_grid: TargetGrid | None = None         # if None, derived from field + resolution

class TemporalFeaturesRecipe(BaseModel):
    kind: Literal[ArtifactKind.temporal_features] = ArtifactKind.temporal_features
    recipe_version: int = 1
    cube_id: str                                  # parent artifact handle
    features: list[TemporalFeature] = [           # productivity, stability, (phenology = M4)
        TemporalFeature.productivity, TemporalFeature.stability,
    ]

class ZoneMapRecipe(BaseModel):
    kind: Literal[ArtifactKind.zone_map] = ArtifactKind.zone_map
    recipe_version: int = 1
    feature_layer_ids: list[str]                  # temporal_features + terrain handles
    n_zones: int | Literal["auto"] = "auto"
    algorithm: Literal["kmeans", "fuzzy_cmeans"] = "kmeans"
    smoothing: SmoothingConfig = SmoothingConfig()

ArtifactRecipe = Annotated[
    CubeRecipe | TemporalFeaturesRecipe | TerrainRecipe | ZoneMapRecipe,
    Field(discriminator="kind"),
]
```

### Per-kind `summary` (what the agent reasons over)

Compact, no pixels — sized for the context window:

- **cube:** `{n_scenes_found, n_scenes_used, n_skipped_reproject, time_span,
grid:{epsg,resolution_m,width,height}, indices, valid_obs:{min,median,max}}`
  — note `n_skipped_reproject` surfaces the spike's grid-mismatch signal as a
  first-class field.
- **temporal_features:** per feature `{mean, min, max, std, within_field_spread}`
  (the within-field spread is the "are there zones worth drawing?" signal).
- **zone_map:** `{n_zones, cluster_validity:{metric, score}, zones:[{zone,
area_ha, pct, mean_productivity, mean_stability}]}` — directly feeds
  `attribute_zones` and the `management-zones` widget.

## Artifact storage

A thin provider behind an interface, mirroring how `geo/` wraps external
providers (typed errors, settings-driven):

```python
# storage/artifact_store.py
class ArtifactStore(Protocol):
    async def put(self, artifact_id: str, key: str, data: bytes) -> str:  # -> uri
    async def get(self, artifact_id: str, key: str) -> bytes:
```

**Shipped in M1 — local filesystem.** `LocalArtifactStore` writes assets under
`<artifact_storage_dir>/<artifact_id>/<key>`; the COG is served back through an
**auth-gated backend route** (`GET /analytics/artifacts/{id}/assets/{key}`,
owner-checked + key-validated against the artifact's declared `assets`) and a
**same-origin UI proxy** that deck.gl-geotiff fetches. No object-store
dependency, no MinIO, no presigning — keeps v1 dependency-free.

**Deferred (future) — object storage.** An `S3ArtifactStore` (MinIO dev / S3
prod) implementing the same protocol, with **presigned GET URLs** minted after
the owner check so the bucket is never public, and `ARTIFACT_BUCKET` /
`S3_ENDPOINT_URL` settings + MinIO in the compose stack. The service is
unchanged when this lands — only the store implementation and the URL the asset
route hands back differ (ADR 0002 D3).

## Service interface

`services/artifact_service.py` — same shape as `RasterService`, with the
get-or-create dedup up front:

```python
class ArtifactService:
    def __init__(self, session, store: ArtifactStore, owner: str | None) -> None: ...

    async def get_or_create(
        self, recipe: ArtifactRecipe, background_tasks: BackgroundTasks
    ) -> Artifact:
        """Return the existing artifact for this (owner, recipe_hash), else create
        a pending row and dispatch the build. Idempotent under the unique
        constraint (INSERT ... ON CONFLICT DO NOTHING, then re-read), exactly like
        RasterStatCacheRepository.put handles concurrent writers."""
        h = recipe_hash(recipe)
        existing = await self._repo.get_by_recipe(self._owner, h)
        if existing is not None:
            return existing                          # cache hit: any status
        artifact_id = uuid4().hex
        created = await self._repo.create_or_get(artifact_id, recipe, h, self._owner)
        if created.id == artifact_id:                # we won the race -> build it
            background_tasks.add_task(self._build, artifact_id, recipe)
        return created

    async def get(self, artifact_id: str) -> Artifact | None:
        """Owner-checked fetch; the route mints presigned URLs from .assets."""

    async def _build(self, artifact_id: str, recipe: ArtifactRecipe) -> None:
        # Own session (outlives the request) — identical to _run_time_series.
        async with SessionLocal() as session:
            repo = ArtifactRepository(session)
            try:
                await repo.set_status(artifact_id, JobStatus.running.value)
                summary, assets = await self._dispatch(recipe)     # -> geo/cube|terrain|zones
                await repo.set_result(artifact_id, summary, assets)
            except (CubeBuildError, ZoneError) as exc:
                await repo.set_error(artifact_id, str(exc))        # safe, typed message
            except Exception:
                logger.exception("Artifact build %s failed", artifact_id)
                await repo.set_error(artifact_id, "Artifact build failed.")  # no leak
```

`_dispatch` routes by `kind` to the new `geo/` modules (`geo/cube.py`,
`geo/terrain.py`, `geo/zones.py`); the blocking xarray/GDAL work runs under
`anyio.to_thread.run_sync` as `raster.zonal_stats` does today, and the COG bytes
are written via `store.put` before the row flips to `succeeded`.

**Repository** (`repositories/artifact_repo.py`) mirrors
`RasterJobRepository` + `RasterStatCacheRepository`: `create_or_get` (ON
CONFLICT on `(owner, recipe_hash)`), `get`, `get_by_recipe`, `set_status`,
`set_result`, `set_error`.

## API routes

Auth-gated router (mirror `routes/routing.py`); `owner` comes from
`CurrentUser`:

```
POST /api/v1/analytics/cubes              -> 202 {artifact_id, status}
POST /api/v1/analytics/temporal-features  -> 202 {artifact_id, status}
POST /api/v1/analytics/zones              -> 202 {artifact_id, status}
GET  /api/v1/analytics/artifacts/{id}     -> {id, kind, status, summary,
                                              assets:[{role, url}],   # presigned, succeeded only
                                              provenance, error}
```

`POST` is idempotent (returns the existing handle on a recipe hit, possibly
already `succeeded`). Provider/build failure → **502**; unconfigured object
store → **503** (the routing.py convention).

## Agent tools

Thin, mirroring `seasonal_index_time_series_for_field` (POST then poll `GET`
until terminal; cadence/timeout are **module constants**, not args, per the
agent invariant):

- `build_cube`, `temporal_features`, `terrain_derive` (primitives)
- `delineate_management_zones` (recipe — runs the chain server-side)

Each returns **`{artifact_id, kind, status, summary}`** to the model — never
`assets`. Rendering is a separate **frontend-action** tool,
`add_zone_layer(artifact_id)` / index-layer equivalent, which the browser
resolves to assets via `GET /artifacts/{id}` and paints — preserving the
UI-tools-vs-data-tools invariant (UI tool returns an ack; the agent answers from
the `summary`).

## Migration & tests

- **Alembic:** one revision adding `artifacts` (+ the unique constraint and
  status index). Keep it runnable under the CI migrations smoke job.
- **Tests** (no live network/DB, per backend conventions):
  - `recipe_hash` determinism — same recipe (incl. reordered geometry vertices /
    JSON keys) → same hash; different `recipe_version` → different hash.
  - Route behaviour with `ArtifactService` monkeypatched; an **auth-boundary**
    test (pop `get_current_user` → 403/401).
  - `ArtifactStore` faked in-memory; assert `_build` writes assets then flips to
    `succeeded`, and that `get_or_create` is idempotent on a recipe hit.

## Open decisions (need owner input)

1. **Owner propagation.** Artifacts should be owned by the _end user_, but the
   agent calls the backend with a **service-user JWT** today. Until the
   end-user identity is propagated from the thread `owner` (relates to #50),
   artifacts would be owned by the service user — weakening per-user cache
   isolation. Options: (a) ship M1 service-user-owned and tighten later; (b)
   thread the end-user id through the agent→backend call now. **Recommend (a)**
   for M1, file the propagation as a follow-up.
2. **Lifecycle / GC.** Artifacts are immutable and cached forever (like
   `RasterStatCache`), but COGs cost storage. **Recommend** keep-forever for M1
   - an `last_accessed` column now (cheap) so an LRU sweeper is a later,
     non-breaking addition.
3. **Does `artifacts` subsume `raster_jobs`?** It can, for _new_ heavy outputs.
   **Recommend** leaving the existing time-series path on `raster_jobs`
   untouched for M1 and only migrating it if the scene-manifest work (M0) makes
   it natural.
