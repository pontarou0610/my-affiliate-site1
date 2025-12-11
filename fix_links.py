
import glob
import re
import os
import urllib.parse

CONTENT_DIR = "c:\\work\\hugo-sites\\my-affiliate-site1\\content\\posts"

# Helper to parse frontmatter quickly
def get_frontmatter_value(content, key):
    # Regex for "key: value" or 'key: "value"'
    match = re.search(r'^' + key + r':\s*(.+)$', content, re.MULTILINE)
    if match:
        val = match.group(1).strip().strip('"').strip("'")
        return val
    return None

def get_date_from_filename(filename):
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match:
        return match.group(1)
    return None

print("Building URL map...")
valid_urls = set()
slug_to_url = {}
simplified_slug_to_url = {}

# Pass 1: Build Map
for filepath in glob.glob(os.path.join(CONTENT_DIR, "*.md")):
    filename = os.path.basename(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    slug = get_frontmatter_value(content, 'slug')
    date_str = get_frontmatter_value(content, 'date')
    
    if not date_str:
        date_str = get_date_from_filename(filename)
    
    if not slug:
        name_part = filename.replace('.md', '')
        date_match = re.match(r'\d{4}-\d{2}-\d{2}-(.+)', name_part)
        if date_match:
            slug = date_match.group(1)
        else:
            slug = name_part
            
    if date_str and slug:
        try:
            year = date_str[0:4]
            month = date_str[5:7]
            
            url = f"/posts/{year}/{month}/{slug}/"
            valid_urls.add(url)
            slug_to_url[slug] = url
            
            # Create simplified slug (remove leading digits and hyphen)
            # e.g. 1-foo -> foo
            simple_slug = re.sub(r'^\d+-', '', slug)
            if simple_slug != slug:
                simplified_slug_to_url[simple_slug] = url
                
        except:
            print(f"Skipping {filename}: Bad date {date_str}")
    else:
        pass

print(f"Mapped {len(slug_to_url)} slugs.")
print(f"Mapped {len(simplified_slug_to_url)} simplified slugs.")

# Pass 2: Fix Links
print("\nFixing links...")
fixed_count = 0
files_changed = 0

for filepath in glob.glob(os.path.join(CONTENT_DIR, "*.md")):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    
    # Regex to find links. logic: [text](url)
    def replace_link(match):
        full_match = match.group(0) # [text](url)
        text = match.group(1)
        url = match.group(2)
        
        # Clean URL
        url_clean = url.split('#')[0]
        if not url_clean.endswith('/'):
            url_clean += '/'
            
        # Check if already valid
        if url_clean in valid_urls:
            return full_match
            
        # Try to fix
        if url_clean.startswith("/posts/"):
            # Extract potential slug parts
            # Case 1: /posts/slug/  (missing date)
            # Case 2: /posts/YYYY/MM/slug/ (wrong slug?)
            
            parts = url_clean.split('/')
            parts = [p for p in parts if p] # remove empty strings
            
            # potential slug is the last part
            if parts:
                slug_candidate = parts[-1]
                slug_decoded = urllib.parse.unquote(slug_candidate)
                
                # Check exact match
                if slug_decoded in slug_to_url:
                    return f"[{text}]({slug_to_url[slug_decoded]})"
                
                # Check simplified match
                if slug_decoded in simplified_slug_to_url:
                    return f"[{text}]({simplified_slug_to_url[slug_decoded]})"
                    
                # Check if the candidate itself has a prefix that shouldn't be there?
                # or if we should strip prefix from candidate?
                simple_candidate = re.sub(r'^\d+-', '', slug_decoded)
                if simple_candidate in simplified_slug_to_url:
                     return f"[{text}]({simplified_slug_to_url[simple_candidate]})"
                if simple_candidate in slug_to_url:
                     return f"[{text}]({slug_to_url[simple_candidate]})"

        return full_match

    new_content = re.sub(r'\[([^\]]+)\]\((/posts/[^)]+)\)', replace_link, content)
    
    if new_content != content:
        print(f"Update: {os.path.basename(filepath)}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        files_changed += 1

print(f"\nDone. Files updated: {files_changed}")
