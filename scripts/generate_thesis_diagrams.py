"""Generate thesis diagrams as maintainable SVG assets."""

from __future__ import annotations

from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "user-guide-assets"
W, H = 1600, 900


def lines(text: str, x: int, y: int, *, size: int = 24, fill: str = "#3f5368",
          weight: int = 400, anchor: str = "middle", gap: int = 36) -> str:
    parts = text.split("\n")
    tspans = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else gap}">{escape(part)}</tspan>'
        for i, part in enumerate(parts)
    )
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{tspans}</text>'
    )


def rect(x: int, y: int, w: int, h: int, *, fill: str = "#ffffff",
         stroke: str = "#8eafd0", rx: int = 18, sw: int = 2,
         shadow: bool = False, dash: str | None = None) -> str:
    attrs = f' filter="url(#shadow)"' if shadow else ""
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{attrs}/>'
    )


def arrow(x1: int, y1: int, x2: int, y2: int, *, color: str = "#547aa5",
          width: int = 4, dashed: bool = False, marker: bool = True) -> str:
    dash = ' stroke-dasharray="10 8"' if dashed else ""
    end = ' marker-end="url(#arrow)"' if marker else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round"{dash}{end}/>'
    )


def path_arrow(d: str, *, color: str = "#547aa5", width: int = 4,
               dashed: bool = False) -> str:
    dash = ' stroke-dasharray="10 8"' if dashed else ""
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"{dash} marker-end="url(#arrow)"/>'
    )


def circle(cx: int, cy: int, r: int, *, fill: str, stroke: str = "#ffffff",
           sw: int = 3) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"/>'
    )


def base(body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="5" result="blur"/>
      <feOffset in="blur" dx="0" dy="4" result="offsetBlur"/>
      <feFlood flood-color="#264766" flood-opacity="0.15" result="shadowColor"/>
      <feComposite in="shadowColor" in2="offsetBlur" operator="in" result="shadow"/>
      <feMerge><feMergeNode in="shadow"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
      <path d="M0,0 L12,6 L0,12 Z" fill="#547aa5"/>
    </marker>
  </defs>
  <rect width="{W}" height="{H}" fill="#ffffff"/>
  {body}
</svg>
"""


def role_permission() -> str:
    parts = [
        rect(55, 55, 1490, 790, fill="#f8fafc", stroke="#8aa7c2", rx=24),
        rect(85, 90, 620, 710, fill="#edf5fc", stroke="#7fa9d2", rx=22),
        rect(735, 90, 780, 710, fill="#f4f7fa", stroke="#9aaec0", rx=22),
        lines("系统级作用域", 395, 145, size=32, fill="#245b91", weight=700),
        lines("项目级作用域（按 project_id 隔离）", 1125, 145, size=32, fill="#245b91", weight=700),
        rect(170, 205, 450, 150, fill="#ffffff", stroke="#5686b5", shadow=True),
        lines("系统管理员  SUPER_ADMIN", 395, 255, size=28, fill="#173a5e", weight=700),
        lines("账号与全局角色 · 项目创建\n全局统计 · 跨项目运维", 395, 302, size=22),
        arrow(395, 355, 395, 410),
        rect(130, 435, 530, 245, fill="#ffffff", stroke="#9abada", shadow=True),
        lines("可管理", 395, 480, size=24, fill="#245b91", weight=700),
        lines("用户账号与状态\n全局角色\n任意项目异常处置", 395, 525, size=23, gap=40),
        rect(785, 205, 680, 110, fill="#ffffff", stroke="#5686b5", shadow=True),
        lines("项目负责人", 965, 250, size=27, fill="#173a5e", weight=700),
        lines("成员与配置管理\n项目内读 / 写 / 审核", 1270, 238, size=22, gap=34),
        rect(785, 345, 320, 125, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("审核人员", 945, 390, size=26, fill="#173a5e", weight=700),
        lines("读取 · 审核 · 评价", 945, 432, size=22),
        rect(1145, 345, 320, 125, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("普通成员", 1305, 390, size=26, fill="#173a5e", weight=700),
        lines("读取 · 编辑 · 智能生成", 1305, 432, size=22),
        rect(785, 500, 320, 125, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("只读成员", 945, 545, size=26, fill="#173a5e", weight=700),
        lines("仅查看授权项目", 945, 587, size=22),
        rect(1145, 500, 320, 125, fill="#fff7ed", stroke="#d99a51", shadow=True),
        lines("权限边界", 1305, 545, size=26, fill="#9a5a13", weight=700),
        lines("不可管理系统用户\n不可访问其他项目", 1305, 582, size=21, gap=33),
        rect(785, 665, 680, 90, fill="#eaf7f4", stroke="#65a99b"),
        lines("后端接口统一校验：读取 · 写入 · 审核 · 管理", 1125, 720,
              size=24, fill="#246b60", weight=700),
        '<line x1="720" y1="185" x2="720" y2="770" stroke="#d0832f" stroke-width="3" stroke-dasharray="10 8"/>',
        rect(640, 410, 160, 62, fill="#fff7ed", stroke="#d99a51", rx=14),
        lines("最小权限边界", 720, 450, size=18, fill="#a86318", weight=700),
    ]
    return base("\n".join(parts))


def trusted_loop() -> str:
    colors = ["#3f78ae", "#4f8f82", "#6d7db3", "#a56f43"]
    titles = ["可信输入", "结构化转化", "知识支撑问答", "结果回存"]
    descs = [
        "实验笔记创建\n审核通过后生效",
        "实体 / 关系抽取\n按项目隔离",
        "资料证据 [S]\n图谱证据 [G]",
        "回答 · 来源 · 评价\n审计日志与实验快照",
    ]
    xs = [90, 470, 850, 1230]
    parts = [
        rect(55, 65, 1490, 745, fill="#f8fafc", stroke="#8aa7c2", rx=26),
        rect(90, 100, 1420, 75, fill="#edf5fc", stroke="#7fa9d2", rx=16),
        lines("项目边界：身份校验与 project_id 贯穿全流程", 800, 150,
              size=29, fill="#245b91", weight=700),
    ]
    for i, x in enumerate(xs):
        parts.extend([
            rect(x, 250, 280, 310, fill="#ffffff", stroke=colors[i], shadow=True),
            circle(x + 140, 300, 38, fill=colors[i]),
            lines(str(i + 1), x + 140, 310, size=27, fill="#ffffff", weight=700),
            lines(titles[i], x + 140, 380, size=29, fill="#173a5e", weight=700),
            lines(descs[i], x + 140, 440, size=23, gap=42),
        ])
        if i < 3:
            parts.append(arrow(x + 285, 405, xs[i + 1] - 15, 405))
    parts.extend([
        path_arrow("M1370 575 C1370 735 230 735 230 575", color="#547aa5", width=4, dashed=True),
        rect(475, 650, 650, 90, fill="#eaf7f4", stroke="#65a99b", rx=18),
        lines("评价与审计结果反向支撑记录复核和知识更新", 800, 706,
              size=24, fill="#246b60", weight=700),
    ])
    return base("\n".join(parts))


def kg_schema() -> str:
    parts = [
        rect(45, 45, 1510, 810, fill="#f8fafc", stroke="#8aa7c2", rx=26),
        rect(90, 85, 1420, 70, fill="#edf5fc", stroke="#7fa9d2", rx=16),
        lines("九类实体、八类关系均携带项目编号与来源信息", 800, 132,
              size=28, fill="#245b91", weight=700),
        circle(235, 430, 82, fill="#3f78ae"),
        lines("项目", 235, 441, size=28, fill="#ffffff", weight=700),
        circle(710, 430, 105, fill="#4f8f82"),
        lines("实验笔记", 710, 440, size=29, fill="#ffffff", weight=700),
        arrow(322, 430, 590, 430),
        lines("包含笔记", 455, 398, size=20, fill="#52687d", weight=700),
        circle(1010, 235, 70, fill="#6d7db3"),
        lines("用户", 1010, 244, size=24, fill="#ffffff", weight=700),
        arrow(785, 355, 955, 275),
        lines("创建者", 870, 292, size=18, fill="#52687d", weight=700),
        circle(1325, 255, 70, fill="#6d7db3"),
        lines("附件资料", 1325, 264, size=23, fill="#ffffff", weight=700),
        arrow(808, 382, 1253, 277),
        lines("关联附件", 1105, 300, size=18, fill="#52687d", weight=700),
        circle(1350, 465, 70, fill="#6d7db3"),
        lines("实验类型", 1350, 474, size=23, fill="#ffffff", weight=700),
        arrow(820, 435, 1270, 460),
        lines("实验类型", 1080, 425, size=18, fill="#52687d", weight=700),
        circle(1300, 700, 70, fill="#b35f6d"),
        lines("实验结果", 1300, 709, size=23, fill="#ffffff", weight=700),
        arrow(795, 505, 1243, 655),
        lines("产生结果", 1080, 600, size=18, fill="#52687d", weight=700),
        circle(990, 710, 70, fill="#a56f43"),
        lines("试剂", 990, 719, size=24, fill="#ffffff", weight=700),
        arrow(765, 525, 950, 648),
        lines("使用试剂", 890, 600, size=18, fill="#52687d", weight=700),
        circle(675, 710, 70, fill="#a56f43"),
        lines("仪器", 675, 719, size=24, fill="#ffffff", weight=700),
        arrow(700, 540, 680, 635),
        lines("使用仪器", 625, 590, size=18, fill="#52687d", weight=700),
        circle(395, 685, 70, fill="#a56f43"),
        lines("样本", 395, 694, size=24, fill="#ffffff", weight=700),
        arrow(630, 505, 452, 638),
        lines("使用样本", 515, 585, size=18, fill="#52687d", weight=700),
        rect(95, 205, 300, 115, fill="#ffffff", stroke="#9abada", rx=16),
        lines("关系属性", 245, 245, size=22, fill="#245b91", weight=700),
        lines("source_type · source_id\nconfidence · properties", 245, 278,
              size=18, gap=26),
    ]
    return base("\n".join(parts))


def kg_flow() -> str:
    parts = [
        rect(45, 55, 1510, 790, fill="#f8fafc", stroke="#8aa7c2", rx=26),
        rect(80, 90, 1440, 70, fill="#edf5fc", stroke="#7fa9d2", rx=16),
        lines("约束：仅处理当前项目内已审核的实验笔记", 800, 137,
              size=28, fill="#245b91", weight=700),
        rect(90, 240, 220, 115, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("草稿 / 更新", 200, 290, size=27, fill="#173a5e", weight=700),
        lines("不触发抽取", 200, 328, size=21),
        arrow(310, 298, 420, 298),
        rect(430, 240, 220, 115, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("提交审核", 540, 307, size=27, fill="#173a5e", weight=700),
        arrow(650, 298, 760, 298),
        '<polygon points="875,205 990,298 875,391 760,298" fill="#fff7ed" stroke="#d99a51" stroke-width="3" filter="url(#shadow)"/>',
        lines("审核通过？", 875, 308, size=26, fill="#9a5a13", weight=700),
        path_arrow("M875 391 L875 435 L200 435 L200 365", color="#d0832f", width=4),
        lines("否：退回修改并记录意见", 530, 470, size=21, fill="#a86318", weight=700),
        arrow(990, 298, 1090, 298),
        lines("是", 1038, 272, size=20, fill="#246b60", weight=700),
        rect(1100, 220, 390, 155, fill="#eaf7f4", stroke="#65a99b", shadow=True),
        lines("基础实体与关系", 1295, 270, size=27, fill="#246b60", weight=700),
        lines("项目 · 笔记 · 用户 · 类型 · 附件\n来自数据库结构化字段", 1295, 315,
              size=21, gap=34),
        arrow(1295, 375, 1295, 450),
        rect(1040, 500, 510, 140, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("实验对象抽取", 1295, 545, size=27, fill="#173a5e", weight=700),
        lines("结构化字段优先 + 自由文本规则补充\n试剂 · 仪器 · 样本 · 结果", 1295, 587,
              size=21, gap=33),
        arrow(1040, 570, 900, 570),
        rect(530, 500, 350, 140, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("归一化与去重", 705, 545, size=27, fill="#173a5e", weight=700),
        lines("norm(term)\nnatural_key = pid:type:term", 705, 587, size=20, gap=32),
        arrow(530, 570, 390, 570),
        rect(80, 500, 290, 155, fill="#ffffff", stroke="#5686b5", shadow=True),
        lines("写入图谱", 225, 545, size=27, fill="#173a5e", weight=700),
        lines("实体 · 关系 · 来源\n置信度 · 抽取运行记录", 225, 590, size=21, gap=33),
        arrow(225, 655, 225, 705),
        rect(80, 720, 1410, 80, fill="#edf5fc", stroke="#7fa9d2", rx=16),
        lines("输出：项目内可追溯知识图谱；手动重建仍只处理已审核笔记", 785, 772,
              size=25, fill="#245b91", weight=700),
    ]
    return base("\n".join(parts))


def rag_comparison() -> str:
    parts = [
        rect(45, 45, 1510, 835, fill="#f8fafc", stroke="#8aa7c2", rx=26),
        rect(565, 75, 470, 90, fill="#edf5fc", stroke="#7fa9d2", shadow=True),
        lines("用户问题 + 项目读取权限校验", 800, 130, size=27,
              fill="#245b91", weight=700),
        path_arrow("M700 165 L420 225", width=4),
        path_arrow("M900 165 L1180 225", width=4),
        rect(85, 210, 650, 600, fill="#f4f7fa", stroke="#9aaec0", rx=22),
        rect(865, 210, 650, 600, fill="#edf5fc", stroke="#7fa9d2", rx=22),
        lines("普通 RAG", 410, 265, size=31, fill="#173a5e", weight=700),
        lines("图谱增强 RAG", 1190, 265, size=31, fill="#173a5e", weight=700),
    ]
    for x in (145, 925):
        parts.extend([
            rect(x, 305, 530, 105, fill="#ffffff", stroke="#8eafd0", shadow=True),
            lines("同一项目资料库", x + 265, 348, size=25, fill="#173a5e", weight=700),
            lines("向量 0.8 + 词项 0.2 → 前 6 个资料片段", x + 265, 383, size=20),
        ])
    parts.extend([
        arrow(410, 410, 410, 495),
        rect(145, 510, 530, 100, fill="#ffffff", stroke="#8eafd0", shadow=True),
        lines("模型输入：资料证据", 410, 570, size=24,
              fill="#173a5e", weight=700),
        arrow(1190, 410, 1190, 450),
        rect(925, 465, 530, 105, fill="#eaf7f4", stroke="#65a99b", shadow=True),
        lines("额外检索一跳图谱关系", 1190, 508, size=24,
              fill="#246b60", weight=700),
        lines("阈值 ≥ 1.0 → 前 10 条关系证据", 1190, 545, size=20),
        arrow(1190, 570, 1190, 620),
        rect(925, 635, 530, 85, fill="#ffffff", stroke="#5686b5", shadow=True),
        lines("模型输入：资料证据 + 关系证据", 1190, 687, size=24,
              fill="#173a5e", weight=700),
        arrow(410, 610, 410, 690),
        rect(145, 690, 530, 65, fill="#edf5fc", stroke="#7fa9d2", rx=14),
        lines("同一 DeepSeek 模型与生成配置", 410, 732, size=22,
              fill="#245b91", weight=700),
        rect(925, 735, 530, 60, fill="#edf5fc", stroke="#7fa9d2", rx=14),
        lines("同一 DeepSeek 模型与生成配置", 1190, 773, size=22,
              fill="#245b91", weight=700),
        rect(600, 825, 400, 50, fill="#fff7ed", stroke="#d99a51", rx=14),
        lines("主要实验变量：是否注入图谱上下文", 800, 858, size=20,
              fill="#9a5a13", weight=700),
    ])
    return base("\n".join(parts))


def traceability() -> str:
    parts = [
        rect(45, 55, 1510, 790, fill="#f8fafc", stroke="#8aa7c2", rx=26),
        rect(85, 95, 1430, 70, fill="#edf5fc", stroke="#7fa9d2", rx=16),
        lines("从回答结论反向定位到检索证据、原始数据与人工评价", 800, 142,
              size=28, fill="#245b91", weight=700),
    ]
    cards = [
        (100, 245, "#3f78ae", "资料来源层", "[S1] - [S6]\n文件 → 数据块 → 检索分数"),
        (100, 435, "#4f8f82", "图谱依据层", "[G1] - [G10]\n源实体 → 关系 → 目标实体"),
        (100, 625, "#a56f43", "评价层", "评分 · 准确性 · 可追溯性\n审核/管理权限提交"),
    ]
    for x, y, color, title, desc in cards:
        parts.extend([
            rect(x, y, 480, 145, fill="#ffffff", stroke=color, shadow=True),
            rect(x, y, 155, 145, fill=color, stroke=color, rx=18),
            lines(title, x + 78, y + 68, size=23, fill="#ffffff", weight=700),
            lines(desc, x + 320, y + 58, size=21, gap=34),
            arrow(x + 490, y + 72, 725, y + 72),
        ])
    parts.extend([
        rect(740, 300, 330, 390, fill="#ffffff", stroke="#5686b5", shadow=True),
        circle(905, 385, 55, fill="#3f78ae"),
        lines("AI", 905, 397, size=28, fill="#ffffff", weight=700),
        lines("问答记录", 905, 485, size=30, fill="#173a5e", weight=700),
        lines("问题 · 回答 · 模式\n来源数 · 图谱命中数\n模型与提示版本\nToken · 时延 · 回退原因", 905, 535,
              size=21, gap=35),
        arrow(1070, 495, 1190, 495),
        rect(1205, 300, 295, 390, fill="#edf5fc", stroke="#7fa9d2", shadow=True),
        lines("审计与复现", 1352, 370, size=29, fill="#245b91", weight=700),
        lines("操作日志\n实验运行编号\n配置快照\n语料哈希\n数据库记录 ID", 1352, 430,
              size=22, gap=43),
        rect(740, 735, 760, 70, fill="#eaf7f4", stroke="#65a99b", rx=16),
        lines("验证路径：回答引用 → 来源编号 → 原始文件 / 图谱关系 → 操作人和时间", 1120, 780,
              size=22, fill="#246b60", weight=700),
    ])
    return base("\n".join(parts))


def architecture() -> str:
    parts = [
        rect(45, 35, 1510, 830, fill="#f8fafc", stroke="#8aa7c2", rx=26),
        rect(105, 65, 1390, 125, fill="#edf5fc", stroke="#7fa9d2", shadow=True),
        lines("用户交互层", 235, 137, size=26, fill="#245b91", weight=700),
        rect(390, 82, 1040, 90, fill="#ffffff", stroke="#8eafd0", rx=14),
        lines("Next.js 前端", 910, 113, size=22, fill="#173a5e", weight=700),
        lines("项目工作台 · 实验笔记 · 资料库 · 知识图谱\nAI 问答 · 智能生成 · 审计追溯",
              910, 140, size=18, gap=25),
        arrow(800, 190, 800, 220),
        rect(105, 230, 1390, 125, fill="#f4f7fa", stroke="#9aaec0", shadow=True),
        lines("接口与权限层", 235, 302, size=26, fill="#245b91", weight=700),
        rect(390, 247, 1040, 90, fill="#ffffff", stroke="#8eafd0", rx=14),
        lines("FastAPI REST API", 910, 278, size=22, fill="#173a5e", weight=700),
        lines("JWT 身份校验 · project_id 权限校验\n统一响应 · 审计记录",
              910, 305, size=18, gap=25),
        arrow(800, 355, 800, 385),
        rect(105, 395, 1390, 205, fill="#edf5fc", stroke="#7fa9d2", shadow=True),
        lines("领域服务层", 225, 505, size=26, fill="#245b91", weight=700),
    ]
    services = [
        (430, "笔记与审核", "版本管理\n状态流转"),
        (655, "资料与 RAG", "分块入库\n混合检索"),
        (880, "知识图谱", "实体抽取\n关系关联"),
        (1105, "问答与生成", "证据注入\n任务生成"),
        (1330, "审计评价", "日志留痕\n实验快照"),
    ]
    for x, title, desc in services:
        parts.extend([
            rect(x - 95, 430, 190, 135, fill="#ffffff", stroke="#8eafd0", rx=16),
            lines(title, x, 472, size=21, fill="#173a5e", weight=700),
            lines(desc, x, 511, size=17, gap=25),
        ])
    parts.extend([
        arrow(800, 600, 800, 630),
        rect(105, 640, 1390, 140, fill="#f4f7fa", stroke="#9aaec0", shadow=True),
        lines("数据与模型层", 225, 722, size=26, fill="#245b91", weight=700),
        rect(365, 667, 310, 88, fill="#ffffff", stroke="#5686b5", rx=14),
        lines("PostgreSQL + pgvector", 520, 720, size=21, fill="#173a5e", weight=700),
        rect(725, 667, 310, 88, fill="#ffffff", stroke="#65a99b", rx=14),
        lines("FastEmbed / ONNX\nCPU 嵌入服务", 880, 704, size=19, gap=26,
              fill="#246b60", weight=700),
        rect(1085, 667, 310, 88, fill="#ffffff", stroke="#d99a51", rx=14),
        lines("DeepSeek 官方 API", 1240, 720, size=21, fill="#9a5a13", weight=700),
        rect(105, 795, 1390, 55, fill="#eaf7f4", stroke="#65a99b", rx=12),
        lines("横向约束", 225, 829, size=20, fill="#246b60", weight=700),
        lines("project_id 数据隔离 · 审核后入库/入图 · 来源与操作全程留痕",
              920, 829, size=18, fill="#246b60", weight=700),
    ])
    return base("\n".join(parts))


DIAGRAMS = {
    "11-role-permission-boundary.svg": role_permission,
    "12-trusted-knowledge-loop.svg": trusted_loop,
    "13-kg-schema.svg": kg_schema,
    "14-kg-construction-flow.svg": kg_flow,
    "15-rag-comparison-flow.svg": rag_comparison,
    "16-traceability-chain.svg": traceability,
    "17-system-architecture.svg": architecture,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, build in DIAGRAMS.items():
        path = OUT / filename
        path.write_text(build(), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
