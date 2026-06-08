import re
with open('docs/毕业论文初稿.md', 'r', encoding='utf-8') as f:
    text = f.read()

chapters = re.split(r'^## ', text, flags=re.MULTILINE)
for ch in chapters:
    if not ch.strip():
        continue
    title = ch.split('\n')[0].strip()
    chars = len(re.findall(r'[\u4e00-\u9fff]', ch))
    print(f'{chars:5d} chars - {title[:40]}')
