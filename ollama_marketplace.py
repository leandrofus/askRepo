import requests
from bs4 import BeautifulSoup

def search_ollama_marketplace(query=""):
    """
    Scrapes ollama.com/library for models.
    Categorizes them based on tags like vision, tools, embedding, etc.
    """
    try:
        url = f"https://ollama.com/library"
        if query:
            url += f"?q={query}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return []
        
        soup = BeautifulSoup(res.text, 'html.parser')
        models = []
        
        for item in soup.find_all('li'):
            a_tag = item.find('a', href=True)
            if a_tag and '/library/' in a_tag['href']:
                # Extracting model slug from href
                slug = a_tag['href'].split('/')[-1]
                
                name_tag = item.find('h2') or item.find('span', class_='text-lg')
                name = name_tag.get_text(strip=True) if name_tag else slug
                
                desc_tag = item.find('p')
                description = desc_tag.get_text(strip=True) if desc_tag else ""
                
                # Extract all span tags (they contain capabilities and sizes)
                all_spans = [s.get_text(strip=True).lower() for s in item.find_all('span')]
                
                # Sizes (e.g. 7b, 1.5b)
                sizes = [s.upper() for s in all_spans if s.endswith('b')]
                
                # Capabilities
                capabilities = []
                if 'vision' in all_spans: capabilities.append('vision')
                if 'tools' in all_spans: capabilities.append('tools')
                if 'thinking' in all_spans: capabilities.append('reasoning')
                if 'embedding' in all_spans: capabilities.append('embedding')
                if 'coder' in slug or 'code' in description.lower(): capabilities.append('coding')
                
                # If no specific capability found, it's a general LLM
                if not capabilities: capabilities.append('general')
                
                models.append({
                    "name": name,
                    "slug": slug,
                    "description": description,
                    "sizes": sizes,
                    "capabilities": capabilities,
                    "url": f"https://ollama.com{a_tag['href']}"
                })
        
        return models
    except Exception as e:
        print(f"Scraper error: {e}")
        return []
