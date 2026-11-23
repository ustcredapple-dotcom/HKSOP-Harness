"""Canonicalize a purchase bill by standard, dimensions, grade and finish."""
import argparse,csv,json,math,re
from pathlib import Path
INTERNAL=re.compile(r'(?i)(?:^|[\s/])(?:v\d+-|custom-|new-|vendor-item-|kit-|lib-|hardware-|component-)')
def text(value):return re.sub(r'\s+',' ',str(value)).strip()
def group(row):
    model=text(row.get("model") or row.get("name") or row.get("description",""))
    desc=text(row.get("description") or row.get("name") or model)
    phrase=(model+" "+desc).upper().replace("Ø","D").replace("Φ","D").replace("×","X").replace("*","X")
    size=re.search(r'\b([MD])\s*(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)',phrase,re.ASCII)
    if not size:size=re.search(r'([MD])\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)',phrase)
    fastener=bool(re.search(r"螺[钉栓]|圆柱头|薄头|定位销|圆柱销|弹性销|SCREW|DOWEL|SOCKET HEAD|ISO[ -]?4762|DIN[ -]?912",phrase))
    if size and (fastener or re.match(r"^[MDØΦ]\s*\d+\s*[×xX]",model) is not None):
        dim="×".join(str(float(s)).removesuffix(".0") for s in size.group(2,3))
        if size[1]=="D":model="Ø"+dim+" "+("弹性销" if "弹性" in phrase else "圆柱销")
        else:
            norm=re.search(r'(ISO|DIN|GB/T)[\s-]*(\d+)',phrase)
            kind=norm[1]+" "+norm[2] if norm else "ISO 4762" if ("圆柱头" in phrase or "柱头" in phrase or "SOCKET HEAD CAP" in phrase) and "薄头" not in phrase else ("薄头螺钉" if "薄头" in phrase else "平头螺钉" if "沉头" in phrase else "螺钉")
            model=kind+" M"+dim
        # Distinct purchased material, thread pitch or surface finishes stay separate.
        for token in (row.get("material"),row.get("grade"),row.get("finish"),row.get("threadPitch")):
            if token:model+=" "+text(token)
        for token in re.findall(r'(?<![A-Z0-9])(?:A[24]-[578]0|12\.9|10\.9|8\.8|316L?|304)(?![A-Z0-9])|黑氧化|镀锌|不锈钢',phrase):
            if token not in model:model+=" "+token
    if INTERNAL.search(model):model=desc
    if not model or INTERNAL.search(model):raise ValueError("需提供可采购型号或规范名称 "+desc)
    return model,desc
def normalize(rows):
    groups={}
    for raw in rows:
        model,desc=group(raw);key=text(model).casefold()
        quantity=raw.get("quantity",raw.get("qty"))
        if isinstance(quantity,bool) or not isinstance(quantity,(float,int)) or not math.isfinite(quantity) or quantity<=0:raise ValueError("数量无效 "+model)
        g=groups.setdefault(key,dict(model=model,description=desc,quantity=0,category=raw.get("category","标准 / 外购"),sources=[],note=""))
        origin=raw.get("source") or raw.get("assembly") or raw.get("note") or desc
        sources=raw.get("sources") or [dict(source=origin,quantity=quantity)]
        if sum(x["quantity"] for x in sources)!=quantity:raise ValueError("来源分解与数量不符 "+model)
        g["sources"].extend(dict(source=text(s["source"]),quantity=s["quantity"]) for s in sources)
        g["quantity"]+=quantity
        if raw.get("note") and raw["note"] not in g["note"]:g["note"]=text(g["note"]+" "+raw["note"])
    return sorted(groups.values(),key=lambda row:row["model"].casefold())
def audit(rows):
    keys=[group(row)[0].casefold() for row in rows];dup=len(keys)-len(set(keys))
    leak=[row["model"] for row in rows if INTERNAL.search(row["model"])]
    provenance=all(row.get("sources") and sum(s["quantity"] for s in row["sources"])==row["quantity"] for row in rows)
    return dict(uniqueSpecifications=not dup,duplicateGroups=sorted(k for k in set(keys) if keys.count(k)>1),internalModelLeaks=leak,quantitiesTraceable=provenance,valid=bool(rows) and not dup and not leak and provenance)
def write(data,folder):
    if "lineItems" in data:rows=data["lineItems"]
    else:rows=data["components"]
    frozen={k:data[k] for k in ("revision","projectSha256","notes","manufacturerCableRating") if k in data}
    normalized=normalize(rows);result=audit(normalized)
    if not result["valid"]:raise ValueError(str(result))
    folder.mkdir(exist_ok=True,parents=True)
    (folder/"bom.json").write_text(json.dumps(dict(frozen,lineItems=normalized),ensure_ascii=False,indent=2)+"\n")
    with (folder/"bom.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f);writer.writerow(["类别","型号","名称","数量","来源分解","装配说明"])
        for row in normalized:
            writer.writerow([row["category"],row["model"],row["description"],row["quantity"]," / ".join(str(q["quantity"])+" × "+q["source"] for q in row["sources"]),row["note"]])
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("input",type=Path);p.add_argument("-o",type=Path,required=True)
    a=p.parse_args();print(json.dumps(write(json.loads(a.input.read_bytes()),a.o),ensure_ascii=False))
