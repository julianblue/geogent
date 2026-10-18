"""2024 post-harvest winter green: cover/catch crop vs next season's autumn-sown crop (labelled by 2025 declaration)."""
import json, sys, numpy as np, collections, datetime as dt
from scipy.signal import savgol_filter
from shapely import wkt, STRtree
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
A=sys.argv[1]; Y=2024
V=np.load(f"{A}/ndvi_{Y}.npy"); doy=np.array([dt.date.fromisoformat(d).timetuple().tm_yday for d in json.load(open(f"{A}/ndvi_{Y}_dates.json"))])
M=json.load(open(f"{A}/meta.json"))["years"]; P=json.load(open(f"{A}/parcels_utm.json"))
E=np.load(f"{A}/parcel_means_{Y}.npy")-np.load(f"{A}/aoi_means.npy")[Y-2019]
grid=np.arange(15,366,5)
g24=[wkt.loads(p["wkt"]) for p in P[str(Y)]]; g25=[wkt.loads(p["wkt"]) for p in P[str(Y+1)]]; tree=STRtree(g25)
def nxt(i):
    best=(0,None)
    for j in tree.query(g24[i]):
        ov=g25[j].intersection(g24[i]).area/g24[i].area
        if ov>best[0]: best=(ov,P[str(Y+1)][j]["hcat"])
    return best[1] if best[0]>=0.8 else None
WINTER=lambda h: h is not None and ("WINTER" in h)
PEREN=("FALLOW","ALFALFA","FORAGE","MEADOW","TURF","GREENHOUSE","CHERR","PLUM","APRICOT","SHRUB","STRAWBERR","ASPARAGUS")
rec=[]
for i in range(len(P[str(Y)])):
    v=V[:,i]; ok=np.isfinite(v); h=M[str(Y)]["hcat"][i]
    if ok.sum()<20 or M[str(Y)]["count"][i]<5 or any(k in h for k in PEREN): continue
    s=savgol_filter(np.interp(grid,doy[ok],v[ok]),7,2)
    main=np.argmax(np.where(grid<=250,s,-1))           # main-season peak (by early Sep)
    if s[main]<0.5: continue
    after=s[main:]; tr=main+int(np.argmin(np.where(grid[main:]<=320,after,9)))
    harvested=s[tr]<0.35
    late=s[grid>=320].mean()                          # mid-Nov..Dec
    if not harvested: continue
    rise=next((int(grid[k]) for k in range(tr,len(grid)) if s[k]>=0.4),None)
    n=nxt(i)
    if late<0.3: cat="bare over winter"
    elif late>=0.45: cat="winter green"
    else: continue
    rec.append(dict(i=i,crop=h,next=n,cat=cat,late=float(late),rise=rise,harvest_doy=int(grid[tr])))
print("harvested arable parcels with clear status:",len(rec), collections.Counter(r["cat"] for r in rec))
wg=[r for r in rec if r["cat"]=="winter green" and r["next"] is not None]
for r in wg: r["kind"]="autumn-sown next crop" if WINTER(r["next"]) else ("cover/catch crop" if not any(k in r["next"] for k in PEREN) else "→ perennial/fallow")
print("winter-green split by 2025 declaration:",collections.Counter(r["kind"] for r in wg))
for k in ["autumn-sown next crop","cover/catch crop"]:
    rs=[r["rise"] for r in wg if r["kind"]==k and r["rise"]]
    q=[str(dt.date(Y,1,1)+dt.timedelta(int(x)-1)) for x in np.quantile(rs,[.25,.5,.75])]
    print(f"  {k}: autumn green-up date p25/p50/p75 = {q}")
print("\npractice by 2024 crop (n>=25):  bare | cover/catch | next winter crop sown")
byc=collections.defaultdict(list)
for r in rec: byc[r["crop"]].append("bare" if r["cat"]=="bare over winter" else r.get("kind","?"))
for c,v in sorted(byc.items(),key=lambda kv:-len(kv[1])):
    if len(v)<25: continue
    n=len(v); f=lambda k: sum(x==k for x in v)/n
    print(f"  {f('bare'):.2f} | {f('cover/catch crop'):.2f} | {f('autumn-sown next crop'):.2f}   n={n} {c}")
# embedding probes
cx=np.array([g.centroid.x for g in g24]); cy=np.array([g.centroid.y for g in g24]); blk=(cx//2000).astype(int)*100+(cy//2000).astype(int)
clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=0.5))
def probe(name,rows,pos):
    idx=np.array([r["i"] for r in rows]); y=np.array([pos(r) for r in rows])
    pe=cross_val_predict(clf,E[idx],y,cv=GroupKFold(5),groups=blk[idx],method="predict_proba")[:,1]
    cl=sorted(set(r["crop"] for r in rows)); OH=np.array([[r["crop"]==c for c in cl] for r in rows],float)
    pb=cross_val_predict(LogisticRegression(max_iter=3000),OH,y,cv=GroupKFold(5),groups=blk[idx],method="predict_proba")[:,1]
    print(f"{name}: n={len(y)} prevalence={y.mean():.2f}  AUC crop-label={roc_auc_score(y,pb):.3f}  AUC embedding={roc_auc_score(y,pe):.3f}  bal.acc={balanced_accuracy_score(y,pe>0.5):.3f}")
    return idx,y,pe
print()
probe("winter green vs bare (after harvest)",rec,lambda r:r["cat"]=="winter green")
two=[r for r in wg if r["kind"] in("autumn-sown next crop","cover/catch crop")]
idx,y,pe=probe("cover/catch crop vs autumn-sown next crop",two,lambda r:r["kind"]=="cover/catch crop")
rs=np.array([r["rise"] or 366 for r in two]); print(f"   (NDVI green-up date alone, AUC = {roc_auc_score(y,-rs):.3f})")
json.dump(rec,open(f"{A}/winter_{Y}.json","w"))
