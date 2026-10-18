import json, sys, collections, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import f1_score, accuracy_score, roc_auc_score, confusion_matrix
from sklearn.decomposition import PCA
S=sys.argv[1]; A=f"{S}/ana"
M=json.load(open(f"{A}/meta.json")); YEARS=list(range(2019,2026))
aoi=np.load(f"{A}/aoi_means.npy")
GROUP={"WINTER SOFT WHEAT":"winter cereal","HARD WINTER WHEAT (DURUM)":"winter cereal","WINTER BARLEY":"winter cereal","WINTER RYE":"winter cereal","WINTER TRITICALE":"winter cereal","WINTER SPELT (SPELT)":"winter cereal",
"SUMMER BARLEY":"spring cereal","SUMMER HARD WHEAT (DURUM)":"spring cereal","MILLET":"spring cereal",
"GRAIN CORN":"maize","SEED CORN PROPAGATION":"maize","SUGAR CORN":"maize",
"SUGAR BEET":"root crop","EDIBLE POTATOES":"root crop","FOOD INDUSTRY POTATOES":"root crop","EARLY POTATOES":"root crop",
"FIELD VEGETABLES SINGLE CULTURE":"field veg","FIELD VEGETABLES PROCESSING SINGLE CULTURE":"field veg","FIELD VEGETABLES PROCESSING MULTI-CULTURED":"field veg","OIL PUMPKIN":"field veg",
"SOYBEANS":"legume/oilseed","SUNFLOWERS":"legume/oilseed","WINTER RAPE":"legume/oilseed",
"GREEN FALLOW":"fallow/forage","ALFALFA":"fallow/forage","OTHER FIELD FORAGE":"fallow/forage"}
rows=[]
for y in YEARS:
    d=M["years"][str(y)]; X=np.load(f"{A}/parcel_means_{y}.npy")
    for i,(h,n) in enumerate(zip(d["hcat"],d["count"])):
        if n>=5: rows.append((y,h,X[i],X[i]-aoi[y-2019],d["disp"][i],n,d["ids"][i],d["crop"][i]))
yr=np.array([r[0] for r in rows]); lab=np.array([r[1] for r in rows]); Xr=np.stack([r[2] for r in rows]); Xc=np.stack([r[3] for r in rows])
cnt=collections.Counter(lab); keep=np.array([cnt[l]>=40 for l in lab])
out={}
def loyo(X,y_lab,mask,name):
    preds=np.empty(mask.sum(),dtype=object); idx=np.flatnonzero(mask); per={}
    for ty in YEARS:
        tr=idx[yr[idx]!=ty]; te=idx[yr[idx]==ty]
        clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=0.5)); clf.fit(X[tr],y_lab[tr])
        p=clf.predict(X[te]); preds[np.searchsorted(idx,te)]=p
        per[ty]=round(accuracy_score(y_lab[te],p),3)
    yt=y_lab[idx]; acc=accuracy_score(yt,preds); f1=f1_score(yt,preds,average="macro")
    base=collections.Counter(yt).most_common(1)[0][1]/len(yt)
    print(f"{name}: n={len(idx)} classes={len(set(yt))} acc={acc:.3f} macroF1={f1:.3f} majority={base:.3f} per-year={per}")
    return preds,acc,f1,per
# A. crop type, leave-one-year-out
pA,accA,f1A,perA=loyo(Xr,lab,keep,"fine crop, raw, LOYO")
pAc,accAc,f1Ac,perAc=loyo(Xc,lab,keep,"fine crop, year-centred, LOYO")
grp=np.array([GROUP.get(l,"other") for l in lab]); gmask=grp!="other"
pG,accG,f1G,perG=loyo(Xc,grp,gmask,"crop group, year-centred, LOYO")
# within-year random CV for comparison (same-year generalisation)
from sklearn.model_selection import cross_val_predict, StratifiedKFold
idx=np.flatnonzero(keep)
pcv=cross_val_predict(make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=0.5)),Xc[idx],lab[idx],cv=StratifiedKFold(5,shuffle=True,random_state=0))
print("fine crop, random 5-fold (mixes years): acc=%.3f macroF1=%.3f"%(accuracy_score(lab[idx],pcv),f1_score(lab[idx],pcv,average="macro")))
# per-class recall + top confusions (LOYO centred)
yt=lab[keep]; classes=sorted(set(yt)); cm=confusion_matrix(yt,pAc,labels=classes)
print("\nper-class recall (LOYO, centred):")
for i,c in enumerate(classes): print(f"  {cm[i,i]/cm[i].sum():.2f}  n={cm[i].sum():4d}  {c}")
conf=[(cm[i,j],classes[i],classes[j]) for i in range(len(classes)) for j in range(len(classes)) if i!=j]
print("top confusions:"); [print(f"  {n:3d}  {a}  ->  {b}") for n,a,b in sorted(conf,reverse=True)[:10]]
# B. year effect
def cos(a,b): return 1-np.dot(a,b)/np.linalg.norm(a)/np.linalg.norm(b)
yd=[np.linalg.norm(aoi[i+1]-aoi[i]) for i in range(6)]
cents={c:Xc[lab==c].mean(0) for c in classes}
cd=[np.linalg.norm(cents[a]-cents[b]) for a in classes for b in classes if a<b]
print(f"\nyear offset |AOI mean_y+1 - AOI mean_y|: {np.round(yd,2)}  vs between-crop centroid dist median {np.median(cd):.2f} (min {min(cd):.2f})")
print("AOI-mean norm per year:",np.round(np.linalg.norm(aoi,axis=1),2), " typical parcel-mean norm:",round(float(np.median(np.linalg.norm(Xr,axis=1))),2))
# C. PCA interpretation
pca=PCA(5).fit(Xc[gmask]); Z=pca.transform(Xc)
print("\nPCA explained var:",np.round(pca.explained_variance_ratio_,3))
for k in range(3):
    s=sorted(((Z[(grp==g),k].mean(),g) for g in set(grp[gmask])))
    print(f"PC{k+1}: "+"  <  ".join(f"{g}({v:+.1f})" for v,g in s))
# D. rotation detection on fixed units (2024 geometries), labels per year by best overlap
U=np.load(f"{A}/unit_means.npy"); uids=M["units_ids"]
import shapely; from shapely import wkt, STRtree
P=json.load(open(f"{A}/parcels_utm.json"))
ug=[wkt.loads(f["wkt"]) for f in P["2024"]]
ulab=np.full((7,len(ug)),None,dtype=object)
for yi,y in enumerate(YEARS):
    gs=[wkt.loads(f["wkt"]) for f in P[str(y)]]; tree=STRtree(gs)
    for u,g in enumerate(ug):
        best=(0,None)
        for j in tree.query(g):
            ov=gs[j].intersection(g).area/g.area
            if ov>best[0]: best=(ov,P[str(y)][j]["hcat"])
        if best[0]>=0.8: ulab[yi,u]=best[1]
ucnt=np.array([M["unit_counts"][str(y)] for y in YEARS])
pairs=[]
for yi in range(6):
    for u in range(len(ug)):
        a,b=ulab[yi,u],ulab[yi+1,u]
        if a is None or b is None or ucnt[yi,u]<5: continue
        raw=cos(U[yi,u],U[yi+1,u]); cen=cos(U[yi,u]-aoi[yi],U[yi+1,u]-aoi[yi+1])
        pairs.append((a!=b,raw,cen,a,b,GROUP.get(a,"other")!=GROUP.get(b,"other"),YEARS[yi]))
ch=np.array([p[0] for p in pairs]); raw=np.array([p[1] for p in pairs]); cen=np.array([p[2] for p in pairs]); gch=np.array([p[5] for p in pairs])
print(f"\nrotation pairs: n={len(pairs)}, changed(fine)={ch.mean():.2f}")
print(f"AUC fine-change: raw={roc_auc_score(ch,raw):.3f} centred={roc_auc_score(ch,cen):.3f}")
same_grp=~gch
print(f"AUC group-change (vs same crop): centred={roc_auc_score(gch[(gch)|(~ch)],cen[(gch)|(~ch)]):.3f}")
ths=np.linspace(0.1,1.5,141); best=max(ths,key=lambda t:((cen>=t)&ch).sum()/ch.sum()-((cen>=t)&~ch).sum()/(~ch).sum())
tp=((cen>=best)&ch).sum(); fp=((cen>=best)&~ch).sum(); fn=((cen<best)&ch).sum()
print(f"best centred threshold (Youden) {best:.2f}: precision={tp/(tp+fp):.3f} recall={tp/(tp+fn):.3f}")
for t in (0.3,0.5,0.7):
    tp=((cen>=t)&ch).sum(); fp=((cen>=t)&~ch).sum(); fn=((cen<t)&ch).sum(); print(f"  t={t}: precision={tp/(tp+fp):.3f} recall={tp/(tp+fn):.3f}")
print("centred dist quantiles  unchanged:",np.round(np.quantile(cen[~ch],[.1,.5,.9]),2)," changed:",np.round(np.quantile(cen[ch],[.1,.5,.9]),2))
# which unchanged pairs look like change, which changes look unchanged
uc=collections.defaultdict(list)
for p in pairs:
    if not p[0]: uc[p[3]].append(p[2])
print("unchanged by crop (median centred dist, n):"); [print(f"  {np.median(v):.2f} n={len(v):3d} {k}") for k,v in sorted(uc.items(),key=lambda kv:-np.median(kv[1])) if len(v)>=10]
lowch=collections.Counter((p[3],p[4]) for p in pairs if p[0] and p[2]<best)
print("changes scored as unchanged (most common):"); [print(f"  {n:3d} {a} -> {b}") for (a,b),n in lowch.most_common(6)]
# E. declaration anomalies: parcels whose embedding strongly disagrees with declared crop (LOYO probs)
from sklearn.model_selection import cross_val_predict
G=grp[gmask]; Xg=Xc[gmask]
prob=np.zeros((gmask.sum(),len(set(G)))); cls=None
for ty in YEARS:
    tr=yr[gmask]!=ty; te=~tr
    clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=0.5)).fit(Xg[tr],G[tr]); cls=clf.classes_
    prob[te]=clf.predict_proba(Xg[te])
pdecl=prob[np.arange(len(G)),np.searchsorted(cls,G)]
flag=pdecl<0.05
print(f"\nanomalies: {flag.mean():.3f} of parcel-years have P(declared group)<0.05")
ri=np.flatnonzero(gmask)
an=collections.Counter((G[i],cls[prob[i].argmax()]) for i in np.flatnonzero(flag))
for (a,b),n in an.most_common(8): print(f"  {n:3d} declared {a} -> looks like {b}")
# F. similarity search precision@10 across years (query year vs other years)
from sklearn.neighbors import NearestNeighbors
Xn=Xc[keep]/np.linalg.norm(Xc[keep],axis=1,keepdims=True); L=lab[keep]; Yk=yr[keep]
nn=NearestNeighbors(n_neighbors=60,metric="cosine").fit(Xn); _,I=nn.kneighbors(Xn)
pk=[]; 
for i in range(len(Xn)):
    nb=[j for j in I[i] if Yk[j]!=Yk[i]][:10]; pk.append(np.mean(L[nb]==L[i]))
print(f"similarity search, other-year neighbours, precision@10 same fine crop: {np.mean(pk):.3f} (chance ~{sum((v/len(L))**2 for v in collections.Counter(L).values()):.3f})")
# G. pixel vs parcel: within-parcel dispersion by crop
disp=collections.defaultdict(list)
for r in rows: disp[r[1]].append(r[4])
print("\nwithin-parcel dispersion (mean px dist to parcel mean), highest/lowest:")
ds=sorted(((np.median(v),k,len(v)) for k,v in disp.items() if len(v)>=40))
for v,k,n in ds[:4]+ds[-4:]: print(f"  {v:.2f} n={n} {k}")
json.dump({"pairs":[(bool(a),float(b),float(c),d,e,bool(f),g) for a,b,c,d,e,f,g in pairs]},open(f"{A}/pairs.json","w"))
