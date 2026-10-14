import subprocess
import os

def render_svg_to_png(svg_path, png_path, scale=3):
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    cmd = [
        chrome_path,
        "--headless",
        "--disable-gpu",
        f"--force-device-scale-factor={scale}",
        f"--screenshot={png_path}",
        "--default-background-color=ffffff",
        svg_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("Error rendering PNG:", res.stderr)
    else:
        print(f"Rendered {png_path} successfully!")

# 1. 方案 A：按四大功能模块划分的标准学术功能模块图
def generate_functional_tree_svg(svg_path):
    width = 1100
    height = 540

    # 颜色与样式配置（完全对齐图 2 的经典 Word/Visio 灰度学术规范）
    stroke_color = "#333333"
    line_stroke = "#2b2b2b"
    arrow_color = "#2b2b2b"
    font_family = "'SimSun', 'Songti SC', 'STSong', 'SimHei', 'Microsoft YaHei', sans-serif"

    # 模块定义
    groups = [
        {
            "name": "记录与审核模块",
            "short_name": "记录与审核",
            "items": ["用户与项目权限", "实验笔记管理", "资料与附件管理"]
        },
        {
            "name": "知识组织模块",
            "short_name": "知识组织",
            "items": ["文档解析与入库", "知识实体抽取", "知识关系抽取", "知识图谱展示", "动态知识蓝图"]
        },
        {
            "name": "证据问答与生成模块",
            "short_name": "证据问答与辅助生成",
            "items": ["检索增强问答", "固定任务辅助生成"]
        },
        {
            "name": "审计与评价模块",
            "short_name": "审计与评价",
            "items": ["智能问答评价", "指标预警闭环", "全流程审计追溯"]
        }
    ]

    card_w = 46
    card_h = 230
    gap_inner = 15
    gap_group = 40

    # 计算各组的几何位置
    group_layout = []
    current_x = 0
    for g in groups:
        count = len(g["items"])
        gw = count * card_w + (count - 1) * gap_inner
        group_layout.append({
            "group": g,
            "count": count,
            "width": gw,
            "x_start": current_x
        })
        current_x += gw + gap_group

    total_cards_width = current_x - gap_group
    offset_x = (width - total_cards_width) / 2

    for gl in group_layout:
        gl["x_start"] += offset_x
        gl["center_x"] = gl["x_start"] + gl["width"] / 2

    # 顶层系统框
    root_w = 260
    root_h = 48
    root_x = (width - root_w) / 2
    root_y = 35
    root_cx = width / 2
    root_bottom_y = root_y + root_h

    # 二级框
    l2_y = 125
    l2_h = 44
    l2_bottom_y = l2_y + l2_h

    # 三级卡片
    l3_y = 235

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg.append('<defs>')
    # 渐变背景（与图2相同，经典浅微灰渐变，富有层次感）
    svg.append('''
      <linearGradient id="boxGrad" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#f5f6f8"/>
      </linearGradient>
      <linearGradient id="rootGrad" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#eff2f6"/>
      </linearGradient>
      <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
        <path d="M1,1 L7,4 L1,7 Z" fill="#2b2b2b"/>
      </marker>
      <filter id="subtleShadow" x="-2%" y="-4%" width="104%" height="112%" filterUnits="userSpaceOnUse">
        <feDropShadow dx="1" dy="1.5" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.12"/>
      </filter>
    ''')
    svg.append('</defs>')

    # 白色纯净画布
    svg.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')

    # 1. 顶层根节点
    svg.append(f'<rect x="{root_x}" y="{root_y}" width="{root_w}" height="{root_h}" fill="url(#rootGrad)" stroke="{stroke_color}" stroke-width="1.6" filter="url(#subtleShadow)"/>')
    svg.append(f'<text x="{root_cx}" y="{root_y + 30}" font-family="{font_family}" font-size="20" font-weight="bold" fill="#111111" text-anchor="middle">科研实验记录管理系统</text>')

    # 2. 顶层向下主干线及分支总线
    split_y1 = root_bottom_y + 22
    first_cx = group_layout[0]["center_x"]
    last_cx = group_layout[-1]["center_x"]

    # 垂线下引
    svg.append(f'<line x1="{root_cx}" y1="{root_bottom_y}" x2="{root_cx}" y2="{split_y1}" stroke="{line_stroke}" stroke-width="1.4"/>')
    # 横向主总线
    svg.append(f'<line x1="{first_cx}" y1="{split_y1}" x2="{last_cx}" y2="{split_y1}" stroke="{line_stroke}" stroke-width="1.4"/>')

    # 3. 二级节点绘制
    for gl in group_layout:
        cx = gl["center_x"]
        # 主总线垂直引向二级框
        svg.append(f'<line x1="{cx}" y1="{split_y1}" x2="{cx}" y2="{l2_y}" stroke="{line_stroke}" stroke-width="1.4" marker-end="url(#arrow)"/>')

        # 二级框
        box_text = gl["group"]["short_name"]
        box_w = max(130, len(box_text) * 18 + 36)
        bx = cx - box_w / 2
        svg.append(f'<rect x="{bx}" y="{l2_y}" width="{box_w}" height="{l2_h}" fill="url(#boxGrad)" stroke="{stroke_color}" stroke-width="1.4" filter="url(#subtleShadow)"/>')
        svg.append(f'<text x="{cx}" y="{l2_y + 27}" font-family="{font_family}" font-size="16" font-weight="bold" fill="#222222" text-anchor="middle">{box_text}</text>')

        # 二级框向下的总线
        split_y2 = l2_bottom_y + 24
        svg.append(f'<line x1="{cx}" y1="{l2_bottom_y}" x2="{cx}" y2="{split_y2}" stroke="{line_stroke}" stroke-width="1.4"/>')

        # 各个竖长条框
        item_x_list = []
        for i in range(gl["count"]):
            ix = gl["x_start"] + i * (card_w + gap_inner)
            icx = ix + card_w / 2
            item_x_list.append((ix, icx))

        # 该组的三级水平总线
        left_icx = item_x_list[0][1]
        right_icx = item_x_list[-1][1]
        if gl["count"] > 1:
            svg.append(f'<line x1="{left_icx}" y1="{split_y2}" x2="{right_icx}" y2="{split_y2}" stroke="{line_stroke}" stroke-width="1.4"/>')

        # 下引线至每个竖框
        for i, (ix, icx) in enumerate(item_x_list):
            svg.append(f'<line x1="{icx}" y1="{split_y2}" x2="{icx}" y2="{l3_y}" stroke="{line_stroke}" stroke-width="1.4" marker-end="url(#arrow)"/>')

            # 绘制竖长条框
            svg.append(f'<rect x="{ix}" y="{l3_y}" width="{card_w}" height="{card_h}" fill="url(#boxGrad)" stroke="{stroke_color}" stroke-width="1.2" filter="url(#subtleShadow)"/>')

            # 绘制竖排文字
            item_name = gl["group"]["items"][i]
            # 计算文字垂直居中分布
            n_chars = len(item_name)
            char_font_size = 14
            char_step = 23 if n_chars >= 8 else (26 if n_chars >= 7 else 28)
            total_text_h = (n_chars - 1) * char_step
            start_y = l3_y + (card_h - total_text_h) / 2 + 5

            for c_idx, char in enumerate(item_name):
                cy = start_y + c_idx * char_step
                svg.append(f'<text x="{icx}" y="{cy}" font-family="{font_family}" font-size="{char_font_size}" font-weight="normal" fill="#222222" text-anchor="middle">{char}</text>')

    svg.append('</svg>')

    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(svg))
    print(f"Generated {svg_path}")

# 2. 方案 B：1:1 对标图 2 的角色维度划分树状图（管理员 / 科研人员）
def generate_role_tree_svg(svg_path):
    width = 1100
    height = 540

    stroke_color = "#333333"
    line_stroke = "#2b2b2b"
    font_family = "'SimSun', 'Songti SC', 'STSong', 'SimHei', 'Microsoft YaHei', sans-serif"

    groups = [
        {
            "name": "系统管理员",
            "items": ["用户账号管理", "权限策略配置", "科研项目管理", "全局审计追溯", "预警阈值配置", "外部模型闸门", "全局索引维护"]
        },
        {
            "name": "科研人员与审核人",
            "items": ["实验笔记管理", "资料附件管理", "笔记审核流转", "知识图谱检索", "检索增强问答", "固定任务生成", "问答质量评价"]
        }
    ]

    card_w = 48
    card_h = 230
    gap_inner = 16
    gap_group = 70

    group_layout = []
    current_x = 0
    for g in groups:
        count = len(g["items"])
        gw = count * card_w + (count - 1) * gap_inner
        group_layout.append({
            "group": g,
            "count": count,
            "width": gw,
            "x_start": current_x
        })
        current_x += gw + gap_group

    total_cards_width = current_x - gap_group
    offset_x = (width - total_cards_width) / 2

    for gl in group_layout:
        gl["x_start"] += offset_x
        gl["center_x"] = gl["x_start"] + gl["width"] / 2

    root_w = 260
    root_h = 48
    root_x = (width - root_w) / 2
    root_y = 35
    root_cx = width / 2
    root_bottom_y = root_y + root_h

    l2_y = 125
    l2_h = 44
    l2_bottom_y = l2_y + l2_h
    l3_y = 235

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg.append('<defs>')
    svg.append('''
      <linearGradient id="boxGradRole" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#f5f6f8"/>
      </linearGradient>
      <linearGradient id="rootGradRole" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#eff2f6"/>
      </linearGradient>
      <marker id="arrowRole" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
        <path d="M1,1 L7,4 L1,7 Z" fill="#2b2b2b"/>
      </marker>
      <filter id="subtleShadowRole" x="-2%" y="-4%" width="104%" height="112%" filterUnits="userSpaceOnUse">
        <feDropShadow dx="1" dy="1.5" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.12"/>
      </filter>
    ''')
    svg.append('</defs>')
    svg.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')

    # 根节点
    svg.append(f'<rect x="{root_x}" y="{root_y}" width="{root_w}" height="{root_h}" fill="url(#rootGradRole)" stroke="{stroke_color}" stroke-width="1.6" filter="url(#subtleShadowRole)"/>')
    svg.append(f'<text x="{root_cx}" y="{root_y + 30}" font-family="{font_family}" font-size="20" font-weight="bold" fill="#111111" text-anchor="middle">科研实验记录管理系统</text>')

    # 主线
    split_y1 = root_bottom_y + 22
    first_cx = group_layout[0]["center_x"]
    last_cx = group_layout[-1]["center_x"]

    svg.append(f'<line x1="{root_cx}" y1="{root_bottom_y}" x2="{root_cx}" y2="{split_y1}" stroke="{line_stroke}" stroke-width="1.4"/>')
    svg.append(f'<line x1="{first_cx}" y1="{split_y1}" x2="{last_cx}" y2="{split_y1}" stroke="{line_stroke}" stroke-width="1.4"/>')

    for gl in group_layout:
        cx = gl["center_x"]
        svg.append(f'<line x1="{cx}" y1="{split_y1}" x2="{cx}" y2="{l2_y}" stroke="{line_stroke}" stroke-width="1.4" marker-end="url(#arrowRole)"/>')

        box_text = gl["group"]["name"]
        box_w = max(150, len(box_text) * 18 + 36)
        bx = cx - box_w / 2
        svg.append(f'<rect x="{bx}" y="{l2_y}" width="{box_w}" height="{l2_h}" fill="url(#boxGradRole)" stroke="{stroke_color}" stroke-width="1.4" filter="url(#subtleShadowRole)"/>')
        svg.append(f'<text x="{cx}" y="{l2_y + 27}" font-family="{font_family}" font-size="16" font-weight="bold" fill="#222222" text-anchor="middle">{box_text}</text>')

        split_y2 = l2_bottom_y + 24
        svg.append(f'<line x1="{cx}" y1="{l2_bottom_y}" x2="{cx}" y2="{split_y2}" stroke="{line_stroke}" stroke-width="1.4"/>')

        item_x_list = []
        for i in range(gl["count"]):
            ix = gl["x_start"] + i * (card_w + gap_inner)
            icx = ix + card_w / 2
            item_x_list.append((ix, icx))

        left_icx = item_x_list[0][1]
        right_icx = item_x_list[-1][1]
        svg.append(f'<line x1="{left_icx}" y1="{split_y2}" x2="{right_icx}" y2="{split_y2}" stroke="{line_stroke}" stroke-width="1.4"/>')

        for i, (ix, icx) in enumerate(item_x_list):
            svg.append(f'<line x1="{icx}" y1="{split_y2}" x2="{icx}" y2="{l3_y}" stroke="{line_stroke}" stroke-width="1.4" marker-end="url(#arrowRole)"/>')
            svg.append(f'<rect x="{ix}" y="{l3_y}" width="{card_w}" height="{card_h}" fill="url(#boxGradRole)" stroke="{stroke_color}" stroke-width="1.2" filter="url(#subtleShadowRole)"/>')

            item_name = gl["group"]["items"][i]
            n_chars = len(item_name)
            char_font_size = 14
            char_step = 23 if n_chars >= 8 else (26 if n_chars >= 7 else 28)
            total_text_h = (n_chars - 1) * char_step
            start_y = l3_y + (card_h - total_text_h) / 2 + 5

            for c_idx, char in enumerate(item_name):
                cy = start_y + c_idx * char_step
                svg.append(f'<text x="{icx}" y="{cy}" font-family="{font_family}" font-size="{char_font_size}" font-weight="normal" fill="#222222" text-anchor="middle">{char}</text>')

    svg.append('</svg>')

    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(svg))
    print(f"Generated {svg_path}")

os.makedirs("docs/figures-redrawn-2026-09-30", exist_ok=True)
fn_svg = "docs/figures-redrawn-2026-09-30/fig-4-2-functional-tree.svg"
fn_png = "docs/figures-redrawn-2026-09-30/fig-4-2-functional-tree.png"
generate_functional_tree_svg(fn_svg)
render_svg_to_png(os.path.abspath(fn_svg), os.path.abspath(fn_png), scale=2.5)

role_svg = "docs/figures-redrawn-2026-09-30/fig-4-2-role-tree.svg"
role_png = "docs/figures-redrawn-2026-09-30/fig-4-2-role-tree.png"
generate_role_tree_svg(role_svg)
render_svg_to_png(os.path.abspath(role_svg), os.path.abspath(role_png), scale=2.5)
