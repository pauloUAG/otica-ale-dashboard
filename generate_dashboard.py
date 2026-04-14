"""
generate_dashboard.py
Lê data/weekly_data.json e gera output/dashboard.html com dados injetados.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows: força stdout em UTF-8 para evitar erro com caracteres especiais
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

CITY_ORDER = ["BELÉM", "ANANINDEUA", "CASTANHAL", "CAPANEMA", "MARITUBA"]
OFFER_COLORS = {
    "R$ 1,00":       {"bg": "#FFF2CC", "text": "#8B6914"},
    "MULTIFOCAL":    {"bg": "#D9E2F3", "text": "#34659E"},
    "EXAME DE VISTA": {"bg": "#FCE4D6", "text": "#A0522D"},
    "LIGAÇÃO":       {"bg": "#BDD7EE", "text": "#1E5A8D"},
    "EM DOBRO":      {"bg": "#E2EFDA", "text": "#2D6A2E"},
    "DIA DA MULHER": {"bg": "#C6EFCE", "text": "#1B5E20"},
    "OUTRO":         {"bg": "#F3F4F6", "text": "#374151"},
}


def group_by_city(ads: list[dict]) -> dict:
    """Agrupa anúncios por cidade com sub-agrupamento por oferta."""
    city_data = {}

    for ad in ads:
        city = ad["city"]
        if city not in city_data:
            city_data[city] = {
                "city": city,
                "spend": 0.0,
                "conversations": 0,
                "clicks": 0,
                "reach": 0,
                "impressions": 0,
                "profile_visits": 0,
                "ads": [],
                "offers": {},
            }

        d = city_data[city]
        d["spend"] += ad["spend"]
        d["conversations"] += ad["conversations"]
        d["clicks"] += ad["clicks"]
        d["reach"] += ad["reach"]
        d["impressions"] += ad["impressions"]
        d["profile_visits"] += ad["profile_visits"]
        d["ads"].append(ad)

        # Sub-agrupamento por oferta
        offer = ad["offer"]
        if offer not in d["offers"]:
            d["offers"][offer] = {
                "offer": offer,
                "spend": 0.0,
                "conversations": 0,
                "clicks": 0,
                "colors": OFFER_COLORS.get(offer, OFFER_COLORS["OUTRO"]),
            }
        d["offers"][offer]["spend"] += ad["spend"]
        d["offers"][offer]["conversations"] += ad["conversations"]
        d["offers"][offer]["clicks"] += ad["clicks"]

    # Calcular CPA e ordenar ofertas por conversas
    for city, d in city_data.items():
        d["cpa"] = round(d["spend"] / d["conversations"], 2) if d["conversations"] else 0.0
        d["active_ads"] = sum(1 for a in d["ads"] if a["spend"] > 0)

        # Top 5 criativos por conversas
        d["top_ads"] = sorted(d["ads"], key=lambda x: x["conversations"], reverse=True)[:5]

        # Ordenar ofertas
        offers_list = list(d["offers"].values())
        for o in offers_list:
            o["cpa"] = round(o["spend"] / o["conversations"], 2) if o["conversations"] else 0.0
        d["offers_list"] = sorted(offers_list, key=lambda x: x["conversations"], reverse=True)

    return city_data


def format_period(start: str, end: str) -> str:
    """Formata período em português. Ex: '07 abr — 13 abr 2026'"""
    months = {
        1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
        7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
    }
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    return f"{s.day:02d} {months[s.month]} \u2014 {e.day:02d} {months[e.month]} {e.year}"


# ---------------------------------------------------------------------------
# Dashboard data assembly
# ---------------------------------------------------------------------------

def build_dashboard_data(weekly_data: dict) -> dict:
    ads = weekly_data["ads"]
    totals = weekly_data["totals"]
    period = weekly_data["period"]

    city_data = group_by_city(ads)

    # Ordenar cidades na ordem canônica
    cities_ordered = []
    for city in CITY_ORDER:
        if city in city_data:
            cities_ordered.append(city_data[city])
    # Adicionar cidades não previstas
    for city, data in city_data.items():
        if city not in CITY_ORDER:
            cities_ordered.append(data)

    return {
        "period_label": format_period(period["start"], period["end"]),
        "period": period,
        "generated_at": weekly_data.get("generated_at", ""),
        "totals": totals,
        "cities": cities_ordered,
        "offer_colors": OFFER_COLORS,
    }


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(dashboard_data: dict, template_path: str) -> str:
    """Injeta dados JSON no template HTML."""
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Serializar dados como JS
    data_json = json.dumps(dashboard_data, ensure_ascii=False, indent=2)

    # Substituir placeholder
    html = template.replace("__DASHBOARD_DATA__", data_json)
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Ótica Alê Eyewear — Geração do Dashboard")
    print("=" * 60)

    data_path = "data/weekly_data.json"
    template_path = "template/dashboard_template.html"
    output_path = "output/dashboard.html"

    # Verificar arquivos necessários
    if not Path(data_path).exists():
        print(f"\nERRO: {data_path} não encontrado.")
        print("Execute primeiro: python fetch_meta_data.py")
        return

    if not Path(template_path).exists():
        print(f"\nERRO: {template_path} não encontrado.")
        return

    print(f"\nLendo dados de: {data_path}")
    with open(data_path, "r", encoding="utf-8") as f:
        weekly_data = json.load(f)

    period = weekly_data["period"]
    totals = weekly_data["totals"]
    print(f"Periodo: {period['start']} a {period['end']}")
    print(f"Anúncios: {totals['ads_count']} ({totals['active_ads']} ativos)")
    print(f"Investimento: R$ {totals['spend']:,.2f}")
    print(f"Conversas: {totals['conversations']}")

    print("\nAgrupando dados por cidade...")
    dashboard_data = build_dashboard_data(weekly_data)

    cities_found = [c["city"] for c in dashboard_data["cities"]]
    print(f"Cidades encontradas: {', '.join(cities_found)}")

    print("\nGerando HTML...")
    os.makedirs("output", exist_ok=True)
    html = generate_html(dashboard_data, template_path)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = Path(output_path).stat().st_size / 1024
    print(f"\n✓ Dashboard gerado: {output_path} ({size_kb:.1f} KB)")
    print(f"\nAbra no navegador:")
    print(f"  file://{Path(output_path).resolve()}")


if __name__ == "__main__":
    main()
