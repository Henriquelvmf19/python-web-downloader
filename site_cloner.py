#!/usr/bin/env python3
"""
site_cloner.py — Clone a full website page as a self-contained local HTML file
with all assets (images, CSS, fonts) preserved for offline viewing.

Uses Playwright to render JavaScript-heavy sites (React, Vite, Next.js, etc.)
and captures the fully rendered DOM along with every asset.

Framework-aware: detects the rendering stack (Next.js, Nuxt, React, Vite, etc.)
and strips hydration/runtime scripts to produce a clean static HTML clone that
works offline with zero console errors.
"""

import asyncio
import re
import sys
import hashlib
import mimetypes
import html as html_module
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from collections import defaultdict

import httpx
from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich import print as rprint

console = Console()

# ─────────────────────────────────────────────
#  Constants & Config
# ─────────────────────────────────────────────

ASSET_EXTENSIONS = {
    "images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".ico", ".bmp", ".tiff", ".apng"},
    "css": {".css"},
    "js": {".js", ".mjs", ".cjs"},
    "fonts": {".woff", ".woff2", ".ttf", ".otf", ".eot"},
    "media": {".mp4", ".webm", ".ogg", ".mp3", ".wav"},
}

CONTENT_TYPE_TO_CATEGORY = {
    "image/": "images",
    "text/css": "css",
    "application/javascript": "js",
    "text/javascript": "js",
    "application/x-javascript": "js",
    "font/": "fonts",
    "application/font": "fonts",
    "application/x-font": "fonts",
    "application/vnd.ms-fontobject": "fonts",
    "video/": "media",
    "audio/": "media",
}

# Frameworks that use client-side hydration (scripts must be stripped)
SPA_FRAMEWORKS = {"nextjs", "nuxt", "react", "vite", "angular"}

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def classify_asset(url: str, content_type: str = "") -> str:
    """Classify an asset into a subfolder based on URL extension or content-type."""
    ct = content_type.split(";")[0].strip().lower()
    for pattern, category in CONTENT_TYPE_TO_CATEGORY.items():
        if pattern in ct:
            return category

    path = urlparse(url).path.lower().split("?")[0]
    ext = Path(path).suffix
    for category, extensions in ASSET_EXTENSIONS.items():
        if ext in extensions:
            return category

    if ext:
        return "misc"
    return "images"


def safe_filename(url: str, content_type: str = "") -> str:
    """Generate a safe, unique filename from a URL."""
    parsed = urlparse(url)
    path_part = unquote(parsed.path)
    name = Path(path_part).name or "asset"
    name_clean = name.split("?")[0].split("#")[0]

    ext = Path(name_clean).suffix
    if not ext and content_type:
        ct = content_type.split(";")[0].strip().lower()
        guessed = mimetypes.guess_extension(ct)
        if guessed:
            ext = guessed
            if ext == ".jpe":
                ext = ".jpg"

    stem = re.sub(r"[^\w\-]", "_", Path(name_clean).stem)[:60]
    digest = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{stem}_{digest}{ext}"


def resolve_url(base: str, src: str) -> str | None:
    """Resolve relative, absolute, or protocol-relative URLs."""
    if not src or src.startswith("data:") or src.startswith("blob:"):
        return None
    if src.startswith("//"):
        src = "https:" + src
    resolved = urljoin(base, src)
    if not resolved.startswith(("http://", "https://")):
        return None
    return resolved


def extract_css_urls(css_text: str, base_url: str, return_raw: bool = False) -> set[str]:
    """Extract all url(...) references from CSS text."""
    urls = set()
    raws = set()

    # Unescape HTML entities first (handles &quot; etc.)
    clean_css = html_module.unescape(css_text)

    pattern = r"""url\(\s*(['"]?)(.*?)\1\s*\)"""
    for match in re.finditer(pattern, clean_css, re.IGNORECASE):
        raw_url = match.group(2).strip()
        resolved = resolve_url(base_url, raw_url)
        if resolved:
            urls.add(resolved)
            raws.add(raw_url)

    import_pattern = r"""@import\s+(['"])(.*?)\1"""
    for match in re.finditer(import_pattern, clean_css, re.IGNORECASE):
        raw_url = match.group(2).strip()
        resolved = resolve_url(base_url, raw_url)
        if resolved:
            urls.add(resolved)
            raws.add(raw_url)

    return raws if return_raw else urls


def extract_srcset_urls(srcset: str, base_url: str, return_raw: bool = False) -> list[str]:
    """Parse srcset attribute and return all URLs or raw matches."""
    urls = []
    raws = []
    for entry in srcset.split(","):
        parts = entry.strip().split()
        if parts:
            raw_url = parts[0]
            resolved = resolve_url(base_url, raw_url)
            if resolved:
                urls.append(resolved)
                raws.append(raw_url)
    return raws if return_raw else urls


# ─────────────────────────────────────────────
#  Framework Detection
# ─────────────────────────────────────────────

def detect_framework(html: str) -> str:
    """
    Detect the rendering framework from the HTML content.
    Returns: "nextjs", "nuxt", "react", "vite", "angular", "static", or "unknown"
    """
    # Next.js markers
    if any(marker in html for marker in [
        "__next_f", "_next/static", "<next-route-announcer",
        "next/dist/client", "__NEXT_DATA__",
    ]):
        return "nextjs"

    # Nuxt.js markers
    if any(marker in html for marker in [
        "__NUXT__", "_nuxt/", "nuxt.config",
    ]):
        return "nuxt"

    # Angular markers
    if any(marker in html for marker in [
        "ng-version", "ng-app", "_ng_",
    ]):
        return "angular"

    # Vite markers (check before generic React since Vite can serve React)
    if any(marker in html for marker in [
        "/@vite/", "vite/modulepreload",
    ]):
        return "vite"

    # Generic React / Create React App
    if any(marker in html for marker in [
        "__REACT_DEVTOOLS", "react-root", 'id="root"',
        "static/js/main.", "react-dom",
    ]):
        return "react"

    # Check for any SPA-like patterns (module scripts, app shells)
    if re.search(r'<script[^>]*type\s*=\s*["\']module["\']', html):
        return "vite"  # likely a modern bundler

    return "static"


# ─────────────────────────────────────────────
#  HTML Cleaning (framework-specific)
# ─────────────────────────────────────────────

def clean_html(html: str, framework: str) -> str:
    """
    Clean the rendered HTML based on detected framework.
    For SPA frameworks: strip ALL scripts to prevent hydration crashes.
    For static sites: keep scripts intact.
    """
    if framework not in SPA_FRAMEWORKS:
        console.log(f"[green]Static site detected — keeping scripts intact.[/green]")
        return html

    console.log(f"[yellow]SPA framework ({framework}) detected — stripping hydration scripts…[/yellow]")

    # Remove ALL <script> tags (inline and external)
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<script\b[^>]*/>', '', html, flags=re.IGNORECASE)

    # Remove framework-specific elements
    if framework == "nextjs":
        html = re.sub(r'<next-route-announcer[^>]*>.*?</next-route-announcer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<next-route-announcer[^>]*/>', '', html, flags=re.IGNORECASE)

    # Unescape HTML entities in inline style attributes
    # This fixes &quot;/images/portfolio_1.jpeg&quot; → "/images/portfolio_1.jpeg"
    def unescape_style(match):
        tag_before = match.group(1)
        style_content = html_module.unescape(match.group(2))
        quote = match.group(3)
        return f'{tag_before}style={quote}{style_content}{quote}'

    html = re.sub(
        r'(<[^>]*?)style\s*=\s*(["\'])(.*?)\2',
        lambda m: f'{m.group(1)}style={m.group(2)}{html_module.unescape(m.group(3))}{m.group(2)}',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Remove <link rel="preload" as="script" ...> since we stripped scripts
    html = re.sub(
        r'<link\b[^>]*\brel\s*=\s*["\']preload["\'][^>]*\bas\s*=\s*["\']script["\'][^>]*/?>',
        '', html, flags=re.IGNORECASE,
    )
    html = re.sub(
        r'<link\b[^>]*\bas\s*=\s*["\']script["\'][^>]*\brel\s*=\s*["\']preload["\'][^>]*/?>',
        '', html, flags=re.IGNORECASE,
    )

    # Count what was removed
    scripts_removed = html.count('<script')  # should be 0 now
    console.log(f"[cyan]Cleaned HTML: all scripts removed, HTML entities unescaped.[/cyan]")

    return html


# ─────────────────────────────────────────────
#  Playwright: Capture page + intercept assets
# ─────────────────────────────────────────────

async def capture_page(
    url: str,
    scroll: bool = True,
    timeout: int = 30000,
) -> tuple[str, dict[str, bytes], dict[str, str]]:
    """
    Launch a headless browser, render the page, and:
    1. Intercept ALL network responses (cache the body bytes)
    2. Capture the fully rendered DOM via page.content()

    Returns:
        - html: the rendered HTML string
        - response_cache: {url: bytes} of all intercepted response bodies
        - content_types: {url: content_type} headers
    """
    response_cache: dict[str, bytes] = {}
    content_types: dict[str, str] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # --- Intercept ALL network responses ---
        async def on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                resp_url = response.url
                if response.ok:
                    try:
                        body = await response.body()
                        response_cache[resp_url] = body
                        content_types[resp_url] = ct
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", on_response)

        console.log(f"[cyan]Navigating to[/cyan] {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
        except Exception as e:
            console.log(f"[yellow]Navigation warning: {e}. Continuing with partial load…[/yellow]")

        # --- Scroll to trigger lazy loading ---
        if scroll:
            console.log("[yellow]Scrolling page to trigger lazy-loaded content…[/yellow]")
            prev_height = 0
            for _ in range(20):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
                await asyncio.sleep(0.6)
                height = await page.evaluate("document.body.scrollHeight")
                if height == prev_height:
                    break
                prev_height = height
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)

        # --- Capture rendered DOM ---
        console.log("[cyan]Capturing rendered DOM…[/cyan]")
        html = await page.content()

        await browser.close()

    console.print(f"[bold green]Captured {len(response_cache)} network responses.[/bold green]")
    return html, response_cache, content_types


# ─────────────────────────────────────────────
#  HTML parsing — extract all asset URLs
# ─────────────────────────────────────────────

def collect_asset_urls(html: str, base_url: str) -> tuple[set[str], dict[str, set[str]]]:
    """
    Parse rendered HTML to find all asset references.
    Returns: (set_of_resolved_urls, dict_mapping_resolved_to_raw_strings)
    """
    urls = set()
    raw_mappings = defaultdict(set)

    def track(raw_url: str):
        resolved = resolve_url(base_url, raw_url)
        if resolved:
            urls.add(resolved)
            raw_mappings[resolved].add(raw_url)

    # <link href>
    for m in re.finditer(r'<link\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # <img src>
    for m in re.finditer(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # <img srcset>
    for m in re.finditer(r'<img\b[^>]*\bsrcset\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        for raw in extract_srcset_urls(m.group(1), base_url, return_raw=True):
            track(raw)

    # <source srcset>
    for m in re.finditer(r'<source\b[^>]*\bsrcset\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        for raw in extract_srcset_urls(m.group(1), base_url, return_raw=True):
            track(raw)

    # <source src>
    for m in re.finditer(r'<source\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # <video src/poster>
    for m in re.finditer(r'<video\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))
    for m in re.finditer(r'<video\b[^>]*\bposter\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # <audio src>
    for m in re.finditer(r'<audio\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # <object data>
    for m in re.finditer(r'<object\b[^>]*\bdata\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # <embed src>
    for m in re.finditer(r'<embed\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        track(m.group(1))

    # Inline styles with url(...) — already unescaped by clean_html
    for m in re.finditer(r'style\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        for raw in extract_css_urls(m.group(1), base_url, return_raw=True):
            track(raw)

    # <style> blocks
    for m in re.finditer(r'<style[^>]*>(.*?)</style>', html, re.IGNORECASE | re.DOTALL):
        for raw in extract_css_urls(m.group(1), base_url, return_raw=True):
            track(raw)

    return urls, raw_mappings


# ─────────────────────────────────────────────
#  Asset download with cache
# ─────────────────────────────────────────────

def _normalize_localhost_url(url: str) -> str:
    """Convert localhost URLs to use 127.0.0.1 for httpx compatibility."""
    parsed = urlparse(url)
    if parsed.hostname == "localhost":
        return url.replace("://localhost", "://127.0.0.1", 1)
    return url


async def download_assets(
    asset_urls: set[str],
    output_dir: Path,
    response_cache: dict[str, bytes],
    content_types: dict[str, str],
    concurrency: int = 10,
) -> tuple[dict[str, Path], list[tuple[str, str]]]:
    """Download all asset URLs, using the response cache when possible."""
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    url_to_path: dict[str, Path] = {}
    failed: list[tuple[str, str]] = []
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()

    async def process_asset(client: httpx.AsyncClient, url: str, progress, task) -> None:
        async with sem:
            try:
                ct = content_types.get(url, "")
                body: bytes | None = response_cache.get(url)

                if body is None:
                    try:
                        # Use 127.0.0.1 to avoid IPv6 resolution issues
                        fetch_url = _normalize_localhost_url(url)
                        r = await client.get(fetch_url, follow_redirects=True, timeout=60)
                        r.raise_for_status()
                        body = r.content
                        ct = r.headers.get("content-type", "")
                    except Exception as exc:
                        async with lock:
                            failed.append((url, f"{type(exc).__name__}: {exc}"))
                        return

                category = classify_asset(url, ct)
                # Don't save JS files for SPA clones (they're stripped from HTML anyway)
                # But DO save them for static sites
                category_dir = assets_dir / category
                category_dir.mkdir(parents=True, exist_ok=True)

                filename = safe_filename(url, ct)
                dest = category_dir / filename

                counter = 1
                while dest.exists():
                    dest = category_dir / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
                    counter += 1

                dest.write_bytes(body)
                async with lock:
                    url_to_path[url] = dest

            except Exception as exc:
                async with lock:
                    failed.append((url, f"{type(exc).__name__}: {exc}"))
            finally:
                progress.advance(task)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Downloading assets…", total=len(asset_urls))
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 site-cloner/2.0"},
            follow_redirects=True,
            timeout=60,
        ) as client:
            await asyncio.gather(*[process_asset(client, u, progress, task) for u in asset_urls])

    return url_to_path, failed


# ─────────────────────────────────────────────
#  CSS deep-scan: find assets inside CSS files
# ─────────────────────────────────────────────

async def deep_scan_css(
    url_to_path: dict[str, Path],
    content_types: dict[str, str],
    output_dir: Path,
    response_cache: dict[str, bytes],
    concurrency: int = 10,
) -> tuple[dict[str, Path], list[tuple[str, str]]]:
    """Scan downloaded CSS files for additional asset references."""
    new_urls: set[str] = set()

    for original_url, local_path in list(url_to_path.items()):
        ct = content_types.get(original_url, "")
        is_css = "css" in ct.lower() or local_path.suffix.lower() == ".css"
        if not is_css:
            continue

        try:
            css_text = local_path.read_text(encoding="utf-8", errors="ignore")
            css_refs = extract_css_urls(css_text, original_url)
            for ref in css_refs:
                if ref not in url_to_path:
                    new_urls.add(ref)
        except Exception:
            pass

    if not new_urls:
        return {}, []

    console.print(f"[cyan]Found {len(new_urls)} additional assets referenced in CSS files.[/cyan]")
    return await download_assets(
        new_urls, output_dir, response_cache, content_types, concurrency
    )


# ─────────────────────────────────────────────
#  Path rewriting
# ─────────────────────────────────────────────

def rewrite_html_paths(html: str, url_to_path: dict[str, Path], output_dir: Path, raw_mappings: dict[str, set[str]]) -> str:
    """Rewrite all asset URLs in the HTML to point to local relative paths."""
    sorted_urls = sorted(url_to_path.keys(), key=len, reverse=True)

    for original_url in sorted_urls:
        local_path = url_to_path[original_url]
        try:
            relative = local_path.relative_to(output_dir)
        except ValueError:
            continue
        rel_str = str(relative).replace("\\", "/")

        # Replace the exact raw strings found in the HTML
        for raw in raw_mappings.get(original_url, []):
            html = html.replace(f'"{raw}"', f'"{rel_str}"')
            html = html.replace(f"'{raw}'", f"'{rel_str}'")
            html = html.replace(f"url({raw})", f"url({rel_str})")
            html = html.replace(f'url("{raw}")', f'url("{rel_str}")')
            html = html.replace(f"url('{raw}')", f"url('{rel_str}')")

        # Fallback: replace the full absolute URL
        html = html.replace(original_url, rel_str)

    return html


def rewrite_css_paths(css_text: str, original_css_url: str, url_to_path: dict[str, Path], css_local_path: Path, output_dir: Path) -> str:
    """Rewrite url(...) references in CSS to point to local relative paths."""
    def replace_url(match):
        quote = match.group(1)
        raw_url = match.group(2).strip()
        resolved = resolve_url(original_css_url, raw_url)
        if resolved and resolved in url_to_path:
            asset_path = url_to_path[resolved]
            try:
                css_dir = css_local_path.parent
                try:
                    rel_path = asset_path.relative_to(css_dir)
                except ValueError:
                    rel_path = Path("..") / asset_path.relative_to(output_dir / "assets")
                rel_str = str(rel_path).replace("\\", "/")
                return f"url({quote}{rel_str}{quote})"
            except Exception:
                pass
        return match.group(0)

    pattern = r"""url\(\s*(['"]?)(.*?)\1\s*\)"""
    return re.sub(pattern, replace_url, css_text, flags=re.IGNORECASE)


def rewrite_all_css_files(url_to_path: dict[str, Path], content_types: dict[str, str], output_dir: Path) -> None:
    """Rewrite paths in all downloaded CSS files."""
    for original_url, local_path in url_to_path.items():
        ct = content_types.get(original_url, "")
        is_css = "css" in ct.lower() or local_path.suffix.lower() == ".css"
        if not is_css:
            continue
        try:
            css_text = local_path.read_text(encoding="utf-8", errors="ignore")
            rewritten = rewrite_css_paths(css_text, original_url, url_to_path, local_path, output_dir)
            if rewritten != css_text:
                local_path.write_text(rewritten, encoding="utf-8")
        except Exception:
            pass


# ─────────────────────────────────────────────
#  Report
# ─────────────────────────────────────────────

def print_report(url_to_path: dict[str, Path], failed: list[tuple[str, str]], output_dir: Path, framework: str) -> None:
    """Print a summary table of the cloning results."""
    console.rule("[bold green]Cloning Complete")

    categories: dict[str, int] = {}
    total_bytes = 0
    for path in url_to_path.values():
        if path.exists():
            total_bytes += path.stat().st_size
            parts = path.relative_to(output_dir).parts
            cat = parts[1] if len(parts) > 2 else "other"
            categories[cat] = categories.get(cat, 0) + 1

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("🔍 Framework", framework)
    table.add_row("✅ Total assets", str(len(url_to_path)))
    for cat, count in sorted(categories.items()):
        emoji = {"images": "🖼️", "css": "🎨", "js": "⚙️", "fonts": "🔤", "media": "🎬"}.get(cat, "📄")
        table.add_row(f"   {emoji} {cat}", str(count))
    table.add_row("❌ Failed", str(len(failed)))
    table.add_row("📁 Output folder", str(output_dir.resolve()))
    if total_bytes < 1_048_576:
        table.add_row("💾 Total size", f"{total_bytes / 1024:.1f} KB")
    else:
        table.add_row("💾 Total size", f"{total_bytes / 1_048_576:.2f} MB")
    console.print(table)

    if failed:
        console.rule("[bold red]Failed URLs")
        for url, reason in failed[:20]:
            rprint(f"  [red]✗[/red] {url[:80]}…  →  [dim]{reason}[/dim]")
        if len(failed) > 20:
            console.print(f"  … and {len(failed) - 20} more.")


# ─────────────────────────────────────────────
#  Main pipeline
# ─────────────────────────────────────────────

async def clone_site(
    url: str,
    output_dir: Path,
    scroll: bool = True,
    timeout: int = 30,
    concurrency: int = 10,
) -> None:
    """Full pipeline: capture → detect → clean → collect → download → rewrite → save."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Capture page with Playwright ──
    console.rule("[bold blue]Step 1 · Capturing Page")
    html, response_cache, content_types = await capture_page(
        url, scroll=scroll, timeout=timeout * 1000
    )

    # ── Step 2: Detect framework ──
    console.rule("[bold blue]Step 2 · Detecting Framework")
    framework = detect_framework(html)
    console.print(f"[bold green]Detected framework: {framework}[/bold green]")

    # ── Step 3: Clean HTML (strip scripts for SPA frameworks) ──
    console.rule("[bold blue]Step 3 · Cleaning HTML")
    html = clean_html(html, framework)

    # ── Step 4: Collect asset URLs from cleaned HTML ──
    console.rule("[bold blue]Step 4 · Collecting Asset URLs")
    asset_urls, raw_mappings = collect_asset_urls(html, url)

    # Also add cached responses that are CSS/fonts/images (not JS for SPA)
    for resp_url, ct in content_types.items():
        if resp_url in asset_urls:
            continue
        ct_lower = ct.lower()
        # For SPA frameworks, skip JS assets since scripts are stripped
        if framework in SPA_FRAMEWORKS:
            if any(js in ct_lower for js in ["javascript", "ecmascript"]):
                continue
        asset_urls.add(resp_url)

    console.print(f"[bold green]{len(asset_urls)} asset URL(s) found.[/bold green]")

    if not asset_urls:
        console.print("[yellow]No assets found. Saving HTML only.[/yellow]")
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        return

    # ── Step 5: Download all assets ──
    console.rule("[bold blue]Step 5 · Downloading Assets")
    url_to_path, failed = await download_assets(
        asset_urls, output_dir, response_cache, content_types, concurrency
    )

    # ── Step 6: Deep-scan CSS for additional assets (fonts, bg images) ──
    console.rule("[bold blue]Step 6 · Scanning CSS for Additional Assets")
    css_extra_paths, css_extra_failed = await deep_scan_css(
        url_to_path, content_types, output_dir, response_cache, concurrency
    )
    url_to_path.update(css_extra_paths)
    failed.extend(css_extra_failed)

    # ── Step 7: Rewrite paths ──
    console.rule("[bold blue]Step 7 · Rewriting Paths")

    rewrite_all_css_files(url_to_path, content_types, output_dir)
    console.log("[cyan]CSS file paths rewritten.[/cyan]")

    html = rewrite_html_paths(html, url_to_path, output_dir, raw_mappings)
    console.log("[cyan]HTML paths rewritten.[/cyan]")

    # ── Step 8: Save index.html ──
    console.rule("[bold blue]Step 8 · Saving Clone")
    index_path = output_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    console.print(f"[bold green]Saved:[/bold green] {index_path.resolve()}")

    # ── Report ──
    print_report(url_to_path, failed, output_dir, framework)


# ─────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────

async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="🌐 Clone a full website page as a self-contained local HTML with all assets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python site_cloner.py https://example.com
  python site_cloner.py https://example.com -o ./my_clone
  python site_cloner.py http://localhost:3000 --no-scroll --timeout 30
  python site_cloner.py https://example.com -c 16
        """,
    )
    parser.add_argument("url", help="Target URL to clone")
    parser.add_argument("-o", "--output", default="./cloned_site", help="Output directory (default: ./cloned_site)")
    parser.add_argument("-c", "--concurrency", type=int, default=10, help="Parallel download workers (default: 10)")
    parser.add_argument("--no-scroll", action="store_true", help="Disable auto-scroll (faster, may miss lazy content)")
    parser.add_argument("--timeout", type=int, default=30, help="Page load timeout in seconds (default: 30)")
    args = parser.parse_args()

    output_dir = Path(args.output)

    console.rule("[bold blue]🌐 Site Cloner v2[/bold blue]")
    console.print(f"[bold]Target:[/bold]  {args.url}")
    console.print(f"[bold]Output:[/bold]  {output_dir.resolve()}\n")

    await clone_site(
        url=args.url,
        output_dir=output_dir,
        scroll=not args.no_scroll,
        timeout=args.timeout,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    asyncio.run(main())
