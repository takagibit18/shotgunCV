from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PageExtractionResult:
    """Single-page extraction with scoring and dual-source tracking."""

    page: int
    text: str
    source: str  # "native" | "ocr" | "hybrid"
    quality_score: float  # 0.0–1.0
    ocr_used: bool
    native_text: str = ""
    ocr_text: str = ""
    native_score: float = 0.0
    ocr_score: float = 0.0
    ocr_triggered: bool = False


@dataclass(slots=True)
class ExtractionBlock:
    """Lightweight block-level intermediate representation."""

    text: str
    page: int
    source: str  # "native" | "ocr" | "hybrid"
    quality_score: float  # 0.0–1.0
    block_type: str  # "heading" | "paragraph" | "unknown"
    section: str | None = None  # e.g. "skills", "experience", …
    bbox: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class TechCorrection:
    """Evidence record for a single tech-term correction."""

    original: str
    normalized: str
    confidence: float
    block_index: int
    page: int


@dataclass(slots=True)
class CvExtractionResult:
    """Aggregate result of CV extraction pipeline.

    Backward-compatible: ``plain_text`` and ``blocks`` are always populated.
    """

    blocks: list[ExtractionBlock] = field(default_factory=list)
    pages: list[PageExtractionResult] = field(default_factory=list)
    corrections: list[TechCorrection] = field(default_factory=list)
    normalized_skills: list[str] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)

    @property
    def markdown(self) -> str:
        """Simple markdown rendering for backward compat."""
        lines: list[str] = []
        for block in self.blocks:
            if block.block_type == "heading":
                sep = "─" * min(len(block.text), 48)
                lines.append(f"## {block.text}")
                lines.append(sep)
            else:
                lines.append(block.text)
            lines.append("")
        return "\n".join(lines)

    def to_plain(self) -> dict[str, Any]:
        """Serialise to a plain dict for storage / API responses."""
        return {
            "blocks": [_block_to_dict(b) for b in self.blocks],
            "pages": [
                {
                    "page": p.page,
                    "text": p.text,
                    "source": p.source,
                    "quality_score": p.quality_score,
                    "ocr_used": p.ocr_used,
                    "native_text": p.native_text,
                    "ocr_text": p.ocr_text,
                    "native_score": p.native_score,
                    "ocr_score": p.ocr_score,
                    "ocr_triggered": p.ocr_triggered,
                }
                for p in self.pages
            ],
            "corrections": [
                {"original": c.original, "normalized": c.normalized, "confidence": c.confidence, "block_index": c.block_index, "page": c.page}
                for c in self.corrections
            ],
            "normalized_skills": self.normalized_skills,
        }


def _block_to_dict(block: ExtractionBlock) -> dict[str, Any]:
    d: dict[str, Any] = {
        "text": block.text,
        "page": block.page,
        "source": block.source,
        "quality_score": block.quality_score,
        "block_type": block.block_type,
        "section": block.section,
    }
    if block.bbox is not None:
        d["bbox"] = list(block.bbox)
    return d


# ---------------------------------------------------------------------------
# Text quality scoring
# ---------------------------------------------------------------------------


# Common Chinese bigrams for semantic quality detection.
# Covers general vocabulary, education, tech, and CV-specific terms.
# When CMap encoding is corrupted, these bigrams will mostly miss.
_CJK_BIGRAMS: frozenset[str] = frozenset([
    # --- General / connectors ---
    "我们", "他们", "自己", "可以", "没有", "已经", "还是", "因为", "所以",
    "但是", "如果", "虽然", "而且", "或者", "不过", "这个", "那个", "什么",
    "怎么", "一个", "一种", "一些", "很多", "非常", "比较", "主要", "其他",
    "通过", "进行", "使用", "提供", "包括", "需要", "作为", "以及", "其中",
    "具有", "所有", "不同", "可能", "一定", "实现", "完成", "支持", "处理",
    "相关", "用户", "信息", "功能", "目前", "目前", "时间", "空间", "世界",
    # --- Education ---
    "大学", "本科", "硕士", "博士", "学历", "学位", "毕业", "学院", "研究生",
    "计算", "算机", "科学", "技术", "工程", "软件", "网络", "数据", "系统",
    "数学", "物理", "化学", "生物", "英语", "语言", "文学", "法律", "经济",
    "管理", "会计", "金融", "市场", "设计", "艺术", "建筑", "医学", "教育",
    "专业", "课程", "实验", "论文", "研究", "导师", "学校", "成绩", "考试",
    "证书", "奖学金", "实习", "经历", "社团", "活动", "组织", "志愿者",
    "中央", "民族", "北京", "清华", "交通", "电子", "邮电", "航空", "航天",
    "理工", "科技", "工业", "师范", "农业", "林业", "海洋", "政法", "财经",
    # --- Work / CV ---
    "工作", "职责", "负责", "参与", "完成", "担任", "任职", "在职", "离职",
    "岗位", "职位", "员工", "主管", "经理", "总监", "总裁", "工程师", "设计师",
    "开发", "研发", "测试", "运维", "运营", "产品", "架构", "算法", "前端",
    "后端", "全栈", "移动", "桌面", "嵌入", "游戏", "安全", "质量", "性能",
    "团队", "协作", "沟通", "领导", "组织", "规划", "执行", "跟踪", "评估",
    "优化", "提升", "降低", "增长", "达成", "突破", "创新", "解决", "落地",
    "公司", "企业", "行业", "业务", "客户", "需求", "方案", "策略", "流程",
    # --- Tech skills ---
    "数据库", "服务器", "平台", "工具", "框架", "组件", "接口", "模块",
    "容器", "集群", "分布", "微服", "服务", "编排", "调度", "监控", "日志",
    "缓存", "消息", "队列", "存储", "检索", "索引", "查询", "事务", "备份",
    "编程", "代码", "编译", "调试", "部署", "发布", "集成", "交付", "流水",
    "训练", "模型", "推理", "部署", "向量", "嵌入", "文档", "知识", "图谱",
    "自然", "语言", "图像", "视觉", "语音", "识别", "生成", "对话", "搜索",
    # --- Project / achievements ---
    "项目", "方案", "成果", "效果", "收益", "效率", "成本", "周期", "迭代",
    "版本", "迭代", "上线", "灰度", "回归", "监控", "报警", "修复", "重构",
    "开源", "贡献", "代码", "仓库", "社区", "文档", "教程", "博客", "文章",
    "演讲", "分享", "会议", "专利", "发表", "竞赛", "获奖", "排名", "荣誉",
    # --- Common verbs/phrases ---
    "学习", "掌握", "熟悉", "了解", "精通", "擅长", "具备", "拥有", "获得",
    "建立", "创建", "搭建", "构建", "开发", "编写", "制定", "执行", "推动",
    "分析", "挖掘", "清洗", "建模", "评估", "预测", "推荐", "分类", "聚类",
    "识别", "检测", "跟踪", "匹配", "转换", "压缩", "加速", "扩展", "迁移",
])

_CJK_BIGRAM_MIN_CHARS = 30  # Need at least this many CJK chars to judge
_CJK_BIGRAM_CORRUPTION_HARD = 0.08  # Below this → near-certain CMap corruption (hard gate)
_CJK_BIGRAM_CORRUPTION_SOFT = 0.15  # Below this → suspicious, trigger OCR evaluation


def _cjk_bigram_hit_rate(text: str) -> float:
    """Return the fraction of CJK character bigrams found in the dictionary.

    Bigrams are formed only within CJK runs (not across non-CJK boundaries),
    avoiding false pairings caused by English/numbers/punctuation in mixed text.

    Normal Chinese text typically scores 0.35–0.70.
    CMap-corrupted text typically scores < 0.15.
    Text with too few CJK chars returns 1.0 (not judged).
    """
    # Split into CJK runs — only pair characters within the same segment
    cjk_segments: list[str] = []
    current: list[str] = []
    for ch in text:
        if "一" <= ch <= "鿿":
            current.append(ch)
        else:
            if len(current) >= 2:
                cjk_segments.append("".join(current))
            current = []
    if len(current) >= 2:
        cjk_segments.append("".join(current))

    total_cjk = sum(len(s) for s in cjk_segments)
    if total_cjk < _CJK_BIGRAM_MIN_CHARS:
        return 1.0  # Too few CJK chars to reliably judge

    hit_bigrams: set[str] = set()
    all_bigrams: set[str] = set()
    for segment in cjk_segments:
        for i in range(len(segment) - 1):
            bg = segment[i] + segment[i + 1]
            all_bigrams.add(bg)
            if bg in _CJK_BIGRAMS:
                hit_bigrams.add(bg)

    if not all_bigrams:
        return 0.0
    return len(hit_bigrams) / len(all_bigrams)


def score_text_quality(text: str) -> float:
    """Return a 0.0–1.0 quality score for extracted text.

    Higher is better.  Heuristic; not a learned model.
    """
    stripped = text.strip()
    if not stripped:
        return 0.0

    visible_chars = sum(1 for ch in stripped if ch.isprintable() and not ch.isspace())
    total_chars = len(stripped)
    replacement_chars = stripped.count("�")
    control_chars = sum(1 for ch in stripped if ord(ch) < 32 and ch not in "\r\n\t")

    # Dimensions (each 0-1 initially, then weighted)
    if total_chars == 0:
        return 0.0

    replacement_ratio = min(1.0, replacement_chars / total_chars)
    control_ratio = min(1.0, control_chars / total_chars)
    content_density = visible_chars / max(1, total_chars)

    # Lines that look like real text (mix of alnum + CJK)
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    good_lines = sum(1 for ln in lines if _line_has_meaningful_content(ln))
    line_quality = good_lines / max(1, len(lines)) if lines else 0.0

    # CJK semantic quality: bigram dictionary hit rate
    cjk_semantic = _cjk_bigram_hit_rate(stripped)

    # Weighted combination
    score = (
        content_density * 0.27
        + (1.0 - replacement_ratio) * 0.22
        + (1.0 - control_ratio) * 0.18
        + line_quality * 0.18
        + cjk_semantic * 0.15
    )
    return round(max(0.0, min(1.0, score)), 4)


def _line_has_meaningful_content(line: str) -> bool:
    """A line has meaningful content if it contains alphanumeric or CJK chars."""
    visible = [ch for ch in line if not ch.isspace()]
    if not visible:
        return False
    content = [ch for ch in visible if ch.isalnum() or "一" <= ch <= "鿿" or ch in ".-_@/:+"]
    return len(content) / len(visible) >= 0.4


# ---------------------------------------------------------------------------
# Page-level fallback strategy
# ---------------------------------------------------------------------------

# Thresholds
NATIVE_QUALITY_MIN = 0.35  # Below this, trigger OCR
OCR_GAIN_THRESHOLD = 0.10  # OCR must beat native by this margin to replace


def decide_page_source(native_text: str, native_score: float, ocr_text: str, ocr_score: float) -> PageExtractionResult:
    """Apply the page-level fallback strategy.

    Rules (in order):
    1. Native score >= threshold → use native, no OCR needed.
    2. Native score < threshold → trigger OCR.
    3. OCR score > native score + margin → use OCR.
    4. Otherwise → use native, keep OCR as supplement.
    """
    page = 1  # caller overrides
    ocr_triggered = native_score < NATIVE_QUALITY_MIN

    if not ocr_triggered:
        return PageExtractionResult(
            page=page,
            text=native_text,
            source="native",
            quality_score=native_score,
            ocr_used=False,
            native_text=native_text,
            ocr_text="",
            native_score=native_score,
            ocr_score=0.0,
            ocr_triggered=False,
        )

    # OCR was triggered — decide whether to use it
    if ocr_text.strip() and ocr_score > native_score + OCR_GAIN_THRESHOLD:
        return PageExtractionResult(
            page=page,
            text=ocr_text,
            source="ocr",
            quality_score=ocr_score,
            ocr_used=True,
            native_text=native_text,
            ocr_text=ocr_text,
            native_score=native_score,
            ocr_score=ocr_score,
            ocr_triggered=True,
        )

    # OCR not better enough — keep native
    return PageExtractionResult(
        page=page,
        text=native_text,
        source="native",
        quality_score=native_score,
        ocr_used=False,
        native_text=native_text,
        ocr_text=ocr_text,
        native_score=native_score,
        ocr_score=ocr_score,
        ocr_triggered=True,
    )


# ---------------------------------------------------------------------------
# Block conversion
# ---------------------------------------------------------------------------

BLOCK_MIN_CHARS = 2  # lines shorter than this are merged into previous block


def build_blocks_from_text(text: str, page: int, source: str, quality_score: float) -> list[ExtractionBlock]:
    """Convert a page-level text string into a list of ExtractionBlocks.

    Simple heuristics for block_type:
    - Short lines ending without punctuation → heading
    - Otherwise → paragraph
    - Lines that are too short and fragmentary → unknown
    """
    raw_lines = text.splitlines()
    # Merge very short fragments
    merged: list[str] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if merged and merged[-1]:
                merged.append("")
            continue
        if len(stripped) < BLOCK_MIN_CHARS and merged and merged[-1]:
            merged[-1] = merged[-1] + " " + stripped
        else:
            merged.append(stripped)

    blocks: list[ExtractionBlock] = []
    for line in merged:
        if not line:
            continue
        block_type = _guess_block_type(line)
        blocks.append(
            ExtractionBlock(
                text=line,
                page=page,
                source=source,
                quality_score=quality_score,
                block_type=block_type,
            )
        )
    return blocks


def _guess_block_type(line: str) -> str:
    """Heuristic block-type classifier."""
    stripped = line.strip()
    length = len(stripped)
    if length <= 80:
        # Short lines without sentence-ending punctuation → likely heading
        if not re.search(r"[。！？.!?;；，,]$", stripped) and length <= 60:
            # Check if it looks like a section title
            if re.match(r"^[\w一-鿿\s\-·•|/&+#]+$", stripped):
                return "heading"
    return "paragraph"


# ---------------------------------------------------------------------------
# CV Section identification
# ---------------------------------------------------------------------------

# Aliases: canonical_section → [aliases]  (lowercase for matching)
SECTION_ALIASES: dict[str, list[str]] = {
    "basic_info": ["基本信息", "个人信息", "联系方式", "personal info", "contact", "基本信息"],
    "education": ["教育经历", "教育背景", "education", "educational background"],
    "skills": ["专业技能", "技能栈", "技术栈", "skills", "technical skills", "tech stack", "专业能力"],
    "projects": ["项目经历", "项目经验", "projects", "project experience", "个人项目"],
    "experience": ["实习经历", "工作经历", "experience", "work experience", "professional experience", "工作经验"],
    "awards": ["荣誉奖项", "证书", "awards", "certificates", "certifications", "获奖", "所获荣誉"],
    "self_eval": ["自我评价", "个人评价", "self evaluation", "summary", "个人总结"],
    "intent": ["求职意向", "求职方向", "career objective", "objective", "求职目标"],
}

# Build reverse map: lowercase alias → canonical section
_ALIAS_TO_SECTION: dict[str, str] = {}
for _section, _aliases in SECTION_ALIASES.items():
    for _a in _aliases:
        _ALIAS_TO_SECTION[_a.lower().strip()] = _section


def identify_cv_sections(blocks: list[ExtractionBlock]) -> list[ExtractionBlock]:
    """Scan blocks, assign ``section`` based on heading detection.

    Rules:
    - Heading blocks are checked against SECTION_ALIASES.
    - Once a heading is recognised, subsequent non-heading blocks inherit that section.
    - A new heading resets the current section.
    - Unknown headings → section stays None for following blocks.
    """
    current_section: str | None = None
    for i, block in enumerate(blocks):
        if block.block_type == "heading":
            matched = _match_section_heading(block.text)
            if matched is not None:
                current_section = matched
                block.section = current_section
            else:
                current_section = None
                block.section = None
        else:
            block.section = current_section
    return blocks


def _match_section_heading(text: str) -> str | None:
    """Return canonical section name if text matches an alias, else None."""
    cleaned = text.strip().lower().rstrip("：:：-─ ").lstrip("#*•·- ")
    # Direct match
    if cleaned in _ALIAS_TO_SECTION:
        return _ALIAS_TO_SECTION[cleaned]
    # Fuzzy: check if any alias is a substring of the cleaned text
    for alias, section in _ALIAS_TO_SECTION.items():
        if alias in cleaned or cleaned in alias:
            return section
    return None


# ---------------------------------------------------------------------------
# Tech stack normalization
# ---------------------------------------------------------------------------

# Minimal tech vocabulary (can be extended)
TECH_VOCABULARY = sorted(
    [
        # Languages
        "Python", "Java", "Go", "C++", "C", "JavaScript", "TypeScript", "Rust", "Kotlin", "Swift",
        # Backend frameworks
        "FastAPI", "Django", "Flask", "Spring Boot", "Express", "Gin",
        # Frontend
        "React", "Vue", "Next.js", "Nuxt", "Angular",
        # Data / Storage
        "MySQL", "PostgreSQL", "Redis", "MongoDB", "Qdrant", "Milvus", "Elasticsearch",
        "SQLite", "ClickHouse",
        # DevOps / Infra
        "Docker", "Kubernetes", "Git", "GitHub Actions", "Linux", "Nginx", "CI/CD",
        "Jenkins", "Terraform",
        # AI / ML
        "LangChain", "LangGraph", "LlamaIndex", "RAG", "BM25", "PyTorch", "Transformers",
        "OpenAI", "TensorFlow", "Hugging Face", "BGE-M3", "Reranker",
        # Tools
        "Pydantic", "Click", "pytest", "Postman", "Jupyter",
    ],
    key=len,
    reverse=True,  # longer tokens matched first to avoid "Java" matching inside "JavaScript"
)

# Known OCR confusions for tech terms
OCR_TECH_CONFUSIONS: dict[str, str] = {
    "fastapl": "FastAPI",
    "fastapi": "FastAPI",
    "postgresqi": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "typescrlpt": "TypeScript",
    "typescript": "TypeScript",
    "langgrapn": "LangGraph",
    "langgraph": "LangGraph",
    "qdrani": "Qdrant",
    "qdrant": "Qdrant",
    "kubernetcs": "Kubernetes",
    "kubernetes": "Kubernetes",
    "dockcr": "Docker",
    "dockor": "Docker",
    "pytoch": "PyTorch",
    "pytorch": "PyTorch",
    "pythan": "Python",
    "pyth0n": "Python",
    "javascrlpt": "JavaScript",
    "typescdpt": "TypeScript",
    "langcham": "LangChain",
    "langchian": "LangChain",
    "milvus": "Milvus",
    "milvu5": "Milvus",
    "pandantic": "Pydantic",
    "pydantlc": "Pydantic",
}

MIN_CONFIDENCE = 0.70  # Only apply corrections above this threshold

# Regex to find potential tech tokens
_TECH_TOKEN_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9.+#_\-/]{1,40}[A-Za-z0-9]\b",
    re.UNICODE,
)


def normalize_tech_stack(
    blocks: list[ExtractionBlock],
) -> tuple[list[ExtractionBlock], list[TechCorrection], list[str]]:
    """Fuzzy-normalize tech terms in skills / projects / experience sections.

    Returns:
    - updated blocks (text is NOT modified; corrections recorded separately)
    - list of TechCorrection records
    - list of unique normalized skill tokens found
    """
    corrections: list[TechCorrection] = []
    skill_set: set[str] = set()
    corrected_blocks: list[ExtractionBlock] = []

    for idx, block in enumerate(blocks):
        # Only process CV-relevant sections
        if block.section not in (None, "skills", "projects", "experience"):
            corrected_blocks.append(block)
            continue

        tokens_found = _find_tech_tokens(block.text)
        for raw_token in tokens_found:
            normalized, confidence = _fuzzy_match_token(raw_token)
            if confidence >= MIN_CONFIDENCE and normalized != raw_token:
                corrections.append(
                    TechCorrection(
                        original=raw_token,
                        normalized=normalized,
                        confidence=confidence,
                        block_index=idx,
                        page=block.page,
                    )
                )
            if confidence >= MIN_CONFIDENCE:
                skill_set.add(normalized)
            elif confidence >= 0.50:
                # Lower confidence: record but don't promote
                pass

        corrected_blocks.append(block)

    return corrected_blocks, corrections, sorted(skill_set)


def _find_tech_tokens(text: str) -> list[str]:
    """Extract potential technology term tokens from text."""
    candidates: list[str] = []
    for match in _TECH_TOKEN_RE.finditer(text):
        token = match.group(0)
        # Filter out obvious non-tech words
        if len(token) < 2:
            continue
        if token.lower() in {
            "the", "and", "for", "with", "from", "this", "that", "have", "been",
            "has", "was", "are", "were", "not", "but", "all", "can", "will",
            "year", "years", "month", "months", "day", "days", "team", "work",
            "user", "data", "system", "based", "using", "used", "use",
            "project", "product", "service", "support", "design", "build",
            "research", "analysis", "part", "role", "experience", "skill",
            "background", "company", "group", "high", "new", "one", "two",
            "http", "https", "www", "com", "org", "edu", "github",
        }:
            continue
        candidates.append(token)
    return candidates


def _fuzzy_match_token(token: str) -> tuple[str, float]:
    """Match a token against TECH_VOCABULARY using difflib.

    Returns (normalized_form, confidence).
    """
    token_lower = token.lower().strip()

    # 1. Direct match (case-insensitive) — highest confidence
    for tech in TECH_VOCABULARY:
        if token_lower == tech.lower():
            return tech, 1.0

    # 2. Known OCR confusion
    if token_lower in OCR_TECH_CONFUSIONS:
        return OCR_TECH_CONFUSIONS[token_lower], 0.95

    # 3. Fuzzy match against vocabulary
    best_score = 0.0
    best_tech = token
    matcher = SequenceMatcher(isjunk=None, a=token_lower, b="")
    for tech in TECH_VOCABULARY:
        tech_lower = tech.lower()
        # Quick length filter
        len_ratio = min(len(token_lower), len(tech_lower)) / max(len(token_lower), len(tech_lower))
        if len_ratio < 0.55:
            continue
        matcher.set_seq2(tech_lower)
        score = matcher.ratio()
        # Bonus for prefix match
        if token_lower[:3] == tech_lower[:3]:
            score = min(1.0, score + 0.08)
        if score > best_score:
            best_score = score
            best_tech = tech

    return best_tech, round(best_score, 4)


# ---------------------------------------------------------------------------
# Convenience: full extraction pipeline
# ---------------------------------------------------------------------------


def post_process_cv_blocks(blocks: list[ExtractionBlock]) -> CvExtractionResult:
    """Run CV-specific post-processing on blocks.

    1. Identify sections.
    2. Normalize tech stack.
    Returns a CvExtractionResult.
    """
    blocks = identify_cv_sections(blocks)
    blocks, corrections, skills = normalize_tech_stack(blocks)
    return CvExtractionResult(blocks=blocks, corrections=corrections, normalized_skills=skills)


def merge_page_results_to_blocks(pages: list[PageExtractionResult]) -> list[ExtractionBlock]:
    """Convert a list of PageExtractionResults into ExtractionBlocks."""
    all_blocks: list[ExtractionBlock] = []
    for page in pages:
        page_blocks = build_blocks_from_text(
            text=page.text,
            page=page.page,
            source=page.source,
            quality_score=page.quality_score,
        )
        all_blocks.extend(page_blocks)
    return all_blocks


def run_cv_extraction_pipeline(pages: list[PageExtractionResult]) -> CvExtractionResult:
    """End-to-end convenience: pages → blocks → CV post-processing → result."""
    blocks = merge_page_results_to_blocks(pages)
    result = post_process_cv_blocks(blocks)
    result.pages = pages
    return result
