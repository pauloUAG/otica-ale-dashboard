"""
parse_csv.py
Processa CSVs exportados do Meta Ads Manager.

Suporta dois formatos:
  - Agregado (sem detalhamento diário): gera data/weekly_data.json
  - Diário   (com coluna "Dia"):        acumula em data/history.json

Uso:
    python parse_csv.py arquivo.csv
    python parse_csv.py arquivo.csv --mode history   # força acúmulo diário
    python parse_csv.py arquivo.csv --mode weekly    # força agregado
"""

import csv
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Colunas esperadas ────────────────────────────────────────────────────────
COL_MAP = {
    "date": [
        "Dia", "Day", "Data",
    ],
    "inicio_relatorio": [
        "Início dos relatórios", "InÃ­cio dos relatÃ³rios", "Inicio dos relatorios",
    ],
    "fim_relatorio": [
        "Encerramento dos relatórios", "Encerramento dos relatÃ³rios",
    ],
    "ad_name": [
        "Nome do anúncio", "Nome do anÃºncio", "Nome do anuncio",
    ],
    "status": [
        "Veiculação de anúncio", "VeiculaÃ§Ã£o de anÃºncio",
    ],
    "spend": [
        "Valor usado (BRL)", "Valor usado (R$)",
    ],
    "conversations": [
        "Conversas por mensagem iniciadas", "Resultados",
    ],
    "link_clicks": [
        "Cliques no link",
    ],
    "ctr": [
        "CTR (taxa de cliques no link)",
    ],
    "reach": [
        "Alcance",
    ],
    "impressions": [
        "Impressões", "ImpressÃµes", "Impressoes",
    ],
    "profile_visits": [
        "Visitas ao perfil do Instagram",
    ],
}

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
    ("AQUECIMENTO",     "AQUECIMENTO"),
    ("R$1,00",          "R$ 1,00"),
    ("R$1",             "R$ 1,00"),
    ("VAGA",            "VAGA"),
    ("ENGAJAMENTO",     "ENGAJAMENTO"),
]

HOOKS = [
    "COMO QUE UMA ARMAÇÃO", "COMO QUE UMA ARMAÃÃO",
    "NÃO É SORTE", "NÃO Ã SORTE",
    "MUITA GENTE",
    "SE VOCÊ ESTÁ VENDO", "SE VOCÃ ESTÃ VENDO",
    "SER CARO",
    "DOIS ÓCULOS", "DOIS ÃCULOS",
    "ALERTA URGENTE",
    "VALOR MEGA ACESSÍVEL", "VALOR MEGA ACESSÃVEL",
    "ESSA ARMAÇÃO", "ESSA ARMAÃÃO",
    "SE ESTE VÍDEO", "SE ESTE VÃDEO",
    "DIA DA MULHER",
    "PAGUE UM LEVE DOIS",
    "VOCÊ PRECISANDO", "VOCÃ PRECISANDO",
    "ÓCULOS EM DOBRO", "ÃCULOS EM DOBRO",
    "NUNCA FEZ ISSO",
    "AQUELA PROMO",
    "IMPOSSÍVEL ACREDITAR", "IMPOSSÃVEL ACREDITAR",
    "GOLPE", "ESSA OFERTA", "POR UM REAL",
    "CANSOU", "OLHA QUE LINDO", "MOEDA", "CAIXINHA",
    "CORRE PARA GARANTIR",
    "NÃO É SORTE É OPORTUNIDADE",
    "INFLUENCER", "MAIS DE 40",
    "RESULTADO EM DOBRO",
    "OLHA SÓ ISSO", "OLHA SÃ ISSO",
    "SEU ÓCULOS VALE DOIS", "SEU ÃCULOS VALE DOIS",
    "SERÁ", "SERÃ",
]

HOOK_CLEAN = {
    "ARMAÃÃO": "ARMAÇÃO", "ÃCULOS": "ÓCULOS", "VOCÃ": "VOCÊ",
    "ESTÃ": "ESTÁ", "VÃDEO": "VÍDEO", "ACESSÃVEL": "ACESSÍVEL",
    "IMPOSSÃVEL": "IMPOSSÍVEL", "SERÃ": "SERÁ", "SÃ": "SÓ",
    "NÃO Ã": "NÃO É",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def fix_encoding(text: str) -> str:
    try:
        return text.encode("latin-1").decode("utf-8")
    except Exception:
        return text


def clean_hook(hook: str) -> str:
    for bad, good in HOOK_CLEAN.items():
        hook = hook.replace(bad, good)
    return hook


def extract_city(name: str) -> str:
    u = name.upper()
    for c in CITIES:
        if c in u:
            return "BELÉM" if c == "BELEM" else c
    return "OUTRO"


def extract_offer(name: str) -> str:
    u = name.upper()
    for kw, label in OFFERS:
        if kw in u:
            return label
    return "OUTRO"


def extract_hook(name: str) -> str:
    u = name.upper()
    for h in HOOKS:
        if h in u:
            return clean_hook(h)
    return "OUTRO"


def safe_float(val) -> float:
    if not val or str(val).strip() == "":
        return 0.0
    try:
        return float(str(val).replace(",", "."))
    except ValueError:
        return 0.0


def safe_int(val) -> int:
    return int(safe_float(val))


def find_col(headers: list, key: str):
    candidates = COL_MAP.get(key, [])
    for h in headers:
        h_s = h.strip()
        if h_s in candidates or fix_encoding(h_s) in candidates:
            return h_s
    return None


# ── Leitura do CSV ───────────────────────────────────────────────────────────

def read_csv(path: str) -> list:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, encoding=enc, newline="") as f:
                content = f.read()
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
            if rows:
                print(f"  Encoding: {enc} | {len(rows)} linhas")
                return rows
        except Exception:
            continue
    raise ValueError(f"Não foi possível ler: {path}")


# ── Processar linha do CSV ───────────────────────────────────────────────────

def parse_row(row: dict, cols: dict) -> dict | None:
    ad_name_raw = row.get(cols["ad_name"], "").strip() if cols["ad_name"] else ""
    if not ad_name_raw:
        return None

    ad_name = fix_encoding(ad_name_raw)
    spend   = safe_float(row.get(cols["spend"], "") if cols["spend"] else "")
    conv    = safe_int(row.get(cols["conversations"], "") if cols["conversations"] else "")
    clicks  = safe_int(row.get(cols["link_clicks"], "") if cols["link_clicks"] else "")
    ctr     = safe_float(row.get(cols["ctr"], "") if cols["ctr"] else "")
    reach   = safe_int(row.get(cols["reach"], "") if cols["reach"] else "")
    imp     = safe_int(row.get(cols["impressions"], "") if cols["impressions"] else "")
    pv      = safe_int(row.get(cols["profile_visits"], "") if cols["profile_visits"] else "")
    status  = row.get(cols["status"], "").strip() if cols["status"] else ""
    # "Dia" column preferred; fall back to "Início dos relatórios" (single-day period rows)
    if cols["date"]:
        date = row.get(cols["date"], "").strip()
    elif cols["inicio_relatorio"]:
        date = row.get(cols["inicio_relatorio"], "").strip()
    else:
        date = ""

    if spend == 0 and conv == 0 and clicks == 0:
        return None

    return {
        "date":           date,
        "name":           ad_name,
        "city":           extract_city(ad_name),
        "offer":          extract_offer(ad_name),
        "hook":           extract_hook(ad_name),
        "status":         "ATIVO" if "active" in status.lower() else "INATIVO",
        "spend":          round(spend, 2),
        "conversations":  conv,
        "clicks":         clicks,
        "ctr":            round(ctr / 100 if ctr > 1 else ctr, 4),
        "reach":          reach,
        "impressions":    imp,
        "profile_visits": pv,
    }


# ── Agregação ────────────────────────────────────────────────────────────────

def aggregate(records: list) -> list:
    """Agrega registros pelo nome do anúncio, somando métricas."""
    agg = {}
    for r in records:
        key = r["name"]
        if key not in agg:
            agg[key] = {**r, "ctr_sum": r["ctr"], "ctr_count": 1 if r["ctr"] else 0}
        else:
            d = agg[key]
            d["spend"]          += r["spend"]
            d["conversations"]  += r["conversations"]
            d["clicks"]         += r["clicks"]
            d["reach"]          += r["reach"]
            d["impressions"]    += r["impressions"]
            d["profile_visits"] += r["profile_visits"]
            d["ctr_sum"]        += r["ctr"]
            d["ctr_count"]      += 1 if r["ctr"] else 0
            if r["status"] == "ATIVO":
                d["status"] = "ATIVO"

    result = []
    for d in agg.values():
        d["ctr"] = round(d["ctr_sum"] / d["ctr_count"], 4) if d["ctr_count"] else 0.0
        sp, cv = d["spend"], d["conversations"]
        d["cpa"] = round(sp / cv, 2) if cv else 0.0
        d.pop("ctr_sum", None)
        d.pop("ctr_count", None)
        d.pop("date", None)
        result.append(d)
    return result


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
        "active_ads":     sum(1 for a in ads if a["status"] == "ATIVO"),
    }


# ── Modo AGREGADO → weekly_data.json ────────────────────────────────────────

def process_weekly(rows: list, cols: dict, period_start: str, period_end: str) -> dict:
    records = [r for r in (parse_row(row, cols) for row in rows) if r]
    ads = aggregate(records)
    return {
        "period":       {"start": period_start, "end": period_end},
        "generated_at": datetime.now().isoformat(),
        "source":       "csv",
        "totals":       build_totals(ads),
        "ads":          ads,
    }


# ── Modo DIÁRIO → history.json ───────────────────────────────────────────────

def process_history(rows: list, cols: dict) -> list:
    """Retorna lista de registros diários {date, name, city, offer, hook, ...}"""
    records = []
    for row in rows:
        r = parse_row(row, cols)
        if r and r.get("date"):
            r["cpa"] = round(r["spend"] / r["conversations"], 2) if r["conversations"] else 0.0
            records.append(r)
    return records


def merge_history(existing: list, new_records: list) -> list:
    """Mescla novos registros no histórico, evitando duplicatas por (date, name)."""
    existing_keys = {(r["date"], r["name"]) for r in existing}
    added = 0
    for r in new_records:
        key = (r["date"], r["name"])
        if key not in existing_keys:
            existing.append(r)
            existing_keys.add(key)
            added += 1
    print(f"  Novos registros adicionados: {added}")
    print(f"  Total no histórico:          {len(existing)}")
    return sorted(existing, key=lambda x: x["date"])


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Ótica Alê Eyewear — Parser de CSV Meta Ads")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("\nUso: python parse_csv.py arquivo.csv [--mode weekly|history]")
        sys.exit(1)

    csv_path = sys.argv[1]
    mode_arg = None
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode_arg = sys.argv[idx + 1]

    if not Path(csv_path).exists():
        print(f"\nERRO: Arquivo não encontrado: {csv_path}")
        sys.exit(1)

    print(f"\nLendo: {csv_path}")
    rows = read_csv(csv_path)
    headers = list(rows[0].keys())
    cols = {key: find_col(headers, key) for key in COL_MAP}

    # Detectar modo automaticamente
    # Daily if has "Dia" column OR if each row has its own single-day period (Início = Encerramento)
    is_daily = bool(cols["date"]) or bool(cols["inicio_relatorio"])
    if mode_arg:
        is_daily = (mode_arg == "history")

    print(f"  Modo: {'DIÁRIO (history.json)' if is_daily else 'AGREGADO (weekly_data.json)'}")

    os.makedirs("data", exist_ok=True)

    if is_daily:
        # ── Modo diário ──────────────────────────────────────────────────────
        new_records = process_history(rows, cols)
        print(f"  Registros lidos: {len(new_records)}")

        history_path = "data/history.json"
        if Path(history_path).exists():
            with open(history_path, encoding="utf-8") as f:
                existing = json.load(f).get("records", [])
            print(f"  Histórico existente: {len(existing)} registros")
        else:
            existing = []
            print("  Histórico: novo arquivo")

        merged = merge_history(existing, new_records)

        dates = [r["date"] for r in merged if r["date"]]
        history_out = {
            "last_updated": datetime.now().isoformat(),
            "period":       {"start": min(dates) if dates else "", "end": max(dates) if dates else ""},
            "records":      merged,
        }

        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history_out, f, ensure_ascii=False, indent=2)

        print(f"\n Histórico salvo: {history_path}")
        print(f"  Período: {history_out['period']['start']} a {history_out['period']['end']}")
        print(f"\nPróximo passo: python generate_dashboard.py --source history")

    else:
        # ── Modo agregado ────────────────────────────────────────────────────
        period_start, period_end = "", ""
        if cols["inicio_relatorio"]:
            dates = [r[cols["inicio_relatorio"]].strip() for r in rows if r.get(cols["inicio_relatorio"])]
            period_start = min((d for d in dates if d), default="")
        if cols["fim_relatorio"]:
            dates = [r[cols["fim_relatorio"]].strip() for r in rows if r.get(cols["fim_relatorio"])]
            period_end = max((d for d in dates if d), default="")

        data = process_weekly(rows, cols, period_start, period_end)
        t = data["totals"]

        out_path = "data/weekly_data.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\nResumo:")
        print(f"  Período:            {period_start} a {period_end}")
        print(f"  Anúncios únicos:    {t['ads_count']}")
        print(f"  Investimento:       R$ {t['spend']:,.2f}")
        print(f"  Conversas:          {t['conversations']}")
        print(f"  CPA médio:          R$ {t['cpa']:,.2f}")
        print(f"  Visitas ao perfil:  {t['profile_visits']}")
        print(f"\n Salvo: {out_path}")
        print(f"Próximo passo: python generate_dashboard.py")


if __name__ == "__main__":
    main()
