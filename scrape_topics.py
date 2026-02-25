import requests
import json
import os
import subprocess
from bs4 import BeautifulSoup

# --- Configuration ---
RESTRICTIONS_PATH = os.path.join(os.path.dirname(__file__), 'scrape_restrictions.json')
TOPICS_PATH = os.path.join(os.path.dirname(__file__), 'topics.json')

# --- Load restrictions ---
def load_restrictions():
    with open(RESTRICTIONS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- Scrape topics from allowed sources ---


def scrape_topics_from_web(buckets, restrictions):
    allowed_sources = restrictions['allowed_sources']
    keywords = restrictions.get('keywords', [])
    exclude = restrictions.get('exclude', [])
    scraped = {}
    for bucket in buckets:
        scraped[bucket] = []
        urls = allowed_sources.get(bucket, [])
        for url in urls:
            try:
                resp = requests.get(url, timeout=20)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, 'html.parser')
                for tag in soup.find_all(['h2', 'li']):
                    text = tag.get_text(strip=True)
                    if any(kw.lower() in text.lower() for kw in keywords) and not any(ex.lower() in text.lower() for ex in exclude):
                        if len(text) < 20:
                            continue
                        if any(ex.lower() in text.lower() for ex in exclude):
                            continue
                        img_url = None
                        img_tag = tag.find_previous('img') or tag.find_next('img')
                        if img_tag:
                            img_url = img_tag.get('src')
                        if not any(t['topic'] == text for t in scraped[bucket]):
                            scraped[bucket].append({'topic': text, 'image': img_url})
            except Exception as e:
                print(f'Error scraping {url}: {e}')
    return scraped

def generate_topics_with_llm(buckets, model='mistral', n=10):
    topics = {}
    for bucket in buckets:
        prompt = (
            f"Generate {n} unique, non-generic, specific LinkedIn post topics for the bucket '{bucket}'. "
            "Avoid generic phrases, buzzwords, and repetition. Return only a plain list, one topic per line."
        )
        try:
            result = subprocess.run(
                ['ollama', 'run', model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90
            )
            if result.returncode != 0:
                print(f"Ollama error for bucket {bucket}: {result.stderr.strip()}")
                topics[bucket] = []
                continue
            lines = [l.strip('- ').strip() for l in result.stdout.split('\n') if l.strip()]
            unique = []
            for t in lines:
                if len(t) < 20:
                    continue
                if t not in unique:
                    unique.append(t)
            topics[bucket] = [{"topic": t, "image": None} for t in unique]
        except Exception as e:
            print(f"Error generating topics for {bucket}: {e}")
            topics[bucket] = []
    return topics

# --- Update topics.json ---
def update_topics(scraped):
    with open(TOPICS_PATH, 'w', encoding='utf-8') as f:
        json.dump(scraped, f, indent=2, ensure_ascii=False)
    print('topics.json updated.')

if __name__ == '__main__':
    buckets = ["career", "ai", "discipline", "personal_brand"]
    restrictions = load_restrictions()
    # Get topics from both LLM and web scraping
    llm_topics = generate_topics_with_llm(buckets)
    web_topics = scrape_topics_from_web(buckets, restrictions)
    # Merge, deduplicate, prefer image from web if available
    merged = {}
    for bucket in buckets:
        merged[bucket] = []
        seen = set()
        # Add web topics first (with images)
        for t in web_topics.get(bucket, []):
            merged[bucket].append(t)
            seen.add(t['topic'])
        # Add LLM topics if not already present
        for t in llm_topics.get(bucket, []):
            if t['topic'] not in seen:
                merged[bucket].append(t)
                seen.add(t['topic'])
    update_topics(merged)
