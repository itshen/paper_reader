"""
OpenAlex 论文搜索模块

免费、无需 API Key，覆盖期刊/会议/预印本全类型，
支持 Open Access PDF 直链。

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import os
import time
import urllib.request
import urllib.parse
import json
from typing import List, Optional
from datetime import datetime

from .arxiv_search import BasePaperSource, PaperInfo


# OpenAlex API 基础地址
_BASE = "https://api.openalex.org"

# 礼貌请求头（OpenAlex 推荐带 User-Agent）
_HEADERS = {
    "User-Agent": "PaperReaderMCP/1.0 (https://github.com/itshen/paper_reader)",
    "Accept": "application/json",
}


def _get(url: str, timeout: int = 20) -> dict:
    """简单 HTTP GET，返回解析后的 JSON"""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# OpenAlex 学科分类 → arXiv 风格短码（用于 UI 展示，仅做映射参考）
_DOMAIN_MAP = {
    "Computer Science": "cs",
    "Mathematics": "math",
    "Physics and Astronomy": "physics",
    "Medicine": "medicine",
    "Biology": "bio",
    "Economics": "econ",
    "Psychology": "psych",
    "Engineering": "eng",
    "Chemistry": "chem",
}


def _parse_work(work: dict, relevance_rank: int = 0) -> PaperInfo:
    """把 OpenAlex work 对象转成 PaperInfo"""
    # 标题
    title = (work.get("title") or "").replace("\n", " ").strip()

    # 摘要：OpenAlex 用倒排索引存，需重建
    abstract = _rebuild_abstract(work.get("abstract_inverted_index"))

    # 作者
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]

    # 发布日期
    pub_date = work.get("publication_date") or work.get("publication_year") or ""
    if isinstance(pub_date, int):
        pub_date = str(pub_date)

    # arXiv ID（OpenAlex 通常在 ids 里存）
    ids = work.get("ids", {}) or {}
    openalex_id = work.get("id", "").split("/")[-1]  # W1234567
    arxiv_raw = ids.get("arxiv", "") or ""
    if arxiv_raw:
        arxiv_id = arxiv_raw.replace("https://arxiv.org/abs/", "").strip()
    else:
        # 用 openalex_id 作为替代标识（前缀区分）
        arxiv_id = f"oa_{openalex_id}"

    # PDF 直链：优先 primary_location，再 best_oa_location
    pdf_url = ""
    for loc_key in ("primary_location", "best_oa_location"):
        loc = work.get(loc_key) or {}
        if loc.get("pdf_url"):
            pdf_url = loc["pdf_url"]
            break
    if not pdf_url:
        oa = work.get("open_access") or {}
        pdf_url = oa.get("oa_url") or ""

    # 如果有 arXiv ID 但没拿到 PDF，构造标准 arXiv PDF 链接
    if not pdf_url and arxiv_raw:
        aid = arxiv_raw.replace("https://arxiv.org/abs/", "").strip()
        pdf_url = f"https://arxiv.org/pdf/{aid}"

    # 分类（取 topics 的 domain）
    topics = work.get("topics") or []
    raw_domains = list(dict.fromkeys(
        t.get("domain", {}).get("display_name", "")
        for t in topics if t.get("domain")
    ))
    categories = [_DOMAIN_MAP.get(d, d) for d in raw_domains if d][:3] or ["unknown"]

    # 引用数
    citation_count = work.get("cited_by_count")

    info = PaperInfo(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors=authors,
        published=pub_date,
        pdf_url=pdf_url,
        categories=categories,
        source="openalex",
        citation_count=citation_count,
    )
    info._relevance_rank = relevance_rank
    try:
        info._published_date = datetime.strptime(pub_date[:10], "%Y-%m-%d")
    except Exception:
        info._published_date = None
    return info


def _rebuild_abstract(inverted: Optional[dict]) -> str:
    """从 OpenAlex 倒排索引重建摘要文本"""
    if not inverted:
        return ""
    # {word: [pos1, pos2, ...]}
    positions: list[tuple[int, str]] = []
    for word, pos_list in inverted.items():
        for pos in pos_list:
            positions.append((pos, word))
    positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in positions)


class OpenAlexSearch(BasePaperSource):
    """OpenAlex 论文搜索客户端（无需 API Key）"""

    # OA 类型过滤，只取有 PDF 直链的
    _OA_FILTER = "open_access.is_oa:true"

    # 每次请求间隔（s），官方建议 0.1s/req，保守用 0.5
    _MIN_INTERVAL = 0.5

    def __init__(self):
        self._last_request_time = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._MIN_INTERVAL:
            time.sleep(self._MIN_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def search(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "smart",
        sort_order: str = "descending",
        category: Optional[str] = None,
    ) -> List[PaperInfo]:
        """
        搜索 OpenAlex 论文。

        Args:
            query: 搜索关键词
            max_results: 最多返回数量（上限 50）
            sort_by: smart / relevance / submitted / updated（与 arXiv 接口对齐）
            sort_order: descending / ascending
            category: 暂不支持按 arXiv 分类过滤，忽略
        """
        max_results = min(max_results, 50)
        fetch = max_results * 3 if sort_by == "smart" else max_results
        fetch = min(fetch, 100)

        # OpenAlex sort_by 映射
        _sort_map = {
            "smart": "relevance_score",
            "relevance": "relevance_score",
            "submitted": "publication_date",
            "updated": "publication_date",
        }
        oa_sort = _sort_map.get(sort_by, "relevance_score")
        # OpenAlex 只有 desc，asc 通过 sort_order 控制（它默认 desc）
        sort_param = f"{oa_sort}:desc" if sort_order == "descending" else f"{oa_sort}:asc"

        fields = (
            "id,ids,title,abstract_inverted_index,authorships,"
            "publication_date,publication_year,open_access,"
            "primary_location,best_oa_location,cited_by_count,"
            "topics"
        )

        params = urllib.parse.urlencode({
            "search": query,
            "filter": self._OA_FILTER,
            "sort": sort_param,
            "per-page": fetch,
            "select": fields,
        })
        url = f"{_BASE}/works?{params}"

        self._throttle()
        try:
            data = _get(url)
        except Exception as e:
            print(f"[OpenAlex] 搜索请求失败: {e}")
            return []

        results_raw = data.get("results") or []
        papers = [_parse_work(w, i) for i, w in enumerate(results_raw)]

        if sort_by == "smart":
            papers = self._smart_sort(papers, max_results)
        else:
            papers = papers[:max_results]

        return papers

    def _smart_sort(self, papers: List[PaperInfo], max_results: int) -> List[PaperInfo]:
        """综合相关性、时间、引用数排序"""
        now = datetime.now()
        max_cite = max((p.citation_count or 0 for p in papers), default=1) or 1

        for p in papers:
            rank = getattr(p, "_relevance_rank", 0)
            relevance_score = 1.0 / (1.0 + rank * 0.1)

            pub_date = getattr(p, "_published_date", None)
            if pub_date:
                days_ago = (now - pub_date).days
                time_score = 1.0 / (1.0 + days_ago / 180)
            else:
                time_score = 0.5

            cite = p.citation_count or 0
            cite_score = cite / max_cite  # 归一化

            # 相关性 50%、时间 30%、引用 20%
            p._smart_score = 0.5 * relevance_score + 0.3 * time_score + 0.2 * cite_score

        papers.sort(key=lambda p: getattr(p, "_smart_score", 0), reverse=True)
        return papers[:max_results]

    def get_paper(self, paper_id: str) -> Optional[PaperInfo]:
        """
        通过 arXiv ID 或 OpenAlex ID（oa_Wxxxxxx）查询单篇论文。
        """
        self._throttle()
        try:
            if paper_id.startswith("oa_W"):
                openalex_id = paper_id[3:]  # 去掉 oa_ 前缀
                url = f"{_BASE}/works/{openalex_id}"
            else:
                # 尝试 arXiv ID
                url = f"{_BASE}/works/https://doi.org/10.48550/arXiv.{paper_id}"

            data = _get(url)
            if "id" in data:
                return _parse_work(data)
        except Exception as e:
            print(f"[OpenAlex] 查询论文失败 {paper_id}: {e}")
        return None

    def download_pdf(self, paper_id: str, save_path: str) -> bool:
        """
        下载 PDF 到 save_path。
        先查 get_paper 拿到 pdf_url，再 urllib 下载。
        """
        # 如果文件已存在且有效，跳过
        if os.path.exists(save_path) and os.path.getsize(save_path) > 10000:
            return True

        paper = self.get_paper(paper_id)
        if not paper or not paper.pdf_url:
            print(f"[OpenAlex] 无法获取 PDF 直链: {paper_id}")
            return False

        pdf_url = paper.pdf_url
        print(f"[OpenAlex] 下载 PDF: {pdf_url}")

        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    pdf_url,
                    headers={
                        **_HEADERS,
                        "User-Agent": "Mozilla/5.0 (compatible; PaperReaderMCP/1.0)",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    content = resp.read()

                if len(content) < 10000:
                    print(f"[OpenAlex] 下载内容太小 ({len(content)} bytes)，可能不是 PDF")
                    continue

                with open(save_path, "wb") as f:
                    f.write(content)

                # 验证 PDF 头
                if content[:4] == b"%PDF":
                    print(f"[OpenAlex] PDF 下载成功")
                    return True
                else:
                    os.remove(save_path)
                    print(f"[OpenAlex] 非 PDF 内容，跳过")
                    return False

            except Exception as e:
                print(f"[OpenAlex] 下载失败 (尝试 {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep((attempt + 1) * 2)

        return False
