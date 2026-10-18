import json, sys, time
import numpy as np
from shapely import wkt
from rasterio.features import rasterize
from geogent_backend.geo.tessera import IcechunkTesseraReader
S=sys.argv[1]
BB=(16.54,48.22,16.66,48.29)
P=json.load(open(f"{S}/ana/parcels_utm.json"))
r=IcechunkTesseraReader(year_threads=1)
units=[(f["id"],wkt.loads(f["wkt"]).buffer(-10)) for f in P["2024"]]
res={"years":{}, "units_ids":[u[0] for u in units]}
unit_means=[]; aoi_means=[]; pix_samples=[]
rng=np.random.default_rng(0)
for y in range(2019,2026):
    t=time.time(); w=r.read_window(BB,[y],128); emb=w.emb[0]  # band,y,x
    H,W=emb.shape[1:]
    valid=np.isfinite(emb).all(0)
    X=emb.reshape(128,-1).T
    aoi_means.append(np.nanmean(X[valid.ravel()],0))
    def zone_means(geoms):
        lab=rasterize([(g,i+1) for i,g in enumerate(geoms) if not g.is_empty],out_shape=(H,W),transform=w.transform,fill=0,dtype="int32").ravel()
        m=(lab>0)&valid.ravel(); L=lab[m]-1; n=len(geoms)
        cnt=np.bincount(L,minlength=n); s=np.zeros((n,128)); np.add.at(s,L,X[m]); s2=np.zeros(n); 
        mean=s/np.maximum(cnt,1)[:,None]
        # within-parcel dispersion: mean distance of pixels to parcel mean
        d=np.linalg.norm(X[m]-mean[L],axis=1); np.add.at(s2,L,d)
        return mean,cnt,s2/np.maximum(cnt,1),lab
    feats=P[str(y)]
    geoms=[wkt.loads(f["wkt"]).buffer(-10) for f in feats]
    m,c,disp,lab=zone_means(geoms)
    res["years"][y]={"ids":[f["id"] for f in feats],"hcat":[f["hcat"] for f in feats],"crop":[f["crop"] for f in feats],"ha":[f["ha"] for f in feats],"count":c.tolist(),"disp":disp.tolist()}
    np.save(f"{S}/ana/parcel_means_{y}.npy",m.astype(np.float32))
    um,uc,_,_=zone_means([g for _,g in units]); unit_means.append(um); res.setdefault("unit_counts",{})[y]=uc.tolist()
    # pixel sample with labels for pixel-level probe
    idx=np.flatnonzero((lab>0)&valid.ravel()); idx=rng.choice(idx,min(20000,len(idx)),replace=False)
    np.save(f"{S}/ana/pix_{y}.npy",np.column_stack([X[idx],lab[idx]-1]).astype(np.float32))
    print(y,"window",H,W,"valid",round(valid.mean(),3),"read",round(time.time()-t,1),"s",flush=True)
np.save(f"{S}/ana/unit_means.npy",np.stack(unit_means).astype(np.float32))
np.save(f"{S}/ana/aoi_means.npy",np.stack(aoi_means).astype(np.float32))
json.dump(res,open(f"{S}/ana/meta.json","w"))
