import re

with open('docs/毕业论文初稿.md', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
total_chars = len(text.strip())

print(f'CHINESE_CHARS: {chinese_chars}')
print(f'TOTAL_CHARS: {total_chars}')
print(f'SHORTFALL: {max(0, 30000 - chinese_chars)}')

# References
refs = re.findall(r'^\[(\d+)\]', text, re.MULTILINE)
print(f'REF_COUNT: {len(refs)}')
print(f'REF_NEEDED: {max(0, 80 - len(refs))}')

# Year distribution
print('--- YEAR DISTRIBUTION ---')
for i in range(1, 21):
    m = re.search(rf'\[{i}\]\s.*?(\d{{4}})', text)
    if m:
        year = m.group(1)
        note = ''
        if int(year) <= 2020:
            note = ' (classic)'
        elif int(year) >= 2023:
            note = ' (recent)'
        else:
            note = ' (2021-2022)'
        print(f'  [{i}] {year}{note}')
