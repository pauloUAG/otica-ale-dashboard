"""
generate_dashboard.py
Gera output/dashboard.html a partir de:
  - data/weekly_data.json  (padrão, dados agregados)
  - data/history.json      (--source history, dados diários com seletor de período)

Uso:
    python generate_dashboard.py
    python generate_dashboard.py --source history
"""

import json
import os
import sys
import io
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CITY_ORDER = ["BELÉM", "ANANINDEUA", "CASTANHAL", "CAPANEMA", "MARITUBA"]

OFFER_COLORS = {
    "R$ 1,00":        {"bg": "#FFF2CC", "text": "#8B6914"},
    "MULTIFOCAL":     {"bg": "#D9E2F3", "text": "#34659E"},
    "EXAME DE VISTA": {"bg": "#FCE4D6", "text": "#A0522D"},
    "LIGAÇÃO":        {"bg": "#BDD7EE", "text": "#1E5A8D"},
    "EM DOBRO":       {"bg": "#E2EFDA", "text": "#2D6A2E"},
    "DIA DA MULHER":  {"bg": "#C6EFCE", "text": "#1B5E20"},
    "AQUECIMENTO":    {"bg": "#EDE9FE", "text": "#5B21B6"},
    "OUTRO":          {"bg": "#F3F4F6", "text": "#374151"},
}


def format_period(start: str, end: str) -> str:
    months = {1:"jan",2:"fev",3:"mar",4:"abr",5:"mai",6:"jun",
              7:"jul",8:"ago",9:"set",10:"out",11:"nov",12:"dez"}
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    return f"{s.day:02d} {months[s.month]} \u2014 {e.day:02d} {months[e.month]} {e.year}"


def group_by_city(ads: list) -> list:
    city_data = {}
    for ad in ads:
        city = ad["city"]
        if city not in city_data:
            city_data[city] = {
                "city": city, "spend": 0.0, "conversations": 0,
                "clicks": 0, "reach": 0, "impressions": 0,
                "profile_visits": 0, "ads": [], "offers": {},
            }
        d = city_data[city]
        d["spend"]          += ad["spend"]
        d["conversations"]  += ad["conversations"]
        d["clicks"]         += ad["clicks"]
        d["reach"]          += ad["reach"]
        d["impressions"]    += ad["impressions"]
        d["profile_visits"] += ad["profile_visits"]
        d["ads"].append(ad)

        offer = ad["offer"]
        if offer not in d["offers"]:
            d["offers"][offer] = {"offer": offer, "spend": 0.0,
                                  "conversations": 0, "clicks": 0,
                                  "colors": OFFER_COLORS.get(offer, OFFER_COLORS["OUTRO"])}
        d["offers"][offer]["spend"]         += ad["spend"]
        d["offers"][offer]["conversations"] += ad["conversations"]
        d["offers"][offer]["clicks"]        += ad["clicks"]

    for d in city_data.values():
        d["cpa"]        = round(d["spend"] / d["conversations"], 2) if d["conversations"] else 0.0
        d["active_ads"] = sum(1 for a in d["ads"] if a["spend"] > 0)
        d["top_ads"]    = sorted(d["ads"], key=lambda x: x["conversations"], reverse=True)[:5]
        offers_list     = list(d["offers"].values())
        for o in offers_list:
            o["cpa"] = round(o["spend"] / o["conversations"], 2) if o["conversations"] else 0.0
        d["offers_list"] = sorted(offers_list, key=lambda x: x["conversations"], reverse=True)

    ordered = []
    for city in CITY_ORDER:
        if city in city_data:
            ordered.append(city_data[city])
    for city, data in city_data.items():
        if city not in CITY_ORDER:
            ordered.append(data)
    return ordered


def build_totals(ads: list) -> dict:
    sp = sum(a["spend"] for a in ads)
    cv = sum(a["conversations"] for a in ads)
    return {
        "spend":          round(sp, 2),
        "conversations":  cv,
        "cpa":            round(sp / cv, 2) if cv else 0.0,
        "reach":          sum(a["reach"] for a in ads),
        "impressions":    sum(a["impressions"] for a in ads),
        "clicks":         sum(a["clicks"] for a in ads),
        "profile_visits": sum(a["profile_visits"] for a in ads),
        "ads_count":      len(ads),
        "active_ads":     sum(1 for a in ads if a.get("status") == "ATIVO"),
    }


def aggregate_records(records: list) -> list:
    """Agrega registros diários por nome de anúncio."""
    agg = {}
    for r in records:
        key = r["name"]
        if key not in agg:
            agg[key] = {**r, "_ctr_sum": r.get("ctr", 0), "_ctr_n": 1 if r.get("ctr") else 0}
        else:
            d = agg[key]
            d["spend"]          += r["spend"]
            d["conversations"]  += r["conversations"]
            d["clicks"]         += r["clicks"]
            d["reach"]          += r["reach"]
            d["impressions"]    += r["impressions"]
            d["profile_visits"] += r["profile_visits"]
            d["_ctr_sum"]       += r.get("ctr", 0)
            d["_ctr_n"]         += 1 if r.get("ctr") else 0
            if r.get("status") == "ATIVO":
                d["status"] = "ATIVO"
    result = []
    for d in agg.values():
        d["ctr"] = round(d["_ctr_sum"] / d["_ctr_n"], 4) if d["_ctr_n"] else 0.0
        d["cpa"] = round(d["spend"] / d["conversations"], 2) if d["conversations"] else 0.0
        d.pop("_ctr_sum", None); d.pop("_ctr_n", None); d.pop("date", None)
        result.append(d)
    return result


def generate_html(dashboard_data: dict, history_data, template_path: str) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    data_json    = json.dumps(dashboard_data, ensure_ascii=False, indent=2)
    history_json = json.dumps(history_data,   ensure_ascii=False)
    html = template.replace("__DASHBOARD_DATA__", data_json)
    html = html.replace("__HISTORY_DATA__", history_json)
    return html


def main():
    print("=" * 60)
    print("Ótica Alê Eyewear — Geração do Dashboard")
    print("=" * 60)

    source = "weekly"
    if "--source" in sys.argv:
        idx = sys.argv.index("--source")
        if idx + 1 < len(sys.argv):
            source = sys.argv[idx + 1]

    template_path = "template/dashboard_template.html"
    output_path   = "output/dashboard.html"

    if not Path(template_path).exists():
        print(f"\nERRO: {template_path} não encontrado.")
        return

    history_data  = None  # só carregado se existir
    ad_account_id = ""

    if source == "history":
        history_path = "data/history.json"
        if not Path(history_path).exists():
            print(f"\nERRO: {history_path} não encontrado.")
            print("Execute primeiro: python parse_csv.py arquivo.csv --mode history")
            return
        print(f"\nFonte: {history_path} (modo diário com seletor de período)")
        with open(history_path, encoding="utf-8") as f:
            history_file = json.load(f)
        history_data = history_file
        records = history_file.get("records", [])
        period  = history_file.get("period", {})
        ads     = aggregate_records(records)
    else:
        data_path = "data/weekly_data.json"
        if not Path(data_path).exists():
            print(f"\nERRO: {data_path} não encontrado.")
            print("Execute: python fetch_meta_data.py  ou  python parse_csv.py arquivo.csv")
            return
        print(f"\nFonte: {data_path}")
        with open(data_path, encoding="utf-8") as f:
            weekly_data = json.load(f)
        ads            = weekly_data["ads"]
        period         = weekly_data["period"]
        ad_account_id  = weekly_data.get("ad_account_id", "")
        # Tenta carregar histórico também, se existir
        history_path = "data/history.json"
        if Path(history_path).exists():
            with open(history_path, encoding="utf-8") as f:
                history_data = json.load(f)

    totals  = build_totals(ads)
    cities  = group_by_city(ads)

    print(f"Periodo: {period.get('start','')} a {period.get('end','')}")
    print(f"Anuncios: {totals['ads_count']} | Conversas: {totals['conversations']} | Investimento: R$ {totals['spend']:,.2f}")
    print(f"Cidades: {', '.join(c['city'] for c in cities)}")

    dashboard_data = {
        "period_label":   format_period(period["start"], period["end"]) if period.get("start") and period.get("end") else "",
        "period":         period,
        "generated_at":   datetime.now().isoformat(),
        "source":         source,
        "has_history":    history_data is not None,
        "totals":         totals,
        "cities":         cities,
        "offer_colors":   OFFER_COLORS,
        "ad_account_id":  ad_account_id,
    }

    os.makedirs("output", exist_ok=True)
    html = generate_html(dashboard_data, history_data, template_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = Path(output_path).stat().st_size / 1024
    print(f"\n Dashboard gerado: {output_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
