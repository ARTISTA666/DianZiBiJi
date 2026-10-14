> status: current
> owner: Codex（论文格式工具）

# AHNU 范文复刻版 v2

面向本仓库增强版 Markdown 的可复现 PDF 排版入口。按作者提供的魏潘晨硕士论文实测版式，在原 GitHub 项目 **ChineseResearchLaTeX / bensz-thesis / thesis-ahnu-master** 上加专用覆盖样式。原引擎、AHNU profile、原样式和校名字样独立保存，5 个来源文件的 SHA-256 见 `template/upstream-manifest.json`；不再裁剪为另一套引擎。

## 使用

依赖 Python 3.9+、Pandoc、XeLaTeX、latexmk、Poppler；TeX 安装需含 ctex、fontspec、xeCJK、adjustbox、booktabs、longtable、caption、tikz、titletoc 等常见宏包。已在 macOS 实际构建。

在仓库根执行：

```bash
python3 tools/ahnu-thesis/build.py
python3 -m unittest discover -s tools/ahnu-thesis -p 'test_*.py'
```

自定义输入和元数据：

```bash
python3 tools/ahnu-thesis/build.py \
  --source docs/毕业论文重构稿-创新点增强版.md \
  --metadata tools/ahnu-thesis/metadata.json \
  --output output/ahnu-thesis
```

`--prepare-only` 只生成 TeX。`--strict` 在缺少作者/导师/研究方向/提交及扉页日期、使用替代字体或尚未编译 PDF 时非零退出；缺字、文字越界在普通模式也会失败。strict 通过只代表这些机器检查通过，不等于学校认证或论文内容验收。

每次构建生成独立时间戳目录，包含 `main.pdf`、源稿快照 `source.md`、完整 TeX 和图片、日志、`report.json`。不会覆写论文、旧 PDF 或其他人的 `/tmp` 工程。报告记录输入/图片/实现哈希、工具版本、字体替代、缺字和越界、摘要汉字计数、构建期间源稿是否变化。并线写作时，PDF 对应其快照，不能用文件名判断是否包含另一条线的最新改动。

元数据为纯文本 JSON，TeX 特殊字符自动转义；换行写成 JSON 的 `\n`。`ahnuTitlePageZh` 仅控制扉页题名断行，改标题时应与 `ahnuTitleZh` 同步。作者、导师、方向和日期目前留白；不复制范文的个人信息。

## 本版复刻内容

- A4、四边 2.8 cm；正文 12bp 宋体、20bp 基线、首行 24bp；章标题 18bp 宋体加粗，二/三级标题 14bp 黑体。
- 原校名位图、封面字距与字段下划线、带边框扉页；不再加入自制签名预览页。
- 页顶仅保留 0.7bp 横线，页码 9bp 居中；目录无页眉页码。前置罗马页码连续计数，正文重新从 1 开始。
- 摘要标题和正文位置、两级目录的 14bp 字号/18bp 行距/点引导线、章标题留白按范文测量调整。
- 图表题 10.5bp 加粗，表内 10.5bp/15bp；数据表三线，表 6-3 功能测试表全框线并加粗，跨页保留表头。
- 文中数字引文上标；数学表达式和 `[0,1]` 区间保留。参考文献采用 12bp/20bp、左对齐小标题、悬挂条目；保留源稿的完整著录文字和 118 个原编号，不以旧 BibTeX 覆写。
- 长代码标识符添加不可见断行点，TikZ 等比例限制在版心，截图和图题同页；图片必须存在，不生成占位框。
- 章末短小结预留整段分页空间，避免一行孤落到下一页。
- 章节动态提取并检查连续性；重复或未知顶层章节报错，附录仅输出一次。保留本论文现有致谢和附录，不为迎合范文删内容。

关键文件：`template/ahnu-reference.sty` 是实测样式覆盖层，`reference-profile.json` 保存范文测量依据，`build.py` 管构建与检查，`convert.py` 和 `merge_captions.py` 复用原论文转换修补。

## 适用范围和差异

这是本论文专用适配器。转换器包含本论文的表题映射、列宽覆盖，以及表 6-3 的特殊表格样式；章节或表号调整后需同步这些规则并重新看 PDF。图片映射为 `assets/screenshots/` → `docs/user-guide-assets/`、`assets/innovation-screenshots/` → `docs/innovation/screenshots/`。输入支持原生 LaTeX/TikZ，按受信任本地论文处理。

范文字体为 SimSun/SimHei，工具优先选用；本机缺失时采用 Songti SC/Heiti SC，字形和断行可能有细微区别，字体不随工具分发。范文 PDF 缺少罗马 II/IV 对应的背页，本版不复制跳号。三位数文献编号使用 30bp 悬挂缩进（范文两位数约 24bp）。本版未复制知网水印，也不补造范文没有显示的签名页。

输出为 PDF；DOCX、学校签名材料、独立 B5 详细摘要等不在此构建入口中。中文摘要仍沿用源稿，机器计数超过 1000 汉字会提示，不通过排版删改论文。

[本版验收与对照](../../docs/论文范文复刻版验收-2026-09-14.md)；[前期官方规范和项目调研（历史）](../../archive/thesis-format/论文格式专用版调研与验收-2026-09-13.md)。

## 来源与许可证

[ChineseResearchLaTeX / thesis-ahnu-master](https://github.com/huangwb8/ChineseResearchLaTeX/tree/main/projects/thesis-ahnu-master) 为 MIT，完整许可保留在 `LICENSE.upstream.txt`。本地导入源为本轮开始时 `/tmp/crlt/projects/thesis-ahnu-master` 中已有修补的工程，未核验其上游 commit，因此以保存的实际文件哈希固定基线。复制后保持基线文件不变，样式改动仅在覆盖层。

转换器及表题合并器派生自 `reviews/round-04/convert-enhanced.py`、`merge-captions.py`；历史脚本不修改。用户范文只作本地测量，不随项目分发。
