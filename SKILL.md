---
name: sci-search
description: >
  学术论文搜索与问答。搜索 arXiv、Semantic Scholar 等学术数据库，获取论文全文/摘要，
  基于 Claude 综合回答学术问题，附引用链接。
  当用户问学术论文相关问题、需要文献检索、论文问答、学术调研时使用。
  触发词：论文搜索、学术搜索、paper search、文献检索、论文问答、sci search、
  找论文、查论文、research paper。
version: 1.1.0
---

# Sci-Search — 学术论文搜索与问答

搜索学术数据库（arXiv、Semantic Scholar），通过 Sci-Hub 获取论文 PDF 全文，基于 Claude 综合回答学术问题。

## 全文获取策略

优先级：**Sci-Hub → arXiv HTML → PubMed 摘要 → URL 抓取**

| 来源 | 全文 | 说明 |
|------|------|------|
| **Sci-Hub** | PDF 下载 + 文本提取 | 覆盖 8000万+ 论文，优先使用 |
| arXiv HTML | 网页全文 | 仅 2022 年后新格式论文 |
| PubMed | 摘要 | 生物医学领域 |
| URL 抓取 | 网页内容 | 最后手段 |

## 论文存储结构

使用 `--output-dir` 时，PDF 和文本分开存放：

```
{output-dir}/
    pdfs/              # 原始 PDF 文件
        10.1038_nature12373.pdf
    texts/             # 提取的全文文本
        10.1038_nature12373.txt
```

## 工具

```bash
S="$HOME/.claude/skills/sci-search/scripts"
```

| 脚本 | 功能 | 示例 |
|------|------|------|
| `sci_search.py` | 统一搜索（并行查询多源） | `python3 $S/sci_search.py "transformer attention"` |
| `arxiv_search.py` | arXiv 搜索 | `python3 $S/arxiv_search.py "LLM reasoning" -n 5` |
| `semantic_scholar.py` | Semantic Scholar 搜索 | `python3 $S/semantic_scholar.py "chain of thought"` |
| `paper_fetch.py` | 获取论文全文（Sci-Hub 优先） | `python3 $S/paper_fetch.py --doi 10.1038/nature12373 --text` |
| `sci_hub_fetch.py` | 独立 Sci-Hub 抓取 | `python3 $S/sci_hub_fetch.py --doi 10.1038/nature12373` |

## 工作流

### 1. 论文问答（核心场景）

用户提出学术问题时的完整流程：

```bash
S="$HOME/.claude/skills/sci-search/scripts"

# ① 统一搜索
python3 "$S/sci_search.py" "用户的学术问题" -n 10

# ② 对搜索结果中有 DOI 的论文，优先用 Sci-Hub 抓全文（选 top 3-5）
python3 "$S/paper_fetch.py" --doi <DOI> --text -d /tmp/papers

# ③ 对有 arxiv_id 但无 DOI 的论文，自动回退到 arXiv HTML
python3 "$S/paper_fetch.py" --arxiv <arxiv_id>

# ④ 对有 pmid 的论文获取摘要
python3 "$S/paper_fetch.py" --pmid <pmid>

# ⑤ Claude 综合所有信息，生成结构化回答
# 回答格式：
# - 总结当前研究状态
# - 列出关键发现（附论文引用）
# - 指出研究空白或争议
# - 每个论点附带 [作者, 年份] 引用
```

### 2. 纯论文搜索

```bash
# 只搜 arXiv
python3 "$S/sci_search.py" "query" -s arxiv

# 只搜 Semantic Scholar
python3 "$S/sci_search.py" "query" -s s2

# 限定年份范围
python3 "$S/sci_search.py" "query" --year-from 2023 --year-to 2026
```

### 3. 获取单篇论文

```bash
# 通过 DOI 从 Sci-Hub 获取全文（推荐）
python3 "$S/paper_fetch.py" --doi 10.1038/nature12373 --text

# 保存 PDF 和文本到指定目录
python3 "$S/paper_fetch.py" --doi 10.1038/nature12373 --text -d /tmp/papers
# 生成:
#   /tmp/papers/pdfs/10.1038_nature12373.pdf
#   /tmp/papers/texts/10.1038_nature12373.txt

# arXiv 论文（自动回退到 HTML 全文）
python3 "$S/paper_fetch.py" --arxiv 2401.12345

# PubMed 论文摘要
python3 "$S/paper_fetch.py" --pmid 12345678

# 任意 URL
python3 "$S/paper_fetch.py" --url "https://..."
```

## 回答规范

学术问答的回答应遵循以下格式：

```markdown
## [问题主题]

### 核心发现
基于 X 篇论文的综合分析：

1. **发现一** — 描述（[Author et al., 2024](arxiv_url)）
2. **发现二** — 描述（[Author et al., 2023](s2_url)）

### 关键论文
| 论文 | 年份 | 核心贡献 | 引用数 |
|------|------|----------|--------|
| [标题](url) | 2024 | ... | 123 |

### 研究空白 / 争议
- ...

### 参考
1. [Author et al., Year — Title](url)
```

## 搜索策略

### 构造查询词

- 用户用中文提问时，翻译为英文关键词搜索（学术论文以英文为主）
- 提取核心概念，去除虚词
- 多词用空格连接，不强制用 AND/OR

### 结果排序逻辑

sci_search.py 自动按以下优先级排序：
1. 有摘要的论文优先
2. 有开放获取 PDF 的优先
3. arXiv 论文加分（可获取全文）
4. 引用数高的优先
5. 年份新的优先

## 依赖

```bash
pip install requests beautifulsoup4 html2text pymupdf
```

无 API Key 需求。arXiv API 和 Semantic Scholar API 均免费开放。

## 注意事项

- arXiv API 有请求频率限制，连续搜索间隔 ≥3 秒
- Semantic Scholar API 每 5 分钟 100 次请求（无 Key）
- arXiv HTML 全文仅适用于新格式论文（约 2022 年后），旧论文只能获取摘要
- Sci-Hub 覆盖 8000万+ 论文，但非常新的论文（发表数周内）可能尚未收录
- Sci-Hub 使用 curl subprocess 绕过 Cloudflare，需要系统有 curl
- 使用 `--output-dir` 时 PDF 和文本自动分开存储到 `pdfs/` 和 `texts/` 子目录
