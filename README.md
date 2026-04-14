# Ótica Alê Eyewear — Dashboard Semanal Meta Ads

Dashboard HTML estático gerado automaticamente toda segunda-feira com dados da semana anterior via Meta Marketing API.

## Estrutura

```
otica-ale-dashboard/
├── fetch_meta_data.py        # Coleta dados da API do Meta → data/weekly_data.json
├── generate_dashboard.py     # Lê JSON → gera output/dashboard.html
├── template/
│   └── dashboard_template.html
├── data/
│   ├── weekly_data.json      # Dados da semana atual
│   └── YYYY-MM-DD.json       # Histórico por semana
├── output/
│   └── dashboard.html        # Dashboard final (abrir no browser)
├── .github/workflows/
│   └── update.yml            # Automação via GitHub Actions
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

### 1. Configurar credenciais

```bash
cp .env.example .env
# Edite .env com seu token e ID de conta
```

Variáveis necessárias:
- `META_ACCESS_TOKEN` — System User Token (nunca expira)
- `META_AD_ACCOUNT_ID` — ID da conta sem o prefixo `act_`
- `META_API_VERSION` — Ex: `v22.0`

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Rodar manualmente

```bash
# Coleta dados da semana anterior automaticamente
python fetch_meta_data.py

# Para período específico
python fetch_meta_data.py 2026-04-07 2026-04-13

# Gera o dashboard
python generate_dashboard.py

# Abre no browser (Windows)
start output/dashboard.html
```

## Automação — GitHub Actions

1. Configure os secrets no repositório:
   - `META_ACCESS_TOKEN`
   - `META_AD_ACCOUNT_ID`

2. O workflow `.github/workflows/update.yml` roda toda segunda-feira às 8h BRT (11h UTC), coleta os dados, gera o HTML e faz commit automático.

3. Você também pode acionar manualmente pela aba **Actions** no GitHub.

## Automação — Cron (Linux/Mac)

```bash
crontab -e
# Adicione:
0 8 * * 1 cd /caminho/para/otica-ale-dashboard && python fetch_meta_data.py && python generate_dashboard.py
```

## Dashboard

O HTML gerado é totalmente estático e auto-contido:

- **KPIs gerais**: Investimento, Conversas, CPA, Alcance, Visitas ao perfil, Anúncios
- **Seletor de cidade**: Belém, Ananindeua, Castanhal, Capanema, Marituba
- **Por cidade**: Métricas, gráfico de ofertas, tabela com saúde do CPA
- **Top 5 criativos**: Cards com drag & drop para upload de thumbnail do Reels

As imagens de thumbnail são carregadas apenas no lado do cliente (base64 no DOM) e não persistem entre reloads.

## Nomes de anúncios

O sistema extrai cidade, oferta e hook a partir do nome do anúncio. Padrão esperado:

```
Ad 00 - REELS - R$1,00 - BELÉM - COMO QUE UMA ARMAÇÃO
Ad 00 - REELS - MULTIFOCAL - ANANINDEUA - SER CARO
ADVANTAGE - 00 - REELS - EM DOBRO - CAPANEMA - ÓCULOS EM DOBRO
```

Se a nomenclatura mudar, atualize as funções `extract_city`, `extract_offer` e `extract_hook` em `fetch_meta_data.py`.
