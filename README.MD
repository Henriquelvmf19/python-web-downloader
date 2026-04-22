# 🖼️ Image Scraper

> Ferramenta de scraping de imagens para sites modernos renderizados com JavaScript — React, Vite, Next.js, SvelteKit e outros frameworks SPA/SSR.

---

## ✨ Funcionalidades

- **Renderização real via browser** — usa Playwright (Chromium headless) para executar o JavaScript da página antes de coletar as imagens, garantindo que o conteúdo dinâmico seja carregado
- **Scroll automático** — percorre a página para disparar o carregamento lazy de imagens
- **Interceptação de rede** — captura imagens diretamente das respostas HTTP, além da extração via DOM
- **Extração abrangente** — coleta `<img src>`, `<img srcset>`, `<source srcset>` (picture element) e `background-image` via CSS
- **Download paralelo** — suporte a múltiplos workers simultâneos para máxima velocidade
- **Filtro por tamanho** — opção para ignorar imagens abaixo de um tamanho mínimo (ideal para ignorar ícones e pixels de rastreamento)
- **Relatório detalhado** — exibe total baixado, falhas, tamanho total e pasta de destino
- **Nomes de arquivo seguros** — gera nomes únicos baseados na URL, preservando a extensão original

---

## 📋 Requisitos

- Python **3.11+**
- pip

---

## 🚀 Instalação

### 1. Clone ou baixe o script

```bash
# Se tiver o repositório clonado
cd image-scraper

# Ou simplesmente coloque o image_scraper.py em uma pasta de sua escolha
```

### 2. Instale as dependências Python

```bash
python3 -m venv .venv && source .venv/bin/activate #específico para seu shell (bash, fish, zsh...)
pip install playwright httpx rich
```

### 3. Instale os browsers do Playwright

```bash
playwright install chromium
```

> Isso faz o download do Chromium (~150 MB). Precisa ser feito apenas uma vez.

---

## 💡 Uso

### Comando básico

```bash
python image_scraper.py https://exemplo.com.br
```

As imagens serão salvas na pasta `./images/` por padrão.

---

### Opções disponíveis

| Opção | Padrão | Descrição |
|---|---|---|
| `url` | *(obrigatório)* | URL do site alvo |
| `-o`, `--output` | `./images` | Pasta de destino para as imagens |
| `-c`, `--concurrency` | `8` | Número de downloads simultâneos |
| `--no-scroll` | `False` | Desativa o scroll automático (mais rápido, pode perder imagens lazy) |
| `--timeout` | `15` | Tempo máximo de carregamento da página (em segundos) |
| `--min-size` | `0` | Ignora imagens menores que N bytes (ex: `--min-size 5000` ignora imagens < 5 KB) |

---

### Exemplos

```bash
# Salvar em pasta personalizada
python image_scraper.py https://exemplo.com -o ./exemplo_imagens

# Site pesado — aumentar timeout e desativar scroll
python image_scraper.py https://exemplo.com --timeout 30 --no-scroll

# Download agressivo com 16 workers paralelos
python image_scraper.py https://exemplo.com -c 16

# Ignorar ícones e imagens muito pequenas (< 10 KB)
python image_scraper.py https://exemplo.com --min-size 10000

# Combinando opções
python image_scraper.py https://loja.exemplo.com -o ./produtos -c 12 --timeout 25 --min-size 5000
```

---

## 📂 Estrutura do output

```
images/
├── hero_banner_a1b2c3d4.jpg
├── logo_e5f6g7h8.png
├── produto_frango_i9j0k1l2.webp
├── galeria_01_m3n4o5p6.jpg
└── ...
```

Cada arquivo recebe um sufixo de hash MD5 (8 caracteres) para garantir nomes únicos, mesmo que duas imagens tenham o mesmo nome de arquivo na URL.

---

## 🔍 Como o scraper funciona

```
URL fornecida
     │
     ▼
┌─────────────────────────────┐
│  Playwright (Chromium)      │
│  • Carrega a página         │
│  • Executa o JavaScript     │
│  • Intercepta respostas     │
│    de rede com imagens      │
│  • Faz scroll automático    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Extração do DOM            │
│  • <img src>                │
│  • <img srcset>             │
│  • <source srcset>          │
│  • background-image (CSS)   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Download paralelo          │
│  (httpx + asyncio)          │
│  • N workers simultâneos    │
│  • Retry automático         │
│  • Extensão correta         │
└──────────────┬──────────────┘
               │
               ▼
         📁 ./images/
```

---

## ⚠️ Casos especiais e soluções

### Site com autenticação (login)

O Playwright pode ser configurado para reutilizar uma sessão autenticada. Salve o estado do navegador após o login:

```python
# Em um script separado, faça o login manualmente e salve o estado:
context.storage_state(path="auth.json")

# No scraper, carregue o estado:
context = await browser.new_context(storage_state="auth.json")
```

### Site com Cloudflare / anti-bot

Instale o plugin de stealth:

```bash
pip install playwright-stealth
```

```python
from playwright_stealth import stealth_async
await stealth_async(page)
```

### Imagens carregam via API (JSON)

Se as imagens vêm de uma API REST, abra o DevTools → aba **Network** → filtre por **Fetch/XHR** e chame o endpoint diretamente com `httpx`, sem precisar do browser.

---

## 📦 Dependências

| Pacote | Uso |
|---|---|
| `playwright` | Controle do browser headless (Chromium) |
| `httpx` | Download assíncrono das imagens |
| `rich` | Interface colorida no terminal com progress bar |

---

## 📄 Licença

MIT — uso livre para fins pessoais e comerciais.