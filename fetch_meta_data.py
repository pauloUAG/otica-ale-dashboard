"""
fetch_meta_data.py
Coleta dados de performance dos anúncios da Ótica Alê Eyewear via Meta Marketing API
e salva em data/weekly_data.json para geração do dashboard.
"""

import json
import os
import sys
import io
from datetime import datetime, timedelta, date

import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")
API_VERSION = os.getenv("META_API_VERSION", "v22.0")
GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_yesterday_range() -> tuple[date, date]:
    """Retorna (ontem, ontem) para busca diária automática."""
    yesterday = date.today() - timedelta(days=1)
    return yesterday, yesterday


# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------

CITIES = ["BELÉM", "BELEM", "ANANINDEUA", "CASTANHAL", "CAPANEMA", "MARITUBA"]

OFFERS = [
    ("MULTIFOCAL",      "MULTIFOCAL"),
    ("EXAME DE VISTA",  "EXAME DE VISTA"),
    ("EXAME",           "EXAME DE VISTA"),
    ("LIGAÇÃO",         "LIGAÇÃO"),
    ("LIGACAO",         "LIGAÇÃO"),
    ("EM DOBRO",        "EM DOBRO"),
    ("DOBRO",           "EM DOBRO"),
    ("DIA DA MULHER",   "DIA DA MULHER"),
    ("R$1,00",          "R$ 1,00"),
    ("R$1",             "R$ 1,00"),
    ("AQUECIMENTO",     "AQUECIMENTO"),
]

HOOKS = [
    "COMO QUE UMA ARMAÇÃO",
    "NÃO É SORTE",
    "MUITA GENTE",
    "SE VOCÊ ESTÁ VENDO",
    "SER CARO",
    "DOIS ÓCULOS",
    "ALERTA URGENTE",
    "VALOR MEGA ACESSÍVEL",
    "ESSA ARMAÇÃO",
    "SE ESTE VÍDEO",
    "DIA DA MULHER",
    "PAGUE UM LEVE DOIS",
    "VOCÊ PRECISANDO",
    "ÓCULOS EM DOBRO",
    "EXAME DE VISTA",
    "DOBRO",
    "MULTIFOCAL",
    "LIGAÇÃO",
]


def extract_city(ad_name: str) -> str:
    name = ad_name.upper()
    for city in CITIES:
        if city in name:
            return "BELÉM" if city == "BELEM" else city
    return "OUTRO"


def extract_offer(ad_name: str) -> str:
    name = ad_name.upper()
    for keyword, label in OFFERS:
        if keyword in name:
            return label
    return "OUTRO"


def extract_hook(ad_name: str) -> str:
    name = ad_name.upper()
    for hook in HOOKS:
        if hook in name:
            return hook
    return "OUTRO"


# ---------------------------------------------------------------------------
# Meta API
# ---------------------------------------------------------------------------

def fetch_all_insights(since: str, until: str, time_increment: int | None = None) -> list[dict]:
    """Busca todos os insights a nível de anúncio com paginação."""
    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        print("ERRO: META_ACCESS_TOKEN e META_AD_ACCOUNT_ID precisam estar no .env", file=sys.stderr)
        sys.exit(1)

    fields = ",".join([
        "ad_name",
        "ad_id",
        "campaign_name",
        "adset_name",
        "spend",
        "actions",
        "cost_per_action_type",
        "clicks",
        "cpc",
        "ctr",
        "reach",
        "impressions",
        "frequency",
        "cpp",
    ])

    url = f"{GRAPH_BASE}/act_{AD_ACCOUNT_ID}/insights"
    params = {
        "level": "ad",
        "fields": fields,
        "time_range": json.dumps({"since": since, "until": until}),
        "filtering": json.dumps([{
            "field": "spend",
            "operator": "GREATER_THAN",
            "value": "0"
        }]),
        "limit": 500,
        "access_token": ACCESS_TOKEN,
    }
    if time_increment:
        params["time_increment"] = str(time_increment)

    all_data = []
    page = 1
    while url:
        print(f"  Buscando página {page}...", end=" ", flush=True)
        resp = requests.get(url, params=params, timeout=120)

        if resp.status_code != 200:
            print(f"\nERRO: Meta API retornou {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
            sys.exit(1)

        body = resp.json()
        data = body.get("data", [])
        all_data.extend(data)
        print(f"{len(data)} registros")

        # Próxima página (next_url já contém todos os parâmetros)
        url = body.get("paging", {}).get("next")
        params = {}
        page += 1

    return all_data


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def get_action_value(actions: list[dict] | None, action_type: str) -> float:
    if not actions:
        return 0.0
    for a in actions:
        if a.get("action_type") == action_type:
            return float(a.get("value", 0))
    return 0.0


def extract_conversations(row: dict) -> int:
    """Extrai 'Conversas por mensagem iniciadas' — mesma métrica do Meta Ads Manager."""
    actions = row.get("actions") or []
    return int(get_action_value(actions, "onsite_conversion.messaging_conversation_started_7d"))


def process_row(row: dict) -> dict:
    """Transforma uma linha da API em um anúncio processado."""
    ad_name = row.get("ad_name", "").strip()
    spend = float(row.get("spend", 0) or 0)
    clicks = float(row.get("clicks", 0) or 0)
    impressions = float(row.get("impressions", 0) or 0)
    reach = float(row.get("reach", 0) or 0)

    try:
        ctr = float(row.get("ctr", 0) or 0)
    except (ValueError, TypeError):
        ctr = clicks / impressions if impressions else 0.0

    try:
        cpc = float(row.get("cpc", 0) or 0)
    except (ValueError, TypeError):
        cpc = spend / clicks if clicks else 0.0

    conversations = extract_conversations(row)
    cpa = spend / conversations if conversations else 0.0

    # Visitas ao perfil do Instagram (se disponível)
    actions = row.get("actions") or []
    profile_visits = int(get_action_value(actions, "page_engagement"))

    city = extract_city(ad_name)
    offer = extract_offer(ad_name)
    hook = extract_hook(ad_name)

    return {
        "name": ad_name,
        "ad_id": row.get("ad_id", ""),
        "city": city,
        "offer": offer,
        "hook": hook,
        "status": "ATIVO",
        "spend": round(spend, 2),
        "conversations": conversations,
        "cpa": round(cpa, 2),
        "clicks": int(clicks),
        "ctr": round(ctr / 100 if ctr > 1 else ctr, 4),  # normaliza para decimal
        "reach": int(reach),
        "impressions": int(impressions),
        "profile_visits": profile_visits,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def build_totals(ads: list[dict]) -> dict:
    total_spend = sum(a["spend"] for a in ads)
    total_conversations = sum(a["conversations"] for a in ads)
    total_reach = sum(a["reach"] for a in ads)
    total_impressions = sum(a["impressions"] for a in ads)
    total_clicks = sum(a["clicks"] for a in ads)
    total_profile_visits = sum(a["profile_visits"] for a in ads)

    cpa = total_spend / total_conversations if total_conversations else 0.0
    active_ads = sum(1 for a in ads if a["conversations"] > 0 or a["spend"] > 0)

    return {
        "spend": round(total_spend, 2),
        "conversations": total_conversations,
        "cpa": round(cpa, 2),
        "reach": total_reach,
        "impressions": total_impressions,
        "clicks": total_clicks,
        "profile_visits": total_profile_visits,
        "ads_count": len(ads),
        "active_ads": active_ads,
    }


# ---------------------------------------------------------------------------
# History update
# ---------------------------------------------------------------------------

def update_history_json(since: str, until: str, daily_ads: list[dict]):
    """Acrescenta registros diários ao history.json, evitando duplicatas."""
    from pathlib import Path
    history_path = "data/history.json"
    if Path(history_path).exists():
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = {"last_updated": "", "period": {"start": since, "end": until}, "records": []}

    # Remove registros existentes para o período (evita duplicatas em re-runs)
    history["records"] = [r for r in history["records"] if not (since <= r.get("date", "") <= until)]

    history["records"].extend(daily_ads)
    history["records"].sort(key=lambda r: r.get("date", ""))

    all_dates = [r["date"] for r in history["records"] if r.get("date")]
    if all_dates:
        history["period"]["start"] = min(all_dates)
        history["period"]["end"]   = max(all_dates)

    history["last_updated"] = datetime.now().isoformat()

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"✓ history.json atualizado: {len(daily_ads)} registros de {since} a {until}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Ótica Alê Eyewear — Coleta de Dados Meta Ads")
    print("=" * 60)

    yesterday, _ = get_yesterday_range()
    since = yesterday.strftime("%Y-%m-%d")
    until = yesterday.strftime("%Y-%m-%d")

    # Permite override via argumentos
    if len(sys.argv) == 3:
        since = sys.argv[1]
        until = sys.argv[2]

    print(f"\nPeriodo: {since} a {until}")
    print(f"Conta: act_{AD_ACCOUNT_ID}")
    print(f"API: {API_VERSION}\n")

    print("Buscando insights da API do Meta...")
    raw_rows = fetch_all_insights(since, until)
    print(f"\nTotal de registros brutos: {len(raw_rows)}")

    print("\nProcessando dados...")
    ads = [process_row(r) for r in raw_rows]
    ads = [a for a in ads if a["spend"] > 0]  # remove zerados

    totals = build_totals(ads)

    output = {
        "period": {"start": since, "end": until},
        "generated_at": datetime.now().isoformat(),
        "ad_account_id": AD_ACCOUNT_ID,
        "totals": totals,
        "ads": ads,
    }

    # Salvar dados da semana atual
    os.makedirs("data", exist_ok=True)
    current_path = "data/weekly_data.json"
    with open(current_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Salvar cópia histórica
    historical_path = f"data/{until}.json"
    with open(historical_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Dados salvos em: {current_path}")
    print(f"✓ Cópia histórica: {historical_path}")
    print(f"\nResumo:")
    print(f"  Anúncios processados: {totals['ads_count']}")
    print(f"  Anúncios ativos:      {totals['active_ads']}")
    print(f"  Investimento total:   R$ {totals['spend']:,.2f}")
    print(f"  Conversas:            {totals['conversations']}")
    print(f"  CPA médio:            R$ {totals['cpa']:,.2f}")

    # Buscar dados diários em blocos de 30 dias e atualizar history.json
    print("\nBuscando dados diários para o histórico (blocos de 30 dias)...")
    chunk_start = date.fromisoformat(since)
    chunk_end_limit = date.fromisoformat(until)
    all_daily_ads = []
    while chunk_start <= chunk_end_limit:
        chunk_end = min(chunk_start + timedelta(days=29), chunk_end_limit)
        cs = chunk_start.strftime("%Y-%m-%d")
        ce = chunk_end.strftime("%Y-%m-%d")
        print(f"  Bloco: {cs} a {ce}")
        raw_daily = fetch_all_insights(cs, ce, time_increment=1)
        for row in raw_daily:
            d = row.get("date_start", "")
            ad = process_row(row)
            if ad["spend"] > 0 and d:
                ad["date"] = d
                all_daily_ads.append(ad)
        chunk_start = chunk_end + timedelta(days=1)
    update_history_json(since, until, all_daily_ads)

    print(f"\nPróximo passo: python generate_dashboard.py")


if __name__ == "__main__":
    main()
