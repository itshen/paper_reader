"""
arXiv 论文搜索模块

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import os
import time
import arxiv
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PaperInfo:
    """论文信息"""
    arxiv_id: str
    title: str
    abstract: str
    authors: List[str]
    published: str
    pdf_url: str
    categories: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "published": self.published,
            "pdf_url": self.pdf_url,
            "categories": self.categories
        }


class ArxivSearch:
    """arXiv 搜索客户端"""
    
    def __init__(self):
        self.client = arxiv.Client()
    
    # 常用分类映射
    CATEGORIES = {
        "cs.AI": "人工智能",
        "cs.CL": "计算语言学/NLP",
        "cs.CV": "计算机视觉",
        "cs.LG": "机器学习",
        "cs.NE": "神经网络/进化计算",
        "cs.IR": "信息检索",
        "cs.RO": "机器人",
        "cs.SE": "软件工程",
        "cs.CR": "密码学与安全",
        "cs.DB": "数据库",
        "cs.DC": "分布式计算",
        "cs.HC": "人机交互",
        "stat.ML": "统计机器学习",
        "math.OC": "优化与控制",
        "eess.AS": "音频与语音处理",
        "eess.IV": "图像与视频处理",
        "physics": "物理学",
        "quant-ph": "量子物理",
        "cond-mat": "凝聚态物理",
        "math": "数学",
        "q-bio": "定量生物学",
        "q-fin": "定量金融",
        "econ": "经济学",
    }
    
    def search(
        self, 
        query: str, 
        max_results: int = 10,
        sort_by: str = "smart",
        sort_order: str = "descending",
        category: Optional[str] = None
    ) -> List[PaperInfo]:
        """
        搜索论文
        
        Args:
            query: 搜索关键词
            max_results: 最大返回数量
            sort_by: 排序方式：
                     - "smart": 智能排序（相关性+时间综合，默认）
                     - "relevance": 仅按相关性
                     - "submitted": 仅按提交时间
                     - "updated": 仅按更新时间
            sort_order: 排序顺序 - "descending"(降序/最新优先), "ascending"(升序/最早优先)
            category: 分类过滤，如 "cs.AI", "cs.LG" 等
        
        Returns:
            论文信息列表
        """
        # 智能排序：先获取更多结果，然后重新排序
        is_smart_sort = sort_by.lower() == "smart"
        
        # 解析排序方式
        sort_criterion_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "smart": arxiv.SortCriterion.Relevance,  # 智能排序先按相关性获取
            "submitted": arxiv.SortCriterion.SubmittedDate,
            "updated": arxiv.SortCriterion.LastUpdatedDate,
        }
        sort_criterion = sort_criterion_map.get(sort_by.lower(), arxiv.SortCriterion.Relevance)
        
        # 解析排序顺序
        sort_order_map = {
            "descending": arxiv.SortOrder.Descending,
            "ascending": arxiv.SortOrder.Ascending,
        }
        arxiv_sort_order = sort_order_map.get(sort_order.lower(), arxiv.SortOrder.Descending)
        
        # 如果指定了分类，添加到查询中
        search_query = query
        if category:
            search_query = f"cat:{category} AND ({query})"
        
        # 智能排序时获取更多结果用于重排序
        fetch_count = max_results * 3 if is_smart_sort else max_results
        fetch_count = min(fetch_count, 100)  # 最多获取 100 篇
        
        search = arxiv.Search(
            query=search_query,
            max_results=fetch_count,
            sort_by=sort_criterion,
            sort_order=arxiv_sort_order
        )
        
        results = []
        for idx, paper in enumerate(self.client.results(search)):
            # 提取 arXiv ID（去掉版本号）
            arxiv_id = paper.entry_id.split("/")[-1]
            if "v" in arxiv_id:
                arxiv_id = arxiv_id.rsplit("v", 1)[0]
            
            info = PaperInfo(
                arxiv_id=arxiv_id,
                title=paper.title.replace("\n", " "),
                abstract=paper.summary.replace("\n", " "),
                authors=[author.name for author in paper.authors],
                published=paper.published.strftime("%Y-%m-%d"),
                pdf_url=paper.pdf_url,
                categories=paper.categories
            )
            # 保存原始排名用于智能排序
            info._relevance_rank = idx
            info._published_date = paper.published
            results.append(info)
        
        # 智能排序：综合相关性和时间
        if is_smart_sort and results:
            results = self._smart_sort(results, max_results)
        else:
            results = results[:max_results]
        
        return results
    
    def _smart_sort(self, papers: List[PaperInfo], max_results: int) -> List[PaperInfo]:
        """
        智能排序：综合相关性和时间
        
        计算方式：
        - 相关性分数：根据原始排名，第1名=1.0，越往后越低
        - 时间分数：根据发布时间，最新的=1.0，一年前的=0.5，更早的更低
        - 综合分数 = 0.6 * 相关性分数 + 0.4 * 时间分数
        """
        now = datetime.now()
        
        for paper in papers:
            # 相关性分数（指数衰减）
            rank = getattr(paper, '_relevance_rank', 0)
            relevance_score = 1.0 / (1.0 + rank * 0.1)  # 排名越靠后分数越低
            
            # 时间分数
            pub_date = getattr(paper, '_published_date', None)
            if pub_date:
                days_ago = (now - pub_date.replace(tzinfo=None)).days
                # 时间衰减：一年约365天，使用指数衰减
                time_score = 1.0 / (1.0 + days_ago / 180)  # 半年衰减到0.5
            else:
                time_score = 0.5
            
            # 综合分数：相关性权重60%，时间权重40%
            paper._smart_score = 0.6 * relevance_score + 0.4 * time_score
        
        # 按综合分数降序排序
        papers.sort(key=lambda p: getattr(p, '_smart_score', 0), reverse=True)
        
        return papers[:max_results]
    
    def get_paper(self, arxiv_id: str) -> Optional[PaperInfo]:
        """
        通过 arXiv ID 获取论文信息
        
        Args:
            arxiv_id: arXiv 论文 ID，如 "2301.12345"
        
        Returns:
            论文信息，未找到返回 None
        """
        search = arxiv.Search(id_list=[arxiv_id])
        
        try:
            for paper in self.client.results(search):
                # 提取 arXiv ID
                paper_id = paper.entry_id.split("/")[-1]
                if "v" in paper_id:
                    paper_id = paper_id.rsplit("v", 1)[0]
                
                return PaperInfo(
                    arxiv_id=paper_id,
                    title=paper.title.replace("\n", " "),
                    abstract=paper.summary.replace("\n", " "),
                    authors=[author.name for author in paper.authors],
                    published=paper.published.strftime("%Y-%m-%d"),
                    pdf_url=paper.pdf_url,
                    categories=paper.categories
                )
        except Exception:
            pass
        
        return None
    
    def download_pdf(self, arxiv_id: str, save_path: str, max_retries: int = 3) -> bool:
        """
        下载论文 PDF（带重试和验证）
        
        Args:
            arxiv_id: arXiv 论文 ID
            save_path: 保存路径
            max_retries: 最大重试次数
        
        Returns:
            是否下载成功
        """
        # 如果文件已存在但损坏，先删除
        if os.path.exists(save_path):
            if not self._verify_pdf(save_path):
                print(f"[ArxivSearch] 检测到损坏的 PDF，删除后重新下载")
                os.remove(save_path)
            else:
                return True  # 文件已存在且完整
        
        search = arxiv.Search(id_list=[arxiv_id])
        
        for attempt in range(max_retries):
            try:
                print(f"[ArxivSearch] 下载 PDF (尝试 {attempt + 1}/{max_retries}): {arxiv_id}")
                
                for paper in self.client.results(search):
                    paper.download_pdf(filename=save_path)
                    
                    # 验证下载的文件
                    if self._verify_pdf(save_path):
                        print(f"[ArxivSearch] PDF 下载成功: {arxiv_id}")
                        return True
                    else:
                        print(f"[ArxivSearch] PDF 验证失败，删除后重试")
                        if os.path.exists(save_path):
                            os.remove(save_path)
                
            except Exception as e:
                print(f"[ArxivSearch] 下载失败 (尝试 {attempt + 1}): {e}")
                if os.path.exists(save_path):
                    os.remove(save_path)
            
            # 重试前等待
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2, 4, 6 秒
                print(f"[ArxivSearch] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        
        return False
    
    def _verify_pdf(self, file_path: str) -> bool:
        """
        验证 PDF 文件是否完整
        
        Args:
            file_path: 文件路径
        
        Returns:
            是否有效
        """
        if not os.path.exists(file_path):
            return False
        
        # 检查文件大小（PDF 通常至少 10KB）
        file_size = os.path.getsize(file_path)
        if file_size < 10000:
            print(f"[ArxivSearch] PDF 文件太小: {file_size} 字节")
            return False
        
        # 检查 PDF 文件头
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF'):
                    print(f"[ArxivSearch] 无效的 PDF 文件头")
                    return False
                
                # 检查文件尾（PDF 应该以 %%EOF 结尾）
                f.seek(-128, 2)  # 从文件末尾往前 128 字节
                tail = f.read()
                if b'%%EOF' not in tail:
                    print(f"[ArxivSearch] PDF 文件不完整（缺少 EOF 标记）")
                    return False
        except Exception as e:
            print(f"[ArxivSearch] 验证 PDF 时出错: {e}")
            return False
        
        return True
