from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import uvicorn
import asyncio
import re
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("img"): os.makedirs("img")
app.mount("/static", StaticFiles(directory="img"), name="static")
BASE_URL = "http://127.0.0.1:8000/static"

# --- CONFIGURAÇÃO DE TEMPO ---
# Se a loja não responder em 25 segundos, ela é cortada para não travar o site
TIMEOUT_GLOBAL = 25000 

def limpar_preco(texto):
    if not texto: return None
    texto_limpo = texto.replace('R$', '').replace('.', '').replace(',', '.').replace('\xa0', '').strip()
    match = re.search(r'(\d+(\.\d+)?)', texto_limpo)
    if match: return float(match.group(1))
    return None

async def bloquear_recursos(route):
    if route.request.resource_type in ["image", "media", "font", "stylesheet", "script", "other"]:
        await route.abort()
    else:
        await route.continue_()

# --- SCRAPERS OTIMIZADOS ---

async def raspar_mercadolivre(context, produto):
    print("⏳ ML: Iniciando...")
    try:
        page = await context.new_page()
        await page.route("**/*", bloquear_recursos)
        await page.goto(f"https://lista.mercadolivre.com.br/{produto.replace(' ', '-')}", wait_until="domcontentloaded", timeout=TIMEOUT_GLOBAL)
        
        content = await page.content()
        await page.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        itens = soup.find_all('li', class_='ui-search-layout__item') or soup.find_all('div', class_='ui-search-result__wrapper') or soup.find_all('div', class_='poly-card')
        
        resultados = []
        for item in itens:
            try:
                titulo = item.find('h2', class_='ui-search-item__title') or item.find('a', class_='poly-component__title')
                if not titulo: continue
                
                preco_tag = item.find('span', class_='andes-money-amount__fraction')
                preco = limpar_preco(preco_tag.text) if preco_tag else None
                
                link_tag = item.find('a', class_='ui-search-link') or item.find('a', class_='poly-component__title') or item.find('a')
                
                img_src = f"{BASE_URL}/ml.png"
                img_tag = item.find('img')
                if img_tag: img_src = img_tag.get('data-src') or img_tag.get('src') or img_src

                if preco: resultados.append({"nome": titulo.text.strip(), "loja": "Mercado Livre", "preco": preco, "preco_antigo": None, "link": link_tag['href'], "img": img_src})
            except: continue
        print(f"   ✅ ML: {len(resultados)} ok")
        return resultados
    except: 
        print("   ❌ ML: Timeout ou Erro")
        return []

async def raspar_amazon(context, produto):
    print("⏳ Amazon: Iniciando...")
    try:
        page = await context.new_page()
        await page.route("**/*", bloquear_recursos)
        await page.goto(f"https://www.amazon.com.br/s?k={produto.replace(' ', '+')}", wait_until="domcontentloaded", timeout=TIMEOUT_GLOBAL)
        content = await page.content()
        await page.close()

        if "captcha" in content.lower(): return []

        soup = BeautifulSoup(content, 'html.parser')
        itens = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        resultados = []
        for item in itens:
            try:
                titulo_tag = item.find('span', class_='a-text-normal') or item.find('h2')
                if not titulo_tag: continue
                
                preco_tag = item.find('span', class_='a-price-whole')
                preco = limpar_preco(preco_tag.text) if preco_tag else None
                if not preco:
                    preco_tag = item.find('span', class_='a-offscreen')
                    preco = limpar_preco(preco_tag.text) if preco_tag else None
                
                if not preco: continue

                link_tag = item.find('a', class_='a-link-normal')
                link = "https://www.amazon.com.br" + link_tag['href']
                
                img_src = f"{BASE_URL}/amazon.svg"
                img_tag = item.find('img', class_='s-image')
                if img_tag: img_src = img_tag.get('src') or img_src

                resultados.append({"nome": titulo_tag.text.strip(), "loja": "Amazon", "preco": preco, "preco_antigo": None, "link": link, "img": img_src})
            except: continue
        print(f"   ✅ Amazon: {len(resultados)} ok")
        return resultados
    except: 
        print("   ❌ Amazon: Timeout ou Erro")
        return []

async def raspar_kabum(context, produto):
    print("⏳ Kabum: Iniciando...")
    try:
        page = await context.new_page()
        await page.route("**/*", bloquear_recursos)
        await page.goto(f"https://www.kabum.com.br/busca?query={produto.replace(' ', '+')}", wait_until="domcontentloaded", timeout=TIMEOUT_GLOBAL)
        content = await page.content()
        await page.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        itens = soup.find_all('article') or soup.find_all('div', class_='productCard')
        
        resultados = []
        for item in itens:
            try:
                titulo = item.find('span', class_='nameCard') or item.find('h2')
                if not titulo: continue
                
                preco_tag = item.find('span', class_='priceCard')
                preco = limpar_preco(preco_tag.text) if preco_tag else None
                if not preco: continue

                link_tag = item.find('a')
                link = "https://www.kabum.com.br" + link_tag['href']
                
                img_src = f"{BASE_URL}/kabum.png"
                img_tag = item.find('img')
                if img_tag: img_src = img_tag.get('src') or img_src

                resultados.append({"nome": titulo.text.strip(), "loja": "Kabum", "preco": preco, "preco_antigo": None, "link": link, "img": img_src})
            except: continue
        print(f"   ✅ Kabum: {len(resultados)} ok")
        return resultados
    except: 
        print("   ❌ Kabum: Timeout ou Erro")
        return []

async def raspar_magalu(context, produto):
    print("⏳ Magalu: Iniciando...")
    try:
        page = await context.new_page()
        await page.route("**/*", bloquear_recursos)
        await page.goto(f"https://www.magazineluiza.com.br/busca/{produto.replace(' ', '+')}/", wait_until="domcontentloaded", timeout=TIMEOUT_GLOBAL)
        content = await page.content()
        await page.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        itens = soup.find_all('li', {'data-testid': 'product-card-container'}) or soup.find_all('a', {'data-testid': 'product-card-container'})
        
        resultados = []
        for item in itens:
            try:
                titulo = item.find('h2', {'data-testid': 'product-title'})
                if not titulo: continue
                
                preco_tag = item.find('p', {'data-testid': 'price-value'})
                preco = limpar_preco(preco_tag.text) if preco_tag else None
                
                link = "https://www.magazineluiza.com.br" + (item['href'] if item.name == 'a' else item.find('a')['href'])
                
                img_src = f"{BASE_URL}/magalu.png"
                img_tag = item.find('img', {'data-testid': 'product-image'}) or item.find('img')
                if img_tag:
                    src = img_tag.get('src') or img_tag.get('data-src')
                    if src and "http" in src: img_src = src

                if preco: resultados.append({"nome": titulo.text.strip(), "loja": "Magalu", "preco": preco, "preco_antigo": None, "link": link, "img": img_src})
            except: continue
        print(f"   ✅ Magalu: {len(resultados)} ok")
        return resultados
    except: 
        print("   ❌ Magalu: Timeout ou Erro")
        return []

async def raspar_pichau(context, produto):
    print("⏳ Pichau: Iniciando...")
    try:
        page = await context.new_page()
        await page.route("**/*", bloquear_recursos)
        await page.goto(f"https://www.pichau.com.br/search?q={produto.replace(' ', '+')}", wait_until="domcontentloaded", timeout=TIMEOUT_GLOBAL)
        
        content = await page.content()
        await page.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        itens = soup.find_all('div', class_='MuiGrid-item') or soup.find_all('a', {'data-cy': 'list-product'})

        resultados = []
        for item in itens:
            try:
                titulo_tag = item.find('h2') or item.find('div', class_='MuiTypography-root')
                if not titulo_tag: continue
                
                preco = None
                textos = item.get_text(" | ")
                match = re.search(r'à vista.*?R\$\s?([\d\.]+,\d{2})', textos)
                if match: preco = limpar_preco(match.group(1))
                
                if not preco: continue

                link_tag = item.find('a')
                if not link_tag: 
                    if item.name == 'a': link_tag = item
                    else: continue
                
                link = link_tag['href']
                if not link.startswith('http'): link = "https://www.pichau.com.br" + link
                
                img_src = f"{BASE_URL}/pichau.png"
                img_tag = item.find('img')
                if img_tag: img_src = img_tag.get('src') or img_src

                resultados.append({"nome": titulo_tag.text.strip(), "loja": "Pichau", "preco": preco, "preco_antigo": None, "link": link, "img": img_src})
            except: continue
        print(f"   ✅ Pichau: {len(resultados)} ok")
        return resultados
    except: 
        print("   ❌ Pichau: Timeout ou Erro")
        return []

async def raspar_terabyte(context, produto):
    print("⏳ Terabyte: Iniciando...")
    try:
        page = await context.new_page()
        await page.route("**/*", bloquear_recursos)
        # 30 segundos no máximo pra Terabyte (antes era 90s)
        await page.goto(f"https://www.terabyteshop.com.br/busca?str={produto.replace(' ', '+')}", wait_until="domcontentloaded", timeout=30000)
        
        content = await page.content()
        await page.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        links_candidatos = soup.find_all('a', href=True)
        
        resultados = []
        links_processados = set()

        for link_tag in links_candidatos:
            try:
                href = link_tag['href']
                if len(href) < 15 or "javascript" in href: continue
                if href in links_processados: continue
                
                img_tag = link_tag.find('img')
                if not img_tag: continue
                
                texto = link_tag.get_text() + " " + (link_tag.parent.get_text() if link_tag.parent else "")
                if "R$" not in texto: continue
                
                nome = img_tag.get('alt') or link_tag.get('title') or link_tag.get_text().strip()
                if len(nome) < 5: continue

                preco = None
                match = re.search(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', texto)
                if match: preco = limpar_preco(match.group(1))
                if not preco: continue
                
                if not href.startswith('http'): href = "https://www.terabyteshop.com.br" + href
                links_processados.add(href)

                img_src = "https://www.google.com/s2/favicons?domain=terabyteshop.com.br&sz=128"
                src = img_tag.get('src') or img_tag.get('data-src')
                if src and src.startswith('http'): img_src = src

                resultados.append({"nome": nome, "loja": "Terabyte", "preco": preco, "preco_antigo": None, "link": href, "img": img_src})
            except: continue
        print(f"   ✅ Terabyte: {len(resultados)} ok")
        return resultados
    except: 
        print("   ❌ Terabyte: Timeout ou Erro")
        return []

# --- ORQUESTRAÇÃO FINAL ---
async def buscar_paralelo(produto, lojas_selecionadas):
    print(f"🚀 BUSCA PARALELA: {produto}")
    
    if not lojas_selecionadas or "todas" in lojas_selecionadas:
        lojas_selecionadas = ["ml", "amazon", "kabum", "magalu", "pichau", "terabyte"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--single-process', '--disable-extensions']
        )
        
        context = await browser.new_context(
            viewport={'width': 800, 'height': 600},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        tasks = []
        if "ml" in lojas_selecionadas: tasks.append(raspar_mercadolivre(context, produto))
        if "amazon" in lojas_selecionadas: tasks.append(raspar_amazon(context, produto))
        if "magalu" in lojas_selecionadas: tasks.append(raspar_magalu(context, produto))
        if "kabum" in lojas_selecionadas: tasks.append(raspar_kabum(context, produto))
        if "pichau" in lojas_selecionadas: tasks.append(raspar_pichau(context, produto))
        if "terabyte" in lojas_selecionadas: tasks.append(raspar_terabyte(context, produto))
        
        # AQUI É A CHAVE: Espera todos, mas desiste de quem demorar
        resultados_listas = await asyncio.gather(*tasks)
        
        await browser.close()
    
    print("✅ TODAS AS BUSCAS TERMINARAM. ENVIANDO RESPOSTA...")
    
    resultados_finais = []
    for lista in resultados_listas:
        resultados_finais.extend(lista)

    unicos = []
    vistos = set()
    for r in resultados_finais:
        chave = r['link']
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(r)

    unicos.sort(key=lambda x: x['preco'])
    return unicos

@app.get("/api/buscar")
async def buscar_produtos(q: str, lojas: str = "todas"):
    lista_lojas = lojas.split(",")
    return await buscar_paralelo(q, lista_lojas)

@app.get("/")
def read_root():
    return FileResponse('index.html')
    
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)