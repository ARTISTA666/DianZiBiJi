import re
with open('docs/毕业论文初稿.md', 'r', encoding='utf-8') as f:
    text = f.read()

chapters = re.split(r'^## ', text, flags=re.MULTILINE)
print(f"{'Chapter':<30} {'Chars':>6} {'Status':>10}")
print("-" * 46)
total = 0
for ch in chapters:
    if not ch.strip(): continue
    title = ch.split('\n')[0].strip()[:30]
    chars = len(re.findall(r'[\u4e00-\u9fff]', ch))
    total += chars
    need = 'NEED EXPAND' if chars < 2000 and '摘要' not in title and 'Abstract' not in title and '参考文献' not in title and '附录' not in title else ''
    print(f'{title:<30} {chars:>6} {need:>10}')
print("-" * 46)
print(f'{TOTAL:<30} {total:>6}')
