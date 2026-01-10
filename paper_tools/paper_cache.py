"""
论文缓存管理模块

淘汰策略：
1. 先删除超过 3 个月的
2. 然后删除最大的文件

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass


@dataclass
class CachedPaper:
    """缓存的论文信息"""
    arxiv_id: str
    title: str
    abstract: str
    authors: str  # JSON 字符串
    published: str
    pdf_path: Optional[str]
    markdown_path: Optional[str]
    file_size: int
    created_at: str
    last_accessed: str
    
    def to_dict(self) -> Dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": json.loads(self.authors) if self.authors else [],
            "published": self.published,
            "pdf_path": self.pdf_path,
            "markdown_path": self.markdown_path,
            "file_size": self.file_size,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed
        }


class PaperCache:
    """论文缓存管理器"""
    
    def __init__(
        self, 
        db_path: str,
        pdf_dir: str,
        markdown_dir: str,
        max_size_bytes: int = 1024 * 1024 * 1024,  # 1GB
        max_age_days: int = 90  # 3 个月
    ):
        """
        初始化缓存管理器
        
        Args:
            db_path: 数据库路径
            pdf_dir: PDF 存储目录
            markdown_dir: Markdown 存储目录
            max_size_bytes: 最大缓存大小（字节）
            max_age_days: 最大缓存天数
        """
        self.db_path = db_path
        self.pdf_dir = pdf_dir
        self.markdown_dir = markdown_dir
        self.max_size_bytes = max_size_bytes
        self.max_age_days = max_age_days
        
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(pdf_dir, exist_ok=True)
        os.makedirs(markdown_dir, exist_ok=True)
        
        # 初始化数据库
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    arxiv_id TEXT PRIMARY KEY,
                    title TEXT,
                    abstract TEXT,
                    authors TEXT,
                    published TEXT,
                    pdf_path TEXT,
                    markdown_path TEXT,
                    file_size INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_accessed TEXT
                )
            """)
            conn.commit()
    
    def get(self, arxiv_id: str) -> Optional[CachedPaper]:
        """
        获取缓存的论文
        
        Args:
            arxiv_id: arXiv 论文 ID
        
        Returns:
            缓存的论文信息，未找到返回 None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM papers WHERE arxiv_id = ?",
                (arxiv_id,)
            )
            row = cursor.fetchone()
            
            if row:
                # 更新最后访问时间
                now = datetime.now().isoformat()
                conn.execute(
                    "UPDATE papers SET last_accessed = ? WHERE arxiv_id = ?",
                    (now, arxiv_id)
                )
                conn.commit()
                
                return CachedPaper(
                    arxiv_id=row[0],
                    title=row[1],
                    abstract=row[2],
                    authors=row[3],
                    published=row[4],
                    pdf_path=row[5],
                    markdown_path=row[6],
                    file_size=row[7] or 0,
                    created_at=row[8],
                    last_accessed=now
                )
        
        return None
    
    def save(
        self,
        arxiv_id: str,
        title: str,
        abstract: str,
        authors: List[str],
        published: str,
        pdf_path: Optional[str] = None,
        markdown_path: Optional[str] = None
    ) -> CachedPaper:
        """
        保存论文到缓存
        
        Args:
            arxiv_id: arXiv 论文 ID
            title: 标题
            abstract: 摘要
            authors: 作者列表
            published: 发布日期
            pdf_path: PDF 文件路径
            markdown_path: Markdown 文件路径
        
        Returns:
            缓存的论文信息
        """
        now = datetime.now().isoformat()
        authors_json = json.dumps(authors, ensure_ascii=False)
        
        # 计算文件大小
        file_size = 0
        if pdf_path and os.path.exists(pdf_path):
            file_size += os.path.getsize(pdf_path)
        if markdown_path and os.path.exists(markdown_path):
            file_size += os.path.getsize(markdown_path)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO papers 
                (arxiv_id, title, abstract, authors, published, pdf_path, markdown_path, file_size, created_at, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                arxiv_id, title, abstract, authors_json, published,
                pdf_path, markdown_path, file_size, now, now
            ))
            conn.commit()
        
        # 执行缓存清理
        self.cleanup()
        
        return CachedPaper(
            arxiv_id=arxiv_id,
            title=title,
            abstract=abstract,
            authors=authors_json,
            published=published,
            pdf_path=pdf_path,
            markdown_path=markdown_path,
            file_size=file_size,
            created_at=now,
            last_accessed=now
        )
    
    def update_paths(
        self,
        arxiv_id: str,
        pdf_path: Optional[str] = None,
        markdown_path: Optional[str] = None
    ):
        """
        更新论文的文件路径
        
        Args:
            arxiv_id: arXiv 论文 ID
            pdf_path: PDF 文件路径
            markdown_path: Markdown 文件路径
        """
        # 计算文件大小
        file_size = 0
        if pdf_path and os.path.exists(pdf_path):
            file_size += os.path.getsize(pdf_path)
        if markdown_path and os.path.exists(markdown_path):
            file_size += os.path.getsize(markdown_path)
        
        with sqlite3.connect(self.db_path) as conn:
            if pdf_path:
                conn.execute(
                    "UPDATE papers SET pdf_path = ?, file_size = ? WHERE arxiv_id = ?",
                    (pdf_path, file_size, arxiv_id)
                )
            if markdown_path:
                conn.execute(
                    "UPDATE papers SET markdown_path = ?, file_size = ? WHERE arxiv_id = ?",
                    (markdown_path, file_size, arxiv_id)
                )
            conn.commit()
        
        # 执行缓存清理
        self.cleanup()
    
    def get_pdf_path(self, arxiv_id: str) -> str:
        """获取 PDF 存储路径"""
        # 将 arxiv_id 中的特殊字符替换
        safe_id = arxiv_id.replace("/", "_").replace(":", "_")
        return os.path.join(self.pdf_dir, f"{safe_id}.pdf")
    
    def get_markdown_path(self, arxiv_id: str) -> str:
        """获取 Markdown 存储路径"""
        safe_id = arxiv_id.replace("/", "_").replace(":", "_")
        return os.path.join(self.markdown_dir, f"{safe_id}.md")
    
    def get_total_size(self) -> int:
        """获取缓存总大小（字节）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT SUM(file_size) FROM papers")
            result = cursor.fetchone()[0]
            return result or 0
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*), SUM(file_size) FROM papers")
            count, total_size = cursor.fetchone()
            
            return {
                "paper_count": count or 0,
                "total_size_bytes": total_size or 0,
                "total_size_mb": round((total_size or 0) / 1024 / 1024, 2),
                "max_size_mb": round(self.max_size_bytes / 1024 / 1024, 2),
                "max_age_days": self.max_age_days
            }
    
    def cleanup(self):
        """
        清理缓存
        
        淘汰策略：
        1. 先删除超过 max_age_days 的
        2. 如果仍超过 max_size_bytes，删除最大的文件
        """
        # 1. 删除超过指定天数的
        cutoff_date = (datetime.now() - timedelta(days=self.max_age_days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            # 获取过期的论文
            cursor = conn.execute(
                "SELECT arxiv_id, pdf_path, markdown_path FROM papers WHERE created_at < ?",
                (cutoff_date,)
            )
            expired = cursor.fetchall()
            
            for arxiv_id, pdf_path, markdown_path in expired:
                self._delete_paper_files(pdf_path, markdown_path)
                conn.execute("DELETE FROM papers WHERE arxiv_id = ?", (arxiv_id,))
                print(f"[PaperCache] 清理过期论文: {arxiv_id}")
            
            conn.commit()
        
        # 2. 如果仍超过大小限制，删除最大的文件
        while self.get_total_size() > self.max_size_bytes:
            with sqlite3.connect(self.db_path) as conn:
                # 获取最大的论文
                cursor = conn.execute(
                    "SELECT arxiv_id, pdf_path, markdown_path FROM papers ORDER BY file_size DESC LIMIT 1"
                )
                row = cursor.fetchone()
                
                if not row:
                    break
                
                arxiv_id, pdf_path, markdown_path = row
                self._delete_paper_files(pdf_path, markdown_path)
                conn.execute("DELETE FROM papers WHERE arxiv_id = ?", (arxiv_id,))
                conn.commit()
                print(f"[PaperCache] 清理大文件论文: {arxiv_id}")
    
    def _delete_paper_files(self, pdf_path: Optional[str], markdown_path: Optional[str]):
        """删除论文文件"""
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception as e:
                print(f"[PaperCache] 删除 PDF 失败: {e}")
        
        if markdown_path and os.path.exists(markdown_path):
            try:
                os.remove(markdown_path)
            except Exception as e:
                print(f"[PaperCache] 删除 Markdown 失败: {e}")
    
    def delete(self, arxiv_id: str):
        """
        删除指定论文的缓存
        
        Args:
            arxiv_id: arXiv 论文 ID
        """
        paper = self.get(arxiv_id)
        if paper:
            self._delete_paper_files(paper.pdf_path, paper.markdown_path)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM papers WHERE arxiv_id = ?", (arxiv_id,))
                conn.commit()
    
    def clear_all(self):
        """清空所有缓存"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT pdf_path, markdown_path FROM papers")
            for pdf_path, markdown_path in cursor.fetchall():
                self._delete_paper_files(pdf_path, markdown_path)
            
            conn.execute("DELETE FROM papers")
            conn.commit()
        
        print("[PaperCache] 已清空所有缓存")
