# sci-search

给 AI Agent 装一个学术论文搜索引擎。

搜 arXiv 和 Semantic Scholar，抓论文全文，让 Agent 帮你综合分析。从"一个下午的体力活"变成"一句话"。

## 它能做什么

- **搜论文**：并行搜索 arXiv 和 Semantic Scholar，返回最相关的结果
- **取全文**：arXiv 论文自动下载 PDF 并提取全文，其他来源提供摘要
- **回答问题**：Agent 基于搜索结果综合分析，给出结构化答案和引用链接

## 快速开始

```bash
# 克隆到 Claude Code skills 目录
git clone https://github.com/fangcun-agi/sci-search.git ~/.claude/skills/sci-search

# 安装依赖
pip install requests beautifulsoup4
```

就这样，重启 Claude Code 即可使用。

## 使用示例

在 Claude Code 中直接问：

```
帮我调研 LLM 在芯片设计中的最新进展
```

Agent 会自动调用 sci-search 搜索论文、抓取全文、综合分析后给你一个带引用的答案。

也可以直接调用脚本：

```bash
# 搜索论文
python3 ~/.claude/skills/sci-search/scripts/sci_search.py "MoE architecture LLM" -n 10

# 获取 arXiv 论文全文
python3 ~/.claude/skills/sci-search/scripts/paper_fetch.py --arxiv 2401.04088
```

## 兼容性

不挑 Agent。只要支持调用命令行工具的 AI Agent 都能用：

- Claude Code
- Hermes
- 其他基于 CLI 的 Agent

## 数据源

| 来源 | 全文 | 覆盖范围 |
|------|------|---------|
| arXiv | PDF 全文下载 | CS、物理、数学、统计等 |
| Semantic Scholar | 摘要 | 全学科 |

完全合规，不依赖任何盗版数据库。

## License

MIT
