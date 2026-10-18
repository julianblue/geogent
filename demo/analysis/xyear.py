"""Cross-year transfer of practice detectors: train on one year's embeddings + NDVI-derived labels, test on another."""
import json, sys, numpy as np, datetime as dt
from scipy.signal import savgol_filter, find_peaks
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, balanced_accuracy_score, precision_score, recall_score
A=sys.argv[1]; YEARS=[int(y) for y in sys.argv[2:]]
M=json.load(open(f"{A}/meta.json"))["years"]; aoi=np.load(f"{A}/aoi_means.npy")
PEREN=("FALLOW","ALFALFA","FORAGE","MEADOW","TURF","GREENHOUSE","CHERR","PLUM","APRICOT","SHRUB","STRAWBERR","ASPARAGUS")
def labels(Y):
    V=np.load(f"{A}/ndvi_{Y}.npy"); doy=np.array([dt.date.fromisoformat(d).timetuple().tm_yday for d in json.load(open(f"{A}/ndvi_{Y}_dates.json"))])
    E=np.load(f"{A}/parcel_means_{Y}.npy")-aoi[Y-2019]; grid=np.arange(15,366,5); g2=np.arange(15,351,5)
    dbl=[]; win=[]
    for i,h in enumerate(M[str(Y)]["hcat"]):
        v=V[:,i]; ok=np.isfinite(v)
        if ok.sum()<20 or M[str(Y)]["count"][i]<5: continue
        s2=savgol_filter(np.interp(g2,doy[ok],v[ok]),7,2)
        pk,_=find_peaks(np.r_[0,s2,s2[-1]],height=0.5,prominence=0.2,distance=8)
        pk=[p for p in pk if 60<=g2[min(p-1,len(g2)-1)]<=300 and p-1<len(g2)-3]
        dbl.append((i,len(pk)>=2))
        if any(k in h for k in PEREN): continue
        s=savgol_filter(np.interp(grid,doy[ok],v[ok]),7,2); main=np.argmax(np.where(grid<=250,s,-1))
        if s[main]<0.5: continue
        tr=main+int(np.argmin(np.where(grid[main:]<=320,s[main:],9)))
        if s[tr]>=0.35: continue
        late=s[grid>=320].mean()
        if late<0.3: win.append((i,False))
        elif late>=0.45: win.append((i,True))
    return E,dbl,win
L={Y:labels(Y) for Y in YEARS}
for Y in YEARS: print(Y,"double-crop prevalence",round(np.mean([b for _,b in L[Y][1]]),3),"n",len(L[Y][1]),"| winter-green prevalence",round(np.mean([b for _,b in L[Y][2]]),3),"n",len(L[Y][2]))
for task,k in (("double crop (2 complete cycles)",1),("winter green after harvest",2)):
    print(f"\n{task}:")
    for tr in YEARS:
        for te in YEARS:
            if tr==te: continue
            Etr,Ete=L[tr][0],L[te][0]; a=L[tr][k]; b=L[te][k]
            Xtr=Etr[[i for i,_ in a]]; ytr=np.array([y for _,y in a]); Xte=Ete[[i for i,_ in b]]; yte=np.array([y for _,y in b])
            clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,C=0.5,class_weight="balanced")).fit(Xtr,ytr)
            p=clf.predict_proba(Xte)[:,1]
            print(f"  train {tr} -> test {te}: AUC {roc_auc_score(yte,p):.3f}  bal.acc {balanced_accuracy_score(yte,p>0.5):.3f}  precision {precision_score(yte,p>0.5):.3f}  recall {recall_score(yte,p>0.5):.3f}")
