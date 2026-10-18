"""Geographic transfer: detectors trained on Marchfeld (ana/), applied unchanged to Upper Austria (ana_ooe/)."""
import json, sys, collections, numpy as np, datetime as dt
from scipy.signal import savgol_filter, find_peaks
from shapely import wkt, STRtree
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, balanced_accuracy_score, precision_score, recall_score
SRC, TGT = sys.argv[1], sys.argv[2]; YEARS=list(range(2019,2026))
GROUP={"WINTER SOFT WHEAT":"winter cereal","HARD WINTER WHEAT (DURUM)":"winter cereal","WINTER BARLEY":"winter cereal","WINTER RYE":"winter cereal","WINTER TRITICALE":"winter cereal","WINTER SPELT (SPELT)":"winter cereal",
"SUMMER BARLEY":"spring cereal","SUMMER HARD WHEAT (DURUM)":"spring cereal","MILLET":"spring cereal","SUMMER OATS":"spring cereal","SUMMER WHEAT":"spring cereal",
"GRAIN CORN":"maize","SEED CORN PROPAGATION":"maize","SUGAR CORN":"maize","SILAGE MAIZE":"maize","CORN SILAGE":"maize",
"SUGAR BEET":"root crop","EDIBLE POTATOES":"root crop","FOOD INDUSTRY POTATOES":"root crop","EARLY POTATOES":"root crop",
"FIELD VEGETABLES SINGLE CULTURE":"field veg","FIELD VEGETABLES PROCESSING SINGLE CULTURE":"field veg","FIELD VEGETABLES PROCESSING MULTI-CULTURED":"field veg","OIL PUMPKIN":"field veg",
"SOYBEANS":"legume/oilseed","SUNFLOWERS":"legume/oilseed","WINTER RAPE":"legume/oilseed",
"GREEN FALLOW":"fallow/forage","ALFALFA":"fallow/forage","OTHER FIELD FORAGE":"fallow/forage","CLOVER GRASS":"fallow/forage"}
PEREN=("FALLOW","ALFALFA","FORAGE","MEADOW","TURF","GREENHOUSE","CHERR","PLUM","APRICOT","SHRUB","STRAWBERR","ASPARAGUS","PASTURE","GRASSLAND","CLOVER","ORCHARD")
def load(A):
    M=json.load(open(f"{A}/meta.json")); aoi=np.load(f"{A}/aoi_means.npy"); X=[];L=[];Yr=[]
    for y in YEARS:
        d=M["years"][str(y)]; E=np.load(f"{A}/parcel_means_{y}.npy")-aoi[y-2019]
        for i,(h,n) in enumerate(zip(d["hcat"],d["count"])):
            if n>=5: X.append(E[i]); L.append(h); Yr.append(y)
    return M,aoi,np.array(X),np.array(L),np.array(Yr)
Ms,aois,Xs,Ls,Ys=load(SRC); Mt,aoit,Xt,Lt,Yt=load(TGT)
cs=collections.Counter(Ls); ct=collections.Counter(Lt)
print("target top crops:",ct.most_common(10))
# ---- (a) crop type
shared=[c for c in cs if cs[c]>=40 and ct[c]>=40]
ms=np.isin(Ls,shared); mt=np.isin(Lt,shared)
clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=4000,C=0.5)).fit(Xs[ms],Ls[ms]); p=clf.predict(Xt[mt])
print(f"\n(a) fine crop, {len(shared)} shared classes, n_target={mt.sum()}")
print(f"   Marchfeld -> Upper Austria : acc {accuracy_score(Lt[mt],p):.3f} macroF1 {f1_score(Lt[mt],p,average='macro'):.3f}  majority {max(collections.Counter(Lt[mt]).values())/mt.sum():.3f}")
pl=np.empty(mt.sum(),dtype=object); idx=np.flatnonzero(mt)
for ty in YEARS:
    tr=idx[Yt[idx]!=ty]; te=idx[Yt[idx]==ty]
    pl[np.searchsorted(idx,te)]=make_pipeline(StandardScaler(),LogisticRegression(max_iter=4000,C=0.5)).fit(Xt[tr],Lt[tr]).predict(Xt[te])
print(f"   Upper Austria own LOYO     : acc {accuracy_score(Lt[mt],pl):.3f} macroF1 {f1_score(Lt[mt],pl,average='macro'):.3f}")
for c in sorted(shared,key=lambda c:-ct[c]):
    m=Lt[mt]==c; print(f"     recall transfer {np.mean(p[m]==c):.2f}  own {np.mean(pl[m]==c):.2f}  n={m.sum():4d} {c}")
gs=np.array([GROUP.get(l,"other") for l in Ls]); gt=np.array([GROUP.get(l,"other") for l in Lt])
sg=[g for g in set(gs) if g!="other" and (gs==g).sum()>=40 and (gt==g).sum()>=40]
a=np.isin(gs,sg); b=np.isin(gt,sg)
pg=make_pipeline(StandardScaler(),LogisticRegression(max_iter=4000,C=0.5)).fit(Xs[a],gs[a]).predict(Xt[b])
print(f"   crop group ({len(sg)} groups) transfer: acc {accuracy_score(gt[b],pg):.3f} macroF1 {f1_score(gt[b],pg,average='macro'):.3f}")
# ---- (b) rotation threshold calibrated in Marchfeld (0.5) applied to target
P=json.load(open(f"{TGT}/parcels_utm.json")); U=np.load(f"{TGT}/unit_means.npy")
ug=[wkt.loads(f["wkt"]) for f in P["2024"]]; ucnt=np.array([Mt["unit_counts"][str(y)] for y in YEARS])
ulab=np.full((7,len(ug)),None,dtype=object)
for yi,y in enumerate(YEARS):
    gg=[wkt.loads(f["wkt"]) for f in P[str(y)]]; tree=STRtree(gg)
    for u,g in enumerate(ug):
        best=(0,None)
        for j in tree.query(g):
            ov=gg[j].intersection(g).area/g.area
            if ov>best[0]: best=(ov,P[str(y)][j]["hcat"])
        if best[0]>=0.8: ulab[yi,u]=best[1]
cos=lambda a,b:1-np.dot(a,b)/np.linalg.norm(a)/np.linalg.norm(b)
ch=[];cen=[];rawd=[];kinds=collections.Counter();grass=[]
for yi in range(6):
    for u in range(len(ug)):
        x,z=ulab[yi,u],ulab[yi+1,u]
        if x is None or z is None or ucnt[yi,u]<5 or ucnt[yi+1,u]<5: continue
        if any(k in (x+z).upper() for k in ("CHERR","PLUM","APRICOT","SHRUB","GREENHOUSE","ORCHARD","VINE","TURF")): continue
        ch.append(x!=z); cen.append(cos(U[yi,u]-aoit[yi],U[yi+1,u]-aoit[yi+1])); rawd.append(cos(U[yi,u],U[yi+1,u]))
        if x==z: kinds[x]+=1
        grass.append(any(k in (x+z).upper() for k in ('MEADOW','PASTURE','FALLOW','FORAGE','CLOVER','ALFALFA')))
ch=np.array(ch); cen=np.array(cen); rawd=np.array(rawd)
print(f"\n(b) rotation, target arable pairs n={len(ch)} changed={ch.mean():.2f}: AUC raw {roc_auc_score(ch,rawd):.3f} centred {roc_auc_score(ch,cen):.3f}")
for t in (0.4,0.5,0.6):
    pass
grass=np.array(grass); g=~grass
print(f"   excluding any grass/fallow/forage pair: n={g.sum()} changed={ch[g].mean():.2f} AUC centred {roc_auc_score(ch[g],cen[g]):.3f}")
for t in (0.4,0.5,0.6):
    print(f"   [all] threshold {t}: precision {precision_score(ch,cen>=t):.3f} recall {recall_score(ch,cen>=t):.3f} FPR {((cen>=t)&~ch).sum()/(~ch).sum():.3f}")
ts=np.linspace(0.1,1.2,111); best=max(ts,key=lambda t:recall_score(ch,cen>=t)-((cen>=t)&~ch).sum()/(~ch).sum())
print(f"   target's own best (Youden) threshold: {best:.2f}   | most common unchanged:",kinds.most_common(4))
print("   centred quantiles unchanged",np.round(np.quantile(cen[~ch],[.1,.5,.9]),2),"changed",np.round(np.quantile(cen[ch],[.1,.5,.9]),2))
for t in (0.4,0.5):
    print(f"   [no grass] threshold {t}: precision {precision_score(ch[g],cen[g]>=t):.3f} recall {recall_score(ch[g],cen[g]>=t):.3f} FPR {((cen[g]>=t)&~ch[g]).sum()/(~ch[g]).sum():.3f}")
# ---- (c) practice detectors
def labels(A,Y,M):
    V=np.load(f"{A}/ndvi_{Y}.npy"); doy=np.array([dt.date.fromisoformat(d).timetuple().tm_yday for d in json.load(open(f"{A}/ndvi_{Y}_dates.json"))])
    E=np.load(f"{A}/parcel_means_{Y}.npy")-np.load(f"{A}/aoi_means.npy")[Y-2019]; grid=np.arange(15,366,5); g2=np.arange(15,351,5); dbl=[]; win=[]
    for i,h in enumerate(M["years"][str(Y)]["hcat"]):
        v=V[:,i]; ok=np.isfinite(v)
        if ok.sum()<20 or M["years"][str(Y)]["count"][i]<5: continue
        s2=savgol_filter(np.interp(g2,doy[ok],v[ok]),7,2)
        pk,_=find_peaks(np.r_[0,s2,s2[-1]],height=0.5,prominence=0.2,distance=8)
        pk=[q for q in pk if 60<=g2[min(q-1,len(g2)-1)]<=300 and q-1<len(g2)-3]
        if not any(k in h for k in PEREN): dbl.append((i,len(pk)>=2))
        if any(k in h for k in PEREN): continue
        s=savgol_filter(np.interp(grid,doy[ok],v[ok]),7,2); mx=np.argmax(np.where(grid<=250,s,-1))
        if s[mx]<0.5: continue
        tr=mx+int(np.argmin(np.where(grid[mx:]<=320,s[mx:],9)))
        if s[tr]>=0.35: continue
        late=s[grid>=320].mean()
        if late<0.3: win.append((i,False))
        elif late>=0.45: win.append((i,True))
    return E,dbl,win,M
src={Y:labels(SRC,Y,Ms) for Y in (2023,2024)}; tgt=labels(TGT,2024,Mt)
Pt=json.load(open(f"{TGT}/parcels_utm.json"))["2024"]
blk=np.array([(int(wkt.loads(p["wkt"]).centroid.x//2000))*100+int(wkt.loads(p["wkt"]).centroid.y//2000) for p in Pt])
print("\n(c) practice detectors, target year 2024")
for name,k in (("double crop (2 complete cycles, arable)",1),("winter green after harvest",2)):
    Xtr=np.vstack([src[Y][0][[i for i,_ in src[Y][k]]] for Y in src]); ytr=np.concatenate([[b for _,b in src[Y][k]] for Y in src])
    ii=np.array([i for i,_ in tgt[k]]); yte=np.array([b for _,b in tgt[k]]); Xte=tgt[0][ii]
    mdl=make_pipeline(StandardScaler(),LogisticRegression(max_iter=4000,C=0.5,class_weight="balanced")).fit(Xtr,ytr); pt=mdl.predict_proba(Xte)[:,1]
    own=cross_val_predict(make_pipeline(StandardScaler(),LogisticRegression(max_iter=4000,C=0.5,class_weight="balanced")),Xte,yte,cv=GroupKFold(5),groups=blk[ii],method="predict_proba")[:,1]
    print(f"  {name}: n={len(yte)} prevalence target {yte.mean():.3f} (Marchfeld {ytr.mean():.3f})")
    print(f"     Marchfeld -> UA : AUC {roc_auc_score(yte,pt):.3f} bal.acc {balanced_accuracy_score(yte,pt>0.5):.3f} precision {precision_score(yte,pt>0.5):.3f} recall {recall_score(yte,pt>0.5):.3f}")
    print(f"     UA own block-CV : AUC {roc_auc_score(yte,own):.3f}")
