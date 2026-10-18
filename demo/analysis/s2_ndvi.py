import json, sys, numpy as np, time
from pystac_client import Client
import rasterio
from rasterio.windows import from_bounds
from rasterio.features import rasterize
from shapely import wkt
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
A=sys.argv[1]; YEAR=int(sys.argv[2])
BB=(16.54,48.22,16.66,48.29)
cat=Client.open("https://earth-search.aws.element84.com/v1")
items=list(cat.search(collections=["sentinel-2-l2a"],bbox=BB,datetime=f"{YEAR}-01-01/{YEAR}-12-31",query={"eo:cloud_cover":{"lt":40}}).items())
# one item per date (prefer lowest cloud), tile 33UXP covers the window
byday={}
for it in items:
    d=it.datetime.date()
    if d not in byday or it.properties["eo:cloud_cover"]<byday[d].properties["eo:cloud_cover"]: byday[d]=it
days=sorted(byday); print(len(items),"items",len(days),"dates",flush=True)
t=Transformer.from_crs(4326,32633,always_xy=True)
xs,ys=zip(*[t.transform(x,y) for x in BB[0::2] for y in BB[1::2]]); ub=(min(xs),min(ys),max(xs),max(ys))
P=json.load(open(f"{A}/parcels_utm.json"))[str(YEAR)]
geoms=[wkt.loads(f["wkt"]).buffer(-10) for f in P]
def read(it):
    out={}
    for b in ("red","nir","scl"):
        with rasterio.open(it.assets[b].href) as src:
            if src.crs.to_epsg()!=32633: return None
            win=from_bounds(*ub,src.transform)
            shp=out["red"][0].shape if b!="red" else None
            arr=src.read(1,window=win,boundless=True,fill_value=0,out_shape=shp)
            out[b]=(arr,src.window_transform(win))
    return out
lab=None; series=[]
with ThreadPoolExecutor(6) as ex:
    for d,res in zip(days,ex.map(lambda d:read(byday[d]),days)):
        if res is None: continue
        red,tr=res["red"]; nir,_=res["nir"]; scl,_=res["scl"]
        if lab is None:
            lab=rasterize([(g,i+1) for i,g in enumerate(geoms) if not g.is_empty],out_shape=red.shape,transform=tr,fill=0,dtype="int32")
        clear=np.isin(scl,[4,5])&(red>0)
        ndvi=(nir.astype("f4")-red)/(nir.astype("f4")+red+1e-6)
        m=(lab>0)&clear; L=lab[m]-1; n=len(geoms)
        cnt=np.bincount(L,minlength=n); tot=np.bincount((lab>0).ravel()*lab.ravel(),minlength=n+1)[1:]
        s=np.bincount(L,weights=ndvi[m],minlength=n)
        v=np.where(cnt>=0.8*np.maximum(tot,1),s/np.maximum(cnt,1),np.nan)
        series.append(v); print(d,"clear parcels",int(np.isfinite(v).sum()),flush=True)
np.save(f"{A}/ndvi_{YEAR}.npy",np.array(series,dtype="f4")); json.dump([str(d) for d in days],open(f"{A}/ndvi_{YEAR}_dates.json","w"))
