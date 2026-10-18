"""A1 crop history + rotation profile per unit (2019-2025 AT / 2019-2023 BB).

Validation: centred YoY embedding distance vs declared change (AUC, 0.5 rule), LOYO group
accuracy for gap-filling untracked years. Baselines: majority group, 'always changed'."""

import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE, CEREAL  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
R = {}
p = F[F.declared_change.notna() & F.emb_yoy_centred.notna()]
y, s = p.declared_change.astype(bool), p.emb_yoy_centred
flag = s >= 0.5
R["rotation_pairs"] = dict(n=len(p), changed=round(y.mean(), 3), auc=round(roc_auc_score(y, s), 3),
                           precision_at_0_5=round((flag & y).sum() / flag.sum(), 3), recall_at_0_5=round((flag & y).sum() / y.sum(), 3),
                           fpr_at_0_5=round((flag & ~y).sum() / (~y).sum(), 3), baseline_always_changed_acc=round(y.mean(), 3),
                           acc_at_0_5=round(((flag == y)).mean(), 3))
gprev = F.set_index(["uid", "year"])["group"]
p = p.assign(prev_group=[gprev.get((u, yy - 1)) for u, yy in zip(p.uid, p.year)])
miss = p[y & ~flag]
R["missed_changes_same_group_share"] = round((miss.group == miss.prev_group).mean(), 3)
R["missed_change_top"] = Counter(zip(miss.prev_hcat, miss.hcat)).most_common(6)
fa = p[~y & flag]
R["false_alarm_top_crops"] = Counter(fa.hcat).most_common(6)

# gap filling of untracked years
t = F[F.tracked & F.emb_group.notna()]
R["loyo_group_acc"] = round((t.emb_group == t.group).mean(), 3)
R["majority_group_acc"] = round(t.group.value_counts(normalize=True).iloc[0], 3)
R["untracked_unit_years"] = int((~F.tracked).sum())
R["untracked_with_embedding_group"] = int((~F.tracked & F.emb_group.notna()).sum())

# per-unit profile
prof = []
for uid, g in F.sort_values("year").groupby("uid"):
    seq = list(g.hcat.where(g.tracked, None))
    grp = list(g.group.where(g.tracked, None))
    dec = [x for x in grp if isinstance(x, str)]
    if len(dec) < 4:
        continue
    run, best = 1, 1
    for a, b in zip(seq, seq[1:]):
        run = run + 1 if (isinstance(a, str) and a == b) else 1
        best = max(best, run)
    c = Counter(dec)
    pr = np.array(list(c.values())) / len(dec)
    emb_flags = int((g.emb_yoy_centred >= 0.5).sum())
    dc = g.declared_change.dropna()
    disagree = int(((g.emb_yoy_centred >= 0.5) != (g.declared_change == 1))[g.declared_change.notna() & g.emb_yoy_centred.notna()].sum())
    prof.append(dict(uid=uid, n_years=len(dec), arable_share=sum(x in ARABLE for x in dec) / len(dec), cereal_share=sum(x in CEREAL for x in dec) / len(dec),
                     n_crops=len(set(x for x in seq if isinstance(x, str))), group_entropy=float(-(pr * np.log2(pr)).sum()), max_monoculture_run=best,
                     declared_changes=int(dc.sum()), emb_changes=emb_flags, disagreements=disagree))
P = pd.DataFrame(prof)
P.to_csv(f"{D}/{name}/rotation_profiles.csv", index=False)
ar = P[P.arable_share >= 0.8]
R["profiles"] = dict(n_units=len(P), n_arable=len(ar), cereal_share_median=round(ar.cereal_share.median(), 2),
                     cereal_share_ge_0_6=round((ar.cereal_share >= 0.6).mean(), 3), monoculture_run_ge_3=round((ar.max_monoculture_run >= 3).mean(), 3),
                     group_entropy_median=round(ar.group_entropy.median(), 2), n_crops_median=float(ar.n_crops.median()),
                     units_with_any_disagreement=round((ar.disagreements > 0).mean(), 3), units_with_ge2_disagreements=round((ar.disagreements >= 2).mean(), 3))
json.dump(R, open(f"results/{name}_a1_rotation.json", "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str))
