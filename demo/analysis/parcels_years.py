import duckdb, json, sys
from pyproj import Transformer
import shapely
from shapely import wkb
BB=(16.54,48.22,16.66,48.29)
t=Transformer.from_crs(4326,31287,always_xy=True)
xs,ys=zip(*[t.transform(x,y) for x in BB[0::2] for y in BB[1::2]])
to_utm=Transformer.from_crs(31287,32633,always_xy=True)
con=duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET enable_server_cert_verification=true; SET ca_cert_file='/root/.ccr/ca-bundle.crt'")
out={}
for y in range(2019,2026):
    url=f"https://data.source.coop/ftw/harmonized-field-data/at/year={y}/at-{y}.parquet"
    rows=con.execute(f"""SELECT id, "crop:name", "hcat:name_en", "hcat:code", ST_AsWKB(geometry) FROM '{url}'
      WHERE bbox.xmin>={min(xs)} AND bbox.xmax<={max(xs)} AND bbox.ymin>={min(ys)} AND bbox.ymax<={max(ys)}""").fetchall()
    feats=[]
    for pid,name,en,code,g in rows:
        geom=shapely.transform(wkb.loads(bytes(g)), lambda c: __import__('numpy').column_stack(to_utm.transform(c[:,0],c[:,1])))
        feats.append({"id":str(pid),"crop":name,"hcat":en,"hcat_code":code,"wkt":geom.wkt,"ha":geom.area/1e4})
    out[y]=feats; print(y,len(feats),"parcels",round(sum(f["ha"] for f in feats)),"ha",flush=True)
json.dump(out,open(sys.argv[1],"w"))
