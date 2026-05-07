import requests
from bs4 import BeautifulSoup

def search_ollama_marketplace(query):
    """
    Scrapes ollama.com/library for models matching the query.
    """
    try:
        url = f"https://ollama.com/library?q={query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return []
        
        soup = BeautifulSoup(res.text, 'html.parser')
        models = []
        
        # Ollama library items are typically inside <li> in a <ul>
        # Based on the text structure, we look for links to /library/model-name
        for item in soup.find_all('li'):
            a_tag = item.find('a', href=True)
            if a_tag and '/library/' in a_tag['href']:
                name_tag = item.find('h2') or item.find('span', class_='text-lg')
                if not name_tag:
                    # Fallback: extract from href or text
                    name = a_tag['href'].split('/')[-1]
                else:
                    name = name_tag.get_text(strip=True)
                
                desc_tag = item.find('p')
                description = desc_tag.get_text(strip=True) if desc_tag else ""
                
                # Extract tags (sizes)
                # These are usually in span or similar inside the item
                tags = [t.get_text(strip=True) for t in item.find_all('span') if any(c.isdigit() for c in t.get_text())]
                # Filter tags to only include things like 7b, 1.5b etc.
                tags = [t for t in tags if t.endswith('b') or t.endswith('B')]
                
                models.append({
                    "name": name,
                    "description": description,
                    "tags": tags,
                    "url": f"https://ollama.com{a_tag['href']}"
                })
        
        return models
    except Exception as e:
        print(f"Scraper error: {e}")
        return []
