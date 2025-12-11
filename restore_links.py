
import glob
import os

CONTENT_DIR = "c:\\work\\hugo-sites\\my-affiliate-site1\\content\\posts"

replacements = {
    "/posts/2025/08/kindle-vs-kobo/": "/posts/kindle-vs-kobo/",
    "/posts/2025/08/kindle-paperwhite-review/": "/posts/kindle-paperwhite-review/",
    "/posts/2025/08/kobo-clara-review/": "/posts/kobo-clara-review/",
}

count = 0

print("Replacing links...")
for filepath in glob.glob(os.path.join(CONTENT_DIR, "*.md")):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements.items():
        if old in new_content:
            new_content = new_content.replace(old, new)
            
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {os.path.basename(filepath)}")
        count += 1

print(f"Finished. Updated {count} files.")
