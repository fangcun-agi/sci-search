# sci-search

给 AI Agent 装一个学术论文搜索引擎。

搜 arXiv 和 Semantic Scholar，通过 Sci-Hub 抓论文 PDF 全文，让 Agent 帮你综合分析。从"一个下午的体力活"变成"一句话"。

## 它能做什么

- **搜论文**：并行搜索 arXiv 和 Semantic Scholar，返回最相关的结果
- **取全文**：优先通过 Sci-Hub 下载 PDF 全文并提取文本，Sci-Hub 没有的回退到 arXiv HTML
- **回答问题**：Agent 基于搜索结果综合分析，给出结构化答案和引用链接

## 快速开始

```bash
# 克隆到 Claude Code skills 目录
git clone https://github.com/fangcun-agi/sci-search.git ~/.claude/skills/sci-search

# 安装依赖
pip install requests beautifulsoup4 html2text pymupdf
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

# 通过 DOI 从 Sci-Hub 获取论文全文
python3 ~/.claude/skills/sci-search/scripts/paper_fetch.py --doi 10.1038/nature12373 --text

# 保存 PDF 和文本到指定目录（分开存储）
python3 ~/.claude/skills/sci-search/scripts/paper_fetch.py --doi 10.1038/nature12373 --text -d /tmp/papers
# 生成:
#   /tmp/papers/pdfs/10.1038_nature12373.pdf
#   /tmp/papers/texts/10.1038_nature12373.txt

# arXiv 论文（Sci-Hub 没有的自动回退）
python3 ~/.claude/skills/sci-search/scripts/paper_fetch.py --arxiv 2401.04088
```

## 全文获取策略

优先级：**Sci-Hub → arXiv HTML → PubMed → URL 抓取**

| 来源 | 全文 | 覆盖范围 |
|------|------|---------|
| **Sci-Hub** | PDF 全文下载 + 文本提取 | 8000万+ 论文，全学科 |
| arXiv HTML | 网页全文 | CS、物理、数学等（2022 年后新格式） |
| Semantic Scholar | 摘要 | 全学科 |
| PubMed | 摘要 | 生物医学 |

## 兼容性

不挑 Agent。只要支持调用命令行工具的 AI Agent 都能用：

- Claude Code
- Hermes
- 其他基于 CLI 的 Agent

## 依赖

```bash
pip install requests beautifulsoup4 html2text pymupdf
```

无 API Key 需求。arXiv API 和 Semantic Scholar API 均免费开放。

## License

MIT
