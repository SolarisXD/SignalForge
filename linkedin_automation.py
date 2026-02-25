import os
import json
import subprocess
import requests
from datetime import datetime
from dotenv import load_dotenv

# --- Load topics from topics.json ---
TOPICS_FILE = os.path.join(os.path.dirname(__file__), 'topics.json')
def load_topics():
    with open(TOPICS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# --- Configuration ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.env')
load_dotenv(CONFIG_PATH)

NOTION_TOKEN = os.getenv('NOTION_TOKEN')
DATABASE_ID = os.getenv('DATABASE_ID')
MODEL_NAME = os.getenv('MODEL_NAME', 'mistral')
HISTORY_FILE_PATH = os.getenv('HISTORY_FILE_PATH', 'used_topics.json')
MAX_WORD_LIMIT = int(os.getenv('MAX_WORD_LIMIT', 220))

TOPICS = load_topics()

# --- Update Notion Bucket property options ---
def update_notion_bucket_options():
    url = f'https://api.notion.com/v1/databases/{DATABASE_ID}'
    headers = {
        'Authorization': f'Bearer {NOTION_TOKEN}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    # Get current properties
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f'Failed to fetch database properties: {resp.status_code} {resp.text}')
        return False
    db = resp.json()
    properties = db['properties']
    if 'Bucket' not in properties or properties['Bucket']['type'] != 'select':
        print('Bucket property missing or not a select type.')
        return False
    # Build new options
    new_options = [{'name': bucket} for bucket in TOPICS.keys()]
    # Patch Bucket property
    patch_url = f'https://api.notion.com/v1/databases/{DATABASE_ID}'
    patch_data = {
        'properties': {
            'Bucket': {
                'select': {
                    'options': new_options
                }
            }
        }
    }
    patch_resp = requests.patch(patch_url, headers=headers, json=patch_data)
    if patch_resp.status_code != 200:
        print(f'Failed to update Bucket options: {patch_resp.status_code} {patch_resp.text}')
        return False
    print('Bucket options updated in Notion.')
    return True

# --- Utility Functions ---
def load_history():
    if not os.path.exists(HISTORY_FILE_PATH):
        with open(HISTORY_FILE_PATH, 'w') as f:
            json.dump([], f)
        return []
    try:
        with open(HISTORY_FILE_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        # Corrupted file, reset
        with open(HISTORY_FILE_PATH, 'w') as f:
            json.dump([], f)
        return []

def save_history(history):
    with open(HISTORY_FILE_PATH, 'w') as f:
        json.dump(history, f, indent=2)

def get_next_topic(history):
    all_topics = []
    for bucket, topics in TOPICS.items():
        for topic_obj in topics:
            if isinstance(topic_obj, dict):
                all_topics.append((bucket, topic_obj['topic']))
            else:
                all_topics.append((bucket, topic_obj))
    used = set(tuple(x) for x in history)
    import random
    unused = [x for x in all_topics if x not in used]
    if not unused:
        # Reset cycle
        save_history([])
        unused = all_topics
    return random.choice(unused)

def validate_post(text):
    # Structure: must have at least 3 bullet points and a closing line
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    bullet_count = sum(1 for l in lines if l.startswith('-'))
    if bullet_count < 3:
        return False, 'Not enough actionable bullet points.'
    if len(lines) < bullet_count + 2:  # Require at least intro/insight, bullets, closing
        return False, 'Not enough structure (intro, bullets, closing).'
    if any(char in text for char in '😀😁😂🤣😃😄😅😆😉😊😋😎😍😘🥰😗😙😚🙂🤗🤩🤔🤨😐😑😶🙄😏😣😥😮🤐😯😪😫😴😌😛😜😝🤤😒😓😔😕🙃🤑😲☹️🙁😖😞😟😤😢😭😦😧😨😩🤯😬😰😱🥵🥶😳🤪😵😡😠🤬😷🤒🤕🤢🤮🥴😇🥳🥺🤠🤡🤥🤫🤭🧐🤓😈👿👹👺💀👻👽👾🤖😺😸😹😻😼😽🙀😿😾'):
        return False, 'Emojis detected.'
    if len(text.split()) > MAX_WORD_LIMIT:
        return False, 'Word count exceeds limit.'
    return True, ''

def generate_post(topic, bucket):
    # Fetch instructions from instructions.md
    instructions_path = os.path.join(os.path.dirname(__file__), 'instructions.md')
    with open(instructions_path, 'r', encoding='utf-8') as f:
        instructions = f.read()
    prompt = instructions.replace('{topic}', topic).replace('{MAX_WORD_LIMIT}', str(MAX_WORD_LIMIT))
    try:
        result = subprocess.run(
            ['ollama', 'run', MODEL_NAME],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=150
        )
        if result.returncode != 0:
            raise RuntimeError(f"Ollama error: {result.stderr.strip()}")
        output = result.stdout.strip()
        valid, reason = validate_post(output)
        if not valid:
            raise ValueError(f"Generated post invalid: {reason}")
        return output
    except FileNotFoundError:
        print('Ollama not installed. Please install Ollama.')
        exit(1)
    except Exception as e:
        print(f'Post generation failed: {e}')
        exit(1)

def save_to_notion(topic, bucket, content):
    url = 'https://api.notion.com/v1/pages'
    headers = {
        'Authorization': f'Bearer {NOTION_TOKEN}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    # Find image URL for topic
    image_url = None
    for topic_obj in TOPICS[bucket]:
        if isinstance(topic_obj, dict) and topic_obj.get('topic') == topic:
            image_url = topic_obj.get('image')
            break
    children = []
    if image_url:
        children.append({
            'object': 'block',
            'type': 'image',
            'image': {
                'type': 'external',
                'external': {'url': image_url}
            }
        })
    children.append({
        'object': 'block',
        'type': 'paragraph',
        'paragraph': {
            'rich_text': [
                {'type': 'text', 'text': {'content': content}}
            ]
        }
    })
    data = {
        'parent': {'database_id': DATABASE_ID},
        'properties': {
            'Title': {'title': [{'text': {'content': topic}}]},
            'Date': {'date': {'start': datetime.now().strftime('%Y-%m-%d')}},
            'Status': {'select': {'name': 'Draft'}},
            'Bucket': {'select': {'name': bucket}}
        },
        'children': children
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code != 200:
        print(f'Notion API error: {resp.status_code} {resp.text}')
        return False
    return True

def main():
    update_notion_bucket_options()
    history = load_history()
    bucket, topic = get_next_topic(history)
    print(f'Generating post for topic: {topic} (bucket: {bucket})')
    post = generate_post(topic, bucket)
    print('Saving to Notion...')
    if save_to_notion(topic, bucket, post):
        history.append([bucket, topic])
        save_history(history)
        print('Draft saved to Notion and history updated.')
    else:
        print('Failed to save to Notion. Topic not marked as used.')

if __name__ == '__main__':
    main()
