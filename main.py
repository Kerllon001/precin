from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn
import time
import re
import os

# --- CONFIGURAÇÃO INICIAL ---
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

# --- UTILITÁRIOS ---
def limpar_preco(texto):
    if not texto: return None
    texto_limpo = texto.replace('R$', '').replace('.', '').replace(',', '.').replace('\xa0', '').strip()
    match = re.search(r'(\d+(\.\d+)?)', texto_limpo)
    if match: return float(match.group(1))
    return None

def rolar_pagina(page):
    print("   -> 📜 Rolando para carregar itens...")
    for _ in range(3):
        page.mouse.wheel(0, 1000)
        time.sleep(0.5)

# --- SCRAPERS ---

def raspar_mercadolivre(page, produto):
    print("⏳ ML: Acessando...")
    try:
        page.goto(f"https://lista.mercadolivre.com.br/{produto.replace(' ', '-')}", wait_until="domcontentloaded")
        rolar_pagina(page)
        soup = BeautifulSoup(page.content(), 'html.parser')
        
        itens = soup.find_all('li', class_='ui-search-layout__item')
        if not itens: itens = soup.find_all('div', class_='ui-search-result__wrapper')
        if not itens: itens = soup.find_all('div', class_='poly-card')
        
        print(f"   -> ML: Encontrei {len(itens)} itens.")
        
        resultados = []
        for item in itens:
            try:
                titulo = item.find('h2', class_='ui-search-item__title') or item.find('a', class_='poly-component__title')
                if not titulo: continue
                
                preco_tag = item.find('span', class_='andes-money-amount__fraction')
                if not preco_tag: continue
                preco = limpar_preco(preco_tag.text)
                
                preco_antigo = None
                antigo_tag = item.find('s', class_='andes-money-amount')
                if antigo_tag:
                    frac = antigo_tag.find('span', class_='andes-money-amount__fraction')
                    if frac: preco_antigo = limpar_preco(frac.text)

                link_tag = item.find('a', class_='ui-search-link') or item.find('a', class_='poly-component__title') or item.find('a')
                
                img_tag = item.find('img')
                img_src = img_tag.get('data-src') or img_tag.get('src') if img_tag else f"{BASE_URL}/ml.png"

                resultados.append({"nome": titulo.text.strip(), "loja": "Mercado Livre", "preco": preco, "preco_antigo": preco_antigo, "link": link_tag['href'], "img": img_src})
            except: continue
        return resultados
    except Exception as e: 
        print(f"Erro ML: {e}")
        return []

def raspar_amazon(page, produto):
    print("⏳ Amazon: Acessando...")
    try:
        page.goto(f"https://www.amazon.com.br/s?k={produto.replace(' ', '+')}", wait_until="domcontentloaded")
        rolar_pagina(page)
        
        if "captcha" in page.content().lower():
            print("   -> 🚨 Amazon pediu Captcha. Tentando recarregar...")
            page.reload()
            time.sleep(2)

        soup = BeautifulSoup(page.content(), 'html.parser')
        itens = soup.find_all('div', {'data-component-type': 's-search-result'})
        
        print(f"   -> Amazon: Encontrei {len(itens)} itens.")
        
        resultados = []
        for item in itens:
            try:
                titulo_tag = item.find('span', class_='a-text-normal') or item.find('h2')
                if not titulo_tag: continue
                
                preco = None
                preco_tag = item.find('span', class_='a-price-whole')
                if preco_tag: preco = limpar_preco(preco_tag.text)
                if not preco:
                    preco_tag = item.find('span', class_='a-offscreen')
                    if preco_tag: preco = limpar_preco(preco_tag.text)
                
                if not preco: continue

                preco_antigo = None
                antigo_tag = item.find('span', class_='a-text-price')
                if antigo_tag:
                    off = antigo_tag.find('span', class_='a-offscreen')
                    if off: preco_antigo = limpar_preco(off.text)

                link_tag = item.find('a', class_='a-link-normal')
                link = "https://www.amazon.com.br" + link_tag['href']
                
                img_tag = item.find('img', class_='s-image')
                img_src = img_tag.get('src') if img_tag else f"{BASE_URL}/amazon.svg"

                resultados.append({"nome": titulo_tag.text.strip(), "loja": "Amazon", "preco": preco, "preco_antigo": preco_antigo, "link": link, "img": img_src})
            except: continue
        return resultados
    except Exception as e: 
        print(f"Erro Amazon: {e}")
        return []

def raspar_kabum(page, produto):
    print("⏳ Kabum: Acessando...")
    try:
        page.goto(f"https://www.kabum.com.br/busca?query={produto.replace(' ', '+')}", wait_until="domcontentloaded")
        try: page.wait_for_selector('article', timeout=3000)
        except: pass
        
        soup = BeautifulSoup(page.content(), 'html.parser')
        itens = soup.find_all('article')
        if not itens: itens = soup.find_all('div', class_='productCard')
        
        print(f"   -> Kabum: Encontrei {len(itens)} itens.")
        
        resultados = []
        for item in itens:
            try:
                titulo = item.find('span', class_='nameCard') or item.find('h2')
                if not titulo: continue
                
                preco_tag = item.find('span', class_='priceCard')
                if not preco_tag: continue
                preco = limpar_preco(preco_tag.text)
                
                preco_antigo = None
                antigo_tag = item.find('span', class_='oldPriceCard')
                if antigo_tag: preco_antigo = limpar_preco(antigo_tag.text)

                link_tag = item.find('a')
                link = "https://www.kabum.com.br" + link_tag['href']
                
                img_tag = item.find('img')
                img_src = img_tag.get('src') if img_tag else f"{BASE_URL}/kabum.png"

                resultados.append({"nome": titulo.text.strip(), "loja": "Kabum", "preco": preco, "preco_antigo": preco_antigo, "link": link, "img": img_src})
            except: continue
        return resultados
    except Exception as e: return []

def raspar_magalu(page, produto):
    print("⏳ Magalu: Acessando...")
    try:
        page.goto(f"https://www.magazineluiza.com.br/busca/{produto.replace(' ', '+')}/", wait_until="domcontentloaded")
        time.sleep(1.5)
        
        soup = BeautifulSoup(page.content(), 'html.parser')
        itens = soup.find_all('li', {'data-testid': 'product-card-container'}) or soup.find_all('a', {'data-testid': 'product-card-container'})
        
        print(f"   -> Magalu: Encontrei {len(itens)} itens.")
        
        resultados = []
        for item in itens:
            try:
                titulo = item.find('h2', {'data-testid': 'product-title'})
                if not titulo: continue
                
                preco_tag = item.find('p', {'data-testid': 'price-value'})
                if not preco_tag: continue
                preco = limpar_preco(preco_tag.text)

                preco_antigo = None
                antigo_tag = item.find('p', {'data-testid': 'price-original'})
                if antigo_tag: preco_antigo = limpar_preco(antigo_tag.text)

                link = "https://www.magazineluiza.com.br" + (item['href'] if item.name == 'a' else item.find('a')['href'])
                
                img_tag = item.find('img', {'data-testid': 'product-image'}) or item.find('img')
                img_src = f"{BASE_URL}/magalu.png"
                if img_tag:
                    src = img_tag.get('src') or img_tag.get('data-src')
                    if src and "http" in src: img_src = src

                resultados.append({"nome": titulo.text.strip(), "loja": "Magalu", "preco": preco, "preco_antigo": preco_antigo, "link": link, "img": img_src})
            except: continue
        return resultados
    except Exception as e: return []

def raspar_pichau(page, produto):
    print("⏳ Pichau: Acessando...")
    try:
        page.goto(f"https://www.pichau.com.br/search?q={produto.replace(' ', '+')}", wait_until="domcontentloaded")
        try: page.wait_for_selector("text=R$", timeout=6000)
        except: pass
        rolar_pagina(page)
        
        soup = BeautifulSoup(page.content(), 'html.parser')
        itens = soup.find_all('div', class_='MuiGrid-item')
        if not itens: itens = soup.find_all('a', {'data-cy': 'list-product'})

        print(f"   -> Pichau: Encontrei {len(itens)} itens.")

        resultados = []
        for item in itens:
            try:
                titulo_tag = item.find('h2') or item.find('div', class_='MuiTypography-root')
                if not titulo_tag or len(titulo_tag.text) < 5: continue
                
                preco = None
                preco_antigo = None
                textos_do_card = item.get_text(" | ")
                match_preco = re.search(r'à vista.*?R\$\s?([\d\.]+,\d{2})', textos_do_card)
                if match_preco: preco = limpar_preco(match_preco.group(1))
                else:
                    match_generico = re.search(r'R\$\s?([\d\.]+,\d{2})', textos_do_card)
                    if match_generico: preco = limpar_preco(match_generico.group(1))

                if not preco: continue

                link_tag = item.find('a')
                if not link_tag: 
                    if item.name == 'a': link_tag = item
                    else: continue
                
                link = link_tag['href']
                if not link.startswith('http'): link = "https://www.pichau.com.br" + link

                img_tag = item.find('img')
                img_src = img_tag.get('src') if img_tag else f"{BASE_URL}/pichau.png"

                resultados.append({"nome": titulo_tag.text.strip(), "loja": "Pichau", "preco": preco, "preco_antigo": preco_antigo, "link": link, "img": img_src})
            except: continue
        return resultados
    except Exception as e: return []

def raspar_terabyte(page, produto):
    print("⏳ Terabyte: Acessando (Modo Força Bruta)...")
    try:
        page.goto(f"https://www.terabyteshop.com.br/busca?str={produto.replace(' ', '+')}", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        
        soup = BeautifulSoup(page.content(), 'html.parser')
        links_candidatos = soup.find_all('a', href=True)
        
        print(f"   -> Terabyte: Analisando {len(links_candidatos)} links...")
        
        resultados = []
        links_processados = set()

        for link_tag in links_candidatos:
            href = link_tag['href']
            if len(href) < 15 or "javascript" in href: continue
            if href in links_processados: continue
            
            img_tag = link_tag.find('img')
            if not img_tag: continue
            
            texto_link = link_tag.get_text()
            texto_pai = link_tag.parent.get_text() if link_tag.parent else ""
            texto_completo = texto_link + " " + texto_pai
            
            if "R$" not in texto_completo: continue
            
            nome = ""
            if img_tag.get('alt'): nome = img_tag.get('alt')
            elif link_tag.get('title'): nome = link_tag.get('title')
            else: nome = link_tag.get_text().strip()
            
            if len(nome) < 5: continue

            preco = None
            match = re.search(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', texto_completo)
            if match: preco = limpar_preco(match.group(1))
            
            if not preco: continue
            
            if not href.startswith('http'): href = "https://www.terabyteshop.com.br" + href
            links_processados.add(href)

            img_src = "https://www.google.com/s2/favicons?domain=terabyteshop.com.br&sz=128"
            src = img_tag.get('src') or img_tag.get('data-src')
            if src and src.startswith('http'): img_src = src

            preco_antigo = None
            todos_valores = re.findall(r'R\$\s?([\d\.,]+)', texto_completo)
            for v in todos_valores:
                v_float = limpar_preco(v)
                if v_float and v_float > preco:
                    preco_antigo = v_float
                    break

            resultados.append({"nome": nome, "loja": "Terabyte", "preco": preco, "preco_antigo": preco_antigo, "link": href, "img": img_src})

        print(f"   -> Terabyte: {len(resultados)} produtos encontrados.")
        return resultados

    except Exception as e: 
        print(f"Erro Geral Terabyte: {e}")
        return []

# --- ORQUESTRAÇÃO ---
def buscar_com_navegador(produto, lojas_selecionadas):
    print(f"🕵️  BUSCANDO: {produto}")
    resultados_finais = []
    
    if not lojas_selecionadas or "todas" in lojas_selecionadas:
        lojas_selecionadas = ["ml", "amazon", "kabum", "magalu", "pichau", "terabyte"]

    # headless=True para não abrir janelas
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        if "ml" in lojas_selecionadas: resultados_finais.extend(raspar_mercadolivre(page, produto))
        if "amazon" in lojas_selecionadas: resultados_finais.extend(raspar_amazon(page, produto))
        if "kabum" in lojas_selecionadas: resultados_finais.extend(raspar_kabum(page, produto))
        if "magalu" in lojas_selecionadas: resultados_finais.extend(raspar_magalu(page, produto))
        if "pichau" in lojas_selecionadas: resultados_finais.extend(raspar_pichau(page, produto))
        if "terabyte" in lojas_selecionadas: resultados_finais.extend(raspar_terabyte(page, produto))

        browser.close()
    
    unicos = []
    vistos = set()
    for r in resultados_finais:
        chave = r['link']
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(r)

    unicos.sort(key=lambda x: x['preco'])
    return unicos

# --- ROTA DA API ---
@app.get("/api/buscar")
def buscar_produtos(q: str, lojas: str = "todas"):
    lista_lojas = lojas.split(",")
    return buscar_com_navegador(q, lista_lojas)

# --- ROTA DO SITE (Para o ngrok funcionar) ---
@app.get("/")
def read_root():
    return FileResponse('index.html')
    
if __name__ == "__main__":
    print("🚀 SERVIDOR ONLINE (Modo Invisível)")
    uvicorn.run(app, host="127.0.0.1", port=8000)