import os
import re
import frontmatter
from pathlib import Path
from datetime import date, datetime

# Configuration
CONTENT_DIR = r"c:\work\hugo-sites\my-affiliate-site1\content"
PERMALINK_FORMAT = "/posts/{year}/{month}/{slug}/"
BASE_URL = "https://pontarou0610.github.io/my-affiliate-site1/"

def get_all_md_files(content_dir):
    return list(Path(content_dir).rglob("*.md"))

def parse_hugo_file_info(file_path):
    try:
        post = frontmatter.load(file_path)
        metadata = post.metadata
        
        # Determine Slug/ID
        slug = metadata.get('slug')
        if not slug:
            # Fallback to filename without extension
            slug = file_path.stem
        
        # Determine Title
        title = metadata.get('title', slug)
        
        # Determine Date for permalink
        date_obj = metadata.get('date')
        if isinstance(date_obj, (datetime, date)):
            year = date_obj.strftime("%Y")
            month = date_obj.strftime("%m")
        elif isinstance(date_obj, str):
            # Try parsing rough formats
            try:
                dt = datetime.strptime(date_obj[:10], "%Y-%m-%d")
                year = dt.strftime("%Y")
                month = dt.strftime("%m")
            except Exception:
                year = "0000"
                month = "00"
        else:
            year = "0000"
            month = "00"

        # Determine URL (explicit or generated)
        url = metadata.get('url')
        if not url:
            if "posts" in file_path.parts:
                url =PERMALINK_FORMAT.format(year=year, month=month, slug=slug)
            elif "lp" in file_path.parts:
                url = f"/lp/{slug}/"
            else:
                url = f"/{slug}/"
        
        # Normalize URL: ensure leading slash, remove trailing slash for comparison
        url = "/" + url.strip("/")
        
        return {
            "path": file_path,
            "url": url,
            "aliases": metadata.get('aliases', []),
            "slug": slug,
            "title": title
        }
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None

def find_broken_links():
    files = get_all_md_files(CONTENT_DIR)
    
    # Build a map of valid URLs
    valid_urls = set()
    file_map = {} # Url -> FilePath
    
    # Also add generated valid URLs
    print("Building URL map...")
    for f in files:
        info = parse_hugo_file_info(f)
        if info:
            valid_urls.add(info['url'])
            file_map[info['url']] = info['path']
            # Add aliases
            for alias in info['aliases']:
                alias = "/" + alias.strip("/")
                valid_urls.add(alias)
                file_map[alias] = info['path']

    # Add some static known paths
    valid_urls.add("/lp/kindle")
    valid_urls.add("/lp/kobo")
    valid_urls.add("/posts")
    valid_urls.add("/tags")
    valid_urls.add("/categories")
    valid_urls.add("/about")
    valid_urls.add("/contact")
    valid_urls.add("/legal/disclosure")
    valid_urls.add("/")

    print(f"Found {len(valid_urls)} valid internal URLs.")

    # Scan for links
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    broken_links = []
    relref_pattern = re.compile(
        r'^\{\{[<%]\s*(?:relref|ref)\s+(?:"([^"]+)"|\'([^\']+)\'|([^\\s>]+))\s*[>%]\}\}$'
    )

    print("Scanning files for broken links...")
    for f in files:
        with open(f, 'r', encoding='utf-8') as file_content:
            text = file_content.read()
            
        matches = link_pattern.findall(text)
        for text, link in matches:
            # Skip external links
            if link.startswith("http") and BASE_URL not in link:
                continue

            # Handle Hugo ref/relref shortcodes inside markdown links.
            if "{{" in link:
                relref_match = relref_pattern.match(link.strip())
                if relref_match:
                    link = next((g for g in relref_match.groups() if g), link)
                else:
                    # If we can't resolve it safely, don't report as broken.
                    continue
            
            # Skip anchor links on same page
            if link.startswith("#"):
                continue

            # Skip email / telephone links
            if link.startswith(("mailto:", "tel:")):
                continue

            # Normalize internal link
            target = link
            if target.startswith(BASE_URL):
                target = target.replace(BASE_URL, "/")
            
            target = target.split("#")[0] # Remove anchor
            target = target.split("?")[0] # Remove query params
            target = "/" + target.strip("/")
            
            # Check if valid
            if target not in valid_urls:
                # Special check for /images/ (not checking static files existence in this script but assuming valid if pattern matches)
                if target.startswith("/images/"):
                    continue
                
                # Report broken link
                broken_links.append({
                    "source": f,
                    "text": text,
                    "link": link,
                    "normalized": target
                })

    return broken_links

if __name__ == "__main__":
    broken = find_broken_links()
    
    if broken:
        print(f"\nFound {len(broken)} potentially broken links:\n")
        for b in broken:
            print(f"Source: {b['source']}")
            print(f"  Link: [{b['text']}]({b['link']})")
            print(f"  Target (normalized): {b['normalized']}")
            print("-" * 40)
    else:
        print("\nNo broken links found!")
