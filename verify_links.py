
import glob
import re
import os
import urllib.parse
from datetime import datetime

CONTENT_DIR = "c:\\work\\hugo-sites\\my-affiliate-site1\\content\\posts"

def parse_frontmatter(content):
    meta = {}
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            yaml_content = content[3:end]
            for line in yaml_content.split('\n'):
                if ':' in line:
                    key, val = line.split(':', 1)
                    val = val.strip().strip('"').strip("'")
                    meta[key.strip()] = val
    return meta

def get_date_from_filename(filename):
    match = re.match(r'(\d{4}-\d{2}-\d{2})', filename)
    if match:
        return match.group(1)
    return None

valid_urls = set()
file_info = {}

print("Scanning files...")
for filepath in glob.glob(os.path.join(CONTENT_DIR, "*.md")):
    filename = os.path.basename(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    meta = parse_frontmatter(content)
    
    date_str = meta.get('date')
    if not date_str:
        date_str = get_date_from_filename(filename)
    
    slug = meta.get('slug')
    explicit_url = meta.get('url')
    
    if explicit_url:
        if not explicit_url.endswith('/'):
            explicit_url += '/'
        valid_urls.add(explicit_url)
        file_info[filepath] = explicit_url
    else:
        if not slug:
            name_part = filename.replace('.md', '')
            match = re.match(r'\d{4}-\d{2}-\d{2}-(.+)', name_part)
            if match:
                slug = match.group(1)
            else:
                slug = name_part
                
        if date_str:
            try:
                year = date_str[0:4]
                month = date_str[5:7]
                url = f"/posts/{year}/{month}/{slug}/"
                valid_urls.add(url)
                file_info[filepath] = url
            except:
                print(f"Error parsing date {date_str} in {filename}")

print(f"Found {len(valid_urls)} valid URLs.")

print("\nChecking links...")
broken_links = []

for filepath in glob.glob(os.path.join(CONTENT_DIR, "*.md")):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # regex for markdown links [text](/posts/...)
    links = re.findall(r'\[.*?\]\((/posts/[^)]+)\)', content)
    
    for link in links:
        link_clean = link.split('#')[0]
        if not link_clean.endswith('/'):
            link_clean += '/'
            
        # Decode url for comparison (e.g. %E3%81%... -> characters)
        # Actually Hugo typically deals in the internal encoded/decoded representation differently depending on config.
        # But usually Japanese slugs in frontmatter are one thing, and the permalink might be another.
        # Let's try to match both.
        
        link_decoded = urllib.parse.unquote(link_clean)
        
        if link_clean not in valid_urls and link_decoded not in valid_urls:
             broken_links.append((os.path.basename(filepath), link, link_clean))

if broken_links:
    print(f"\nFound {len(broken_links)} Broken Links:")
    for filename, original_link, clean_link in broken_links:
        print(f"File: {filename}")
        print(f"  Link: {original_link}")
else:
    print("No broken links found.")
