import re
with open('docs/毕业论文初稿.md', 'r', encoding='utf-8') as f:
    text = f.read()

refs = set()
for m in re.finditer(r'\[(\d+)\]', text):
    refs.add(int(m.group(1)))
for m in re.finditer(r'\[(\d+)-(\d+)\]', text):
    for i in range(int(m.group(1)), int(m.group(2))+1):
        refs.add(i)

print(f'Max ref: {max(refs)}')
print(f'Min ref: {min(refs)}')
print(f'All refs: {sorted(refs)}')

high = [r for r in sorted(refs) if r > 20]
if high:
    print(f'\nWARNING: refs > 20 exist: {high}')
    lines = text.split('\n')
    for r in high:
        for i, line in enumerate(lines, 1):
            if f'[{r}]' in line or f'[{r}-' in line:
                print(f'  Line {i}: {line.strip()[:80]}')
else:
    print('\nOK: all refs within 1-20')

# Count Chinese chars (excluding code blocks and tables)
clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
chinese = len(re.findall(r'[\u4e00-\u9fff]', clean))
print(f'\nChinese chars: {chinese}')
print(f'Shortfall: {max(0, 30000 - chinese)}')
