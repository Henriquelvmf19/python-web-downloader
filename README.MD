# 🖼️ Image Scraper & 🌐 Site Cloner

> Ferramentas de scraping para sites modernos renderizados com JavaScript — React, Vite, Next.js, SvelteKit e outros frameworks SPA/SSR.

---

## ✨ Funcionalidades

### 🖼️ Image Scraper (`scrape_images.py`)

- **Renderização real via browser** — usa Playwright (Chromium headless) para executar o JavaScript da página antes de coletar as imagens, garantindo que o conteúdo dinâmico seja carregado
- **Scroll automático** — percorre a página para disparar o carregamento lazy de imagens
- **Interceptação de rede** — captura imagens diretamente das respostas HTTP, além da extração via DOM
- **Extração abrangente** — coleta `<img src>`, `<img srcset>`, `<source srcset>` (picture element) e `background-image` via CSS
- **Download paralelo** — suporte a múltiplos workers simultâneos para máxima velocidade
- **Filtro por tamanho** — opção para ignorar imagens abaixo de um tamanho mínimo (ideal para ignorar ícones e pixels de rastreamento)
- **Relatório detalhado** — exibe total baixado, falhas, tamanho total e pasta de destino
- **Nomes de arquivo seguros** — gera nomes únicos baseados na URL, preservando a extensão original

### 🌐 Site Cloner (`site_cloner.py`) — **v2 (Framework-Aware)**

- **Clone estático de alta fidelidade** — Produz uma versão HTML pura do site que funciona offline sem erros de console ou travamentos de hidratação.
- **Detecção de Framework** — Identifica automaticamente pilhas como Next.js, React, Vite, Nuxt e Angular para aplicar estratégias de limpeza específicas.
- **Remoção de Hydration Scripts** — Remove scripts de hidratação e payloads RSC (em frameworks SPA) que costumam quebrar sites offline (erros de WebSocket, hydration mismatches, etc.).
- **Limpeza de Artefatos** — Remove elementos específicos de frameworks (como `<next-route-announcer>`) para um HTML mais limpo.
- **Unescaping de Estilos Inline** — Processa corretamente URLs dentro de estilos inline que foram escapados como entidades HTML (`&quot;`), comum em temas Next.js.
- **Captura do DOM renderizado** — Captura o HTML final após execução total de JavaScript e animações iniciais.
- **Download de todos os assets** — Baixa imagens, CSS, fontes, vídeos e outros recursos usando interceptação de rede (cache) e scan profundo.
- **Scan profundo de CSS** — Analisa arquivos CSS baixados para encontrar fontes (`@font-face`) e imagens de fundo ocultas em arquivos externos.
- **Reescrita Robusta de Caminhos** — Garante que referências complexas (como links no Next.js JSON) sejam mapeadas para a pasta `assets/`.
- **Suporte a Localhost** — Melhorado para clonar sites rodando localmente (dev servers), tratando corretamente resoluções IPv6/IPv4.

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

# Ou simplesmente coloque os scripts em uma pasta de sua escolha
```

### 2. Instale as dependências Python

```bash
python3 -m venv .venv && source .venv/bin/activate #específico para seu shell (bash, fish, zsh...)
pip install playwright httpx rich
```

> **Nota:** Ambas as ferramentas (`scrape_images.py` e `site_cloner.py`) usam as mesmas dependências. Não é necessário instalar pacotes adicionais para o Site Cloner.

### 3. Instale os browsers do Playwright

```bash
playwright install chromium
```

> Isso faz o download do Chromium (~150 MB). Precisa ser feito apenas uma vez.

---

## 💡 Uso

### 🖼️ Image Scraper

#### Comando básico

```bash
python scrape_images.py https://exemplo.com.br
```

As imagens serão salvas na pasta `./images/` por padrão.

#### Opções disponíveis

| Opção | Padrão | Descrição |
|---|---|---|
| `url` | *(obrigatório)* | URL do site alvo |
| `-o`, `--output` | `./images` | Pasta de destino para as imagens |
| `-c`, `--concurrency` | `8` | Número de downloads simultâneos |
| `--no-scroll` | `False` | Desativa o scroll automático (mais rápido, pode perder imagens lazy) |
| `--timeout` | `15` | Tempo máximo de carregamento da página (em segundos) |
| `--min-size` | `0` | Ignora imagens menores que N bytes (ex: `--min-size 5000` ignora imagens < 5 KB) |

#### Exemplos

```bash
# Salvar em pasta personalizada
python scrape_images.py https://exemplo.com -o ./exemplo_imagens

# Site pesado — aumentar timeout e desativar scroll
python scrape_images.py https://exemplo.com --timeout 30 --no-scroll

# Download agressivo com 16 workers paralelos
python scrape_images.py https://exemplo.com -c 16

# Ignorar ícones e imagens muito pequenas (< 10 KB)
python scrape_images.py https://exemplo.com --min-size 10000

# Combinando opções
python scrape_images.py https://loja.exemplo.com -o ./produtos -c 12 --timeout 25 --min-size 5000
```

---

### 🌐 Site Cloner

#### Comando básico

```bash
python site_cloner.py https://exemplo.com.br
```

O site será clonado na pasta `./cloned_site/` por padrão, com a seguinte estrutura:

```
cloned_site/
├── index.html
└── assets/
    ├── images/
    │   ├── hero_banner_a1b2c3d4.jpg
    │   ├── logo_e5f6g7h8.png
    │   └── ...
    ├── css/
    │   ├── styles_f9a8b7c6.css
    │   └── ...
    ├── js/
    │   ├── main_d5e4f3g2.js
    │   └── ...
    ├── fonts/
    │   ├── inter_h1i2j3k4.woff2
    │   └── ...
    └── media/
        └── ...
```

Basta abrir o `index.html` em qualquer navegador para visualizar a página clonada offline.

#### Opções disponíveis

| Opção | Padrão | Descrição |
|---|---|---|
| `url` | *(obrigatório)* | URL do site alvo para clonar |
| `-o`, `--output` | `./cloned_site` | Pasta de destino para o clone |
| `-c`, `--concurrency` | `10` | Número de downloads simultâneos |
| `--no-scroll` | `False` | Desativa o scroll automático (mais rápido, pode perder conteúdo lazy) |
| `--timeout` | `30` | Tempo máximo de carregamento da página (em segundos) |

#### Exemplos

```bash
# Clonar em pasta personalizada
python site_cloner.py https://exemplo.com -o ./meu_clone

# Site pesado — aumentar timeout e desativar scroll
python site_cloner.py https://exemplo.com --timeout 60 --no-scroll

# Download agressivo com 16 workers paralelos
python site_cloner.py https://exemplo.com -c 16

# Combinando opções
python site_cloner.py https://loja.exemplo.com -o ./clone_loja -c 12 --timeout 45
```

---

## 📂 Estrutura do output

### Image Scraper

```
images/
├── hero_banner_a1b2c3d4.jpg
├── logo_e5f6g7h8.png
├── produto_frango_i9j0k1l2.webp
├── galeria_01_m3n4o5p6.jpg
└── ...
```

Cada arquivo recebe um sufixo de hash MD5 (8 caracteres) para garantir nomes únicos, mesmo que duas imagens tenham o mesmo nome de arquivo na URL.

### Site Cloner

```
cloned_site/
├── index.html          ← Página HTML com caminhos reescritos para assets locais
└── assets/
    ├── images/         ← Imagens (PNG, JPG, WebP, SVG, etc.)
    ├── css/            ← Folhas de estilo com url() reescritas
    ├── js/             ← Scripts JavaScript
    ├── fonts/          ← Fontes web (WOFF2, WOFF, TTF, etc.)
    └── media/          ← Vídeos e áudios
```

---

## 🔍 Como funciona

### Image Scraper

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

### Site Cloner

```
URL fornecida
     │
     ▼
┌──────────────────────────────────┐
│  Playwright (Chromium)           │
│  • Carrega e renderiza a página  │
│  • Intercepta TODAS as          │
│    respostas de rede (cache)     │
│  • Captura DOM renderizado       │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Detecção e Limpeza (v2)         │
│  • Detecta stack (Next, React,..)│
│  • REMOVE scripts de hidratação  │
│  • Unescape de entidades HTML    │
│  • Limpa artefatos de framework  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Coleta de Asset URLs            │
│  • CSS url(), @import           │
│  • Imagens nos estilos inline    │
│  • Assets no cache de rede       │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Download e Scan Profundo        │
│  • N workers simultâneos         │
│  • Scan de CSS para fontes       │
│  • Tratamento de localhost       │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Reescrita de Caminhos           │
│  • Mapeamento de raw strings     │
│  • Reescrita de URLs no JSON     │
│  • Caminhos relativos locais     │
└──────────────┬───────────────────┘
               │
               ▼
    📁 ./cloned_site/
    ├── index.html (Pure Static)
    └── assets/
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

### Site Cloner — O que esperar do clone

O Site Cloner v2 foca em **fidelidade visual absoluta** e **estabilidade offline**. Como ele remove scripts de hidratação para evitar erros:

- **O que funciona:** Todos os layouts, estilos, cores, fontes, imagens e **animações CSS** (keyframes, transições, hover effects).
- **O que NÃO funciona:** Interatividade complexa baseada em JS (menus mobile que abrem via JS, carrosséis de biblioteca, modais dinâmicos, envios de formulário).
- **Vantagem:** O site abre instantaneamente, não trava o browser tentando conectar a servidores de desenvolvimento e não exibe telas pretas de erro de framework.

### Outras limitações
- **Escopo de página única** — O cloner captura apenas a página fornecida. Não faz crawling de múltiplas páginas do site.
- **Conteúdo autenticado** — Para sites que requerem login, use o `storage_state` do Playwright.

---

## 📦 Dependências

| Pacote | Uso |
|---|---|
| `playwright` | Controle do browser headless (Chromium) |
| `httpx` | Download assíncrono de imagens e assets |
| `rich` | Interface colorida no terminal com progress bar |

Instale todas as dependências com:

```bash
pip install playwright httpx rich
playwright install chromium
```

---

## 📄 Licença

MIT — uso livre para fins pessoais e comerciais.