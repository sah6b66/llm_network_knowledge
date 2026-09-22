import json
import os

os.makedirs("data/topics_slices", exist_ok=True)
ts = json.load(open("data/topics.json", encoding="utf-8"))

def by_layer(layer, offset=0, limit=None):
    sel = [t for t in ts if t["category"]["protocol_layer"] == layer]
    sel = sel[offset:]
    if limit:
        sel = sel[:limit]
    return sel

out = {
    "data/topics_slices/topics_1_physical.json": by_layer("物理层"),
    "data/topics_slices/topics_2_link.json": by_layer("链路层"),
    "data/topics_slices/topics_3a_ip.json": by_layer("IP层", 0, 15),
    "data/topics_slices/topics_3b_ip.json": by_layer("IP层", 15),
    "data/topics_slices/topics_4_transport.json": by_layer("传输层"),
    "data/topics_slices/topics_5_other.json": by_layer("其他"),
}
for f, sel in out.items():
    json.dump(sel, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f, len(sel))
