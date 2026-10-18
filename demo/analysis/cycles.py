import json, sys, numpy as np, collections, datetime as dt
from scipy.signal import find_peaks, savgol_filter
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
A=sys.argv[1]; Y=2024
V=np.load(f"{A}/ndvi_{Y}.npy"); D=[dt.date.fromisoformat(d) for d in json.load(open(f"{A}/ndvi_{Y}_dates.json"))]
doy=np.array([d.timetuple().tm_yday for d in D])
M=json.load(open(f"{A}/meta.json"))["years"][str(Y)]
P=json.load(open(f"{A}/parcels_utm.json"))[str(Y)]
E=np.load(f"{A}/parcel_means_{Y}.npy"); aoi=np.load(f"{A}/aoi_means.npy")[Y-2019]; Ec=E-aoi
grid=np.arange(15,351,5)
ncyc=np.full(len(P),-1); peaks_doy=[None]*len(P)
for i in range(len(P)):
    v=V[:,i]; ok=np.isfinite(v)
    if ok.sum()<20 or M["count"][i]<5: continue
    s=np.interp(grid,doy[ok],v[ok]); s=savgol_filter(s,7,2)
    pk,pr=find_peaks(np.r_[0,s,s[-1]],height=0.5,prominence=0.2,distance=8)  # pad start only: a cycle must decline before year end
    pk=[p for p in pk if 60<=grid[min(p-1,len(grid)-1)]<=300 and p-1<len(grid)-3]
    ncyc[i]=len(pk); peaks_doy[i]=[int(grid[p-1]) for p in pk]
ok=ncyc>=0
hc=np.array(M["hcat"])
print("parcels with usable series:",ok.sum(),"cycle counts:",collections.Counter(ncyc[ok].tolist()))
two=ncyc>=2
# characterise second cycles: timing of first/second peak
def season(d): return "spring(<Jun15)" if d<166 else ("summer(Jun15-Aug15)" if d<227 else "late(Aug15-Oct)")
pat=collections.Counter(tuple(season(d) for d in peaks_doy[i][:2]) for i in np.flatnonzero(ok&two))
print("two-cycle timing patterns:",pat.most_common(5))
print("\nshare with >=2 cycles by declared crop (n>=25):")
for c,n in collections.Counter(hc[ok]).most_common():
    if n<25: break
    m=ok&(hc==c); print(f"  {two[m].mean():.2f}  n={n:4d}  {c}")
# embedding probe, spatially blocked CV (2 km blocks)
from shapely import wkt
cx=np.array([wkt.loads(p["wkt"]).centroid.x for p in P]); cy=np.array([wkt.loads(p["wkt"]).centroid.y for p in P])
blk=(cx//2000).astype(int)*100+(cy//2000).astype(int)
idx=np.flatnonzero(ok); y=two[idx]
clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=0.5))
pe=cross_val_predict(clf,Ec[idx],y,cv=GroupKFold(5),groups=blk[idx],method="predict_proba")[:,1]
# baseline: declared crop only (one-hot), same CV
cl=sorted(set(hc[idx])); OH=np.array([[h==c for c in cl] for h in hc[idx]],dtype=float)
pb=cross_val_predict(LogisticRegression(max_iter=3000),OH,y,cv=GroupKFold(5),groups=blk[idx],method="predict_proba")[:,1]
pc=cross_val_predict(clf,np.c_[Ec[idx],OH],y,cv=GroupKFold(5),groups=blk[idx],method="predict_proba")[:,1]
print(f"\npredict >=2 cycles (n={len(idx)}, prevalence {y.mean():.2f}), 2-km spatial block CV:")
print(f"  declared crop only : AUC {roc_auc_score(y,pb):.3f}")
print(f"  embedding only     : AUC {roc_auc_score(y,pe):.3f}  bal.acc {balanced_accuracy_score(y,pe>0.5):.3f}")
print(f"  embedding + crop   : AUC {roc_auc_score(y,pc):.3f}")
print("within-crop AUC of embedding score (crops with both classes, >=10 each):")
for c in cl:
    m=hc[idx]==c
    if m.sum()>=30 and 10<=y[m].sum()<=m.sum()-10: print(f"  {roc_auc_score(y[m],pe[m]):.3f}  n={m.sum()} two-cycle={y[m].mean():.2f}  {c}")
json.dump({"ncyc":ncyc.tolist(),"peaks":peaks_doy},open(f"{A}/cycles_strict_{Y}.json","w"))
