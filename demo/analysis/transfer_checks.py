import json,sys,collections,numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import accuracy_score,f1_score
exec(open(sys.argv[3]).read().split("# ---- (a)")[0].split("SRC, TGT")[0])  # imports only
SRC,TGT=sys.argv[1],sys.argv[2]; YEARS=list(range(2019,2026))
def load(A,center,stand=False):
    M=json.load(open(f"{A}/meta.json")); aoi=np.load(f"{A}/aoi_means.npy"); X=[];L=[]
    allE=[]
    for y in YEARS:
        d=M["years"][str(y)]; E=np.load(f"{A}/parcel_means_{y}.npy")
        keep=[i for i,n in enumerate(d["count"]) if n>=5]
        Ey=E[keep]-(aoi[y-2019] if center else 0)
        X.append(Ey); L+= [d["hcat"][i] for i in keep]
    return np.vstack(X),np.array(L)
for mode in ("raw","centred"):
    Xs,Ls=load(SRC,mode=="centred"); Xt,Lt=load(TGT,mode=="centred")
    cs=collections.Counter(Ls); ct=collections.Counter(Lt); sh=[c for c in cs if cs[c]>=40 and ct[c]>=40]
    a=np.isin(Ls,sh); b=np.isin(Lt,sh)
    p=make_pipeline(StandardScaler(),LogisticRegression(max_iter=4000,C=0.5)).fit(Xs[a],Ls[a]).predict(Xt[b])
    print(f"transfer {mode}: acc {accuracy_score(Lt[b],p):.3f} macroF1 {f1_score(Lt[b],p,average='macro'):.3f}")
    if mode=="centred":
        for c in ("GRAIN CORN","WINTER BARLEY","WINTER TRITICALE"):
            m=Lt[b]==c; print(f"   {c} predicted as:",collections.Counter(p[m]).most_common(3))
