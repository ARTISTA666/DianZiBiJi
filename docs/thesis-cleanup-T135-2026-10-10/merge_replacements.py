from pathlib import Path
import json, shutil

ROOT = Path(__file__).resolve().parent
TEMP = Path('/tmp/thesis-T135')
source = json.loads((ROOT/'paragraphs.json').read_text())
by_p = {r['p']: r['text'] for r in source}
approved = {}
for name in ['prose-1-5.json', 'prose-6-7.json', 'prose-appendix.json']:
    data = json.loads((TEMP/name).read_text())
    shutil.copy2(TEMP/name, ROOT/name)
    rows = data if isinstance(data, list) else data.get('candidates', data.get('replacements', data.get('changes')))
    assert isinstance(rows, list), name
    for row in rows:
        if 'original' in row: row['old'] = row.pop('original')
        assert by_p[row['p']] == row['old'], (name, row['p'])
        approved[row['p']] = row

def set_change(p, new, reason, action='replace'):
    approved[p] = {'p': p, 'old': by_p[p], 'new': new, 'action': action, 'reason': reason}

for p, companion in [(777, 778), (1041, 1042)]:
    approved.pop(companion, None)
    set_change(p, '', '删除整行重复免责声明；保留表中实际输入、结果、来源编号。', 'delete_row')

for p in [158, 3560]:
    set_change(p, by_p[p].replace('本轮性能', '性能'), '移除论文标题中的本轮内部工作口吻。')
set_change(3574, '基线bbe72eb', '保留测试基线标识，删除工作树未提交状态的制作说明。')
set_change(1684, by_p[1684].replace('论文仍有不足，我会带着在这段经历中形成的审慎态度继续学习。', ''), '删除致谢结尾的自我辩护句，保留完整感谢内容。')
set_change(1155, by_p[1155].replace('GSE111619扩展批次未绑定代码版本。', ''), '迁移前Python原型与当前Rust已明确分列，删除重复的代码绑定缺口说明。')
set_change(936, by_p[936].replace('本轮图谱与问答实验', '图谱与问答实验'), '数据构造与输入类型保持，移除内部工作口吻。')
set_change(1170, '附录D.3展示PCR、细胞活力、Western Blot及qPCR四条固定合成笔记和七份SOP提要。历史问答批次共使用15条笔记。', '保留合成样本性质与数量，删除逐字段一致、逐字一致和内部制作来源重复说明。')
set_change(758, '资料方法与适用条件使用[F]；[N]说明项目自身实验；当前为模板定义阶段', '保留输出规则与实际阶段，改用正向状态替代未验证免责。')
set_change(763, '每条事实紧邻对应[N]；缺少单位或验证条件须人工确认；当前为模板定义阶段', '保留人工确认条件与实际阶段，改用正向状态替代未验证免责。')
set_change(1221, '可查看账号、小组、成员状态与审计记录', '将可核验修饰改为具体的查看操作。')
set_change(1683, by_p[1683].replace('交流使我有机会从不同角度重新审视自己的表述，也提醒我把尚未说明清楚的地方继续梳理。', '交流使我有机会从不同角度梳理研究思路与论文表达。'), '保留学术交流致谢，去掉结尾未说明清楚的自我解释。')
set_change(1676, '（1）独立复核参考规则。52条参考关系来自四条合成笔记，新12题及前置规则由AI编制。后续扩充记录，复核关系和答案参考并重复验证。', '保留规则来源和独立复核方向，收紧重复展望表述，避免章节尾部两行单独占页。')
set_change(1677, '（2）扩充样本并统一评价。旧20题单次生成、事后评分，修复前3题含误抽关系；新12题各重复三次。GPT为未经校准的单次评价，与DeepSeek RAGAS指标不同；另两种RAG尚未自动评分。后续统一指标，扩充题集并开展多模型重复评价，报告一致性与失败。', '保留全部样本规模、评价次数和指标差异，用紧凑表述集中说明后续评价工作。')
set_change(1678, '（3）改进复杂检索与证据支持。一跳检索难以处理指代、时间、计数与聚合，归档评价中召回提高而忠实度下降。后续完善中文匹配、分组聚合与固定任务逐结论核验，在相同语料、预算和规则下比较有限多跳、GraphRAG及LightRAG。', '保留检索问题、忠实度下降和同条件比较方向，精简重复表达以改善章节尾部分页。')
set_change(1679, '（4）补充异常处理与性能评价。对合并冲突、主动推送、跨项目数量隔离和上游失败写入开展专项测试，核对退回动作枚举与重抽后的停滞天数，完善优先级、预警与事件记录，并在明确规模和并发条件下观测性能。', '计划覆盖含义已在方法章说明，删除展望中的重复方法句；保留全部异常核对、优先级、预警和性能观测方向。')
for p, text in by_p.items():
    if p < 160 and '6.4 多角色流程走查记录复核' in text:
        set_change(p, text.replace('6.4 多角色流程走查记录复核', '6.4 多角色协作流程验证'), '目录标题与正文同步。')

for row in approved.values():
    assert row['old'] == by_p[row['p']]
    assert row['new'] != row['old'], row['p']
(ROOT/'approved-replacements.json').write_text(json.dumps(sorted(approved.values(), key=lambda x:x['p']), ensure_ascii=False, indent=2))
for name in ['prose-appendix-audit.json', 'svg-protection-audit.json']:
    if (TEMP/name).exists(): shutil.copy2(TEMP/name, ROOT/name)
print(json.dumps({'approved_changes':len(approved)}, ensure_ascii=False))
