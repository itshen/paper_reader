"""
MCP 服务器 - 论文搜索与阅读

运行方式:
    python3.11 server.py

访问地址:
    Web 界面: http://localhost:8633
    MCP 端点: http://localhost:8633/mcp

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import os
import sys
import json
from typing import Optional
import yaml

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth import AuthManager
from api_logger import APILogger
from paper_tools import ArxivSearch, PaperCache, PDFConverter


# ==================== 配置加载 ====================

def load_config() -> tuple:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), config_path
    return {}, config_path


config, config_path = load_config()

# 服务器配置
SERVER_NAME = config.get("server", {}).get("name", "Paper Reader MCP")
SERVER_HOST = config.get("server", {}).get("host", "0.0.0.0")
SERVER_PORT = config.get("server", {}).get("port", 8633)

# 数据目录
DATA_DIR = config.get("storage", {}).get("data_dir", "./data")
DB_PATH = os.path.join(DATA_DIR, "auth.db")
LOG_DB_PATH = os.path.join(DATA_DIR, "api_logs.db")

# 论文缓存配置
PAPERS_DIR = os.path.join(DATA_DIR, "papers")
PAPERS_DB_PATH = os.path.join(PAPERS_DIR, "papers.db")
PAPERS_PDF_DIR = os.path.join(PAPERS_DIR, "pdf")
PAPERS_MD_DIR = os.path.join(PAPERS_DIR, "markdown")

# 论文缓存限制
paper_config = config.get("papers", {})
PAPERS_MAX_SIZE_MB = paper_config.get("max_size_mb", 1024)  # 默认 1GB
PAPERS_MAX_AGE_DAYS = paper_config.get("max_age_days", 90)  # 默认 3 个月

# 创建认证管理器
auth_manager = AuthManager(DB_PATH, config)

# 创建日志记录器
api_logger = APILogger(LOG_DB_PATH, max_records=1000)

# 创建论文工具
arxiv_search = ArxivSearch()
paper_cache = PaperCache(
    db_path=PAPERS_DB_PATH,
    pdf_dir=PAPERS_PDF_DIR,
    markdown_dir=PAPERS_MD_DIR,
    max_size_bytes=PAPERS_MAX_SIZE_MB * 1024 * 1024,
    max_age_days=PAPERS_MAX_AGE_DAYS
)
pdf_converter = PDFConverter()

# 存储 MCP 会话的 token
mcp_session_tokens: dict = {}


# ==================== MCP 服务器实例 ====================

mcp = FastMCP(SERVER_NAME, host=SERVER_HOST, port=SERVER_PORT)


# ==================== MCP Token 验证 ====================

def verify_mcp_token(token: str) -> bool:
    """验证 MCP API Token"""
    if not token:
        return False
    return auth_manager.verify_api_token(token)


def get_current_session_token() -> str:
    """获取当前 MCP 会话的 token"""
    if len(mcp_session_tokens) == 1:
        return list(mcp_session_tokens.values())[0]
    if mcp_session_tokens:
        return list(mcp_session_tokens.values())[-1]
    return ""


# ==================== 论文工具 ====================

@mcp.tool()
def search_papers(
    query: str,
    max_results: int = 10,
    sort_by: str = "smart",
    sort_order: str = "descending",
    category: Optional[str] = None
) -> str:
    """
    搜索 arXiv 论文
    
    通过关键词搜索学术论文，返回标题、摘要等信息。
    
    Args:
        query: 搜索关键词，如 "machine learning"、"transformer attention"
        max_results: 最大返回数量，默认 10，最多 50
        sort_by: 排序方式，可选值：
                 - "smart": 智能排序（默认），综合相关性和时间，越相关且越新的排越前
                 - "relevance": 仅按相关性排序
                 - "submitted": 仅按提交时间排序
                 - "updated": 仅按更新时间排序
        sort_order: 排序顺序，可选值：
                    - "descending": 降序，最新/最相关优先（默认）
                    - "ascending": 升序，最早/最不相关优先
        category: 分类过滤，**建议指定分类以获得更精准的结果**。常用分类：
                  - cs.AI: 人工智能
                  - cs.CL: 计算语言学/NLP（推荐用于 LLM、文本处理）
                  - cs.CV: 计算机视觉（推荐用于图像、视频）
                  - cs.LG: 机器学习（推荐用于通用 ML 算法）
                  - cs.NE: 神经网络/进化计算
                  - cs.IR: 信息检索（推荐用于搜索、推荐系统）
                  - cs.RO: 机器人
                  - cs.SE: 软件工程
                  - stat.ML: 统计机器学习
                  - eess.AS: 音频与语音处理
                  - eess.IV: 图像与视频处理
                  不指定分类会搜索全部领域，结果可能不够精准
    
    Returns:
        论文列表，包含 arXiv ID、标题、摘要、作者、发布日期、分类
    """
    token = get_current_session_token()
    if not verify_mcp_token(token):
        return "认证失败：请在 MCP 客户端配置有效的 API Token"
    
    try:
        # 限制最大结果数
        max_results = min(max_results, 50)
        
        # 搜索论文
        papers = arxiv_search.search(
            query,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
            category=category
        )
        
        if not papers:
            return (
                f"未找到与 \"{query}\" 相关的论文\n\n"
                f"💡 建议：\n"
                f"1. 尝试使用英文关键词搜索（arXiv 论文主要是英文）\n"
                f"2. 使用更通用或更具体的关键词\n"
                f"3. 检查拼写是否正确"
            )
        
        # 格式化结果
        sort_by_names = {
            "smart": "智能排序（相关性+时间）",
            "relevance": "相关性",
            "submitted": "提交时间",
            "updated": "更新时间"
        }
        sort_order_names = {"descending": "降序", "ascending": "升序"}
        sort_info = f"{sort_by_names.get(sort_by, sort_by)} ({sort_order_names.get(sort_order, sort_order)})"
        
        lines = [f"📚 搜索结果：\"{query}\"（共 {len(papers)} 篇）"]
        lines.append(f"🔄 排序: {sort_info}")
        if category:
            lines.append(f"🏷️ 分类过滤: {category}")
        lines.append("")
        
        for i, paper in enumerate(papers, 1):
            # 截断摘要
            abstract = paper.abstract
            if len(abstract) > 300:
                abstract = abstract[:300] + "..."
            
            # 作者（最多显示 3 个）
            authors = paper.authors[:3]
            if len(paper.authors) > 3:
                authors.append(f"等 {len(paper.authors)} 人")
            authors_str = ", ".join(authors)
            
            lines.append(f"---\n")
            lines.append(f"**{i}. {paper.title}**\n")
            lines.append(f"📌 arXiv ID: {paper.arxiv_id}")
            lines.append(f"👤 作者: {authors_str}")
            lines.append(f"📅 发布日期: {paper.published}")
            lines.append(f"🏷️ 分类: {', '.join(paper.categories[:3])}")
            lines.append(f"\n📝 摘要:\n{abstract}\n")
        
        lines.append("---")
        lines.append("\n💡 提示：")
        lines.append("• 使用 `get_paper_content(arXiv ID)` 获取论文全文")
        lines.append("• arXiv 论文主要是英文，建议使用英文关键词搜索效果更好")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ 搜索失败: {str(e)}"


@mcp.tool()
def get_paper_content(
    paper_id: str,
    page: int = 1,
    max_chars: int = 20000
) -> str:
    """
    获取论文全文（Markdown 格式，支持分页）
    
    通过 arXiv ID 下载论文 PDF 并转换为 Markdown 格式返回。
    论文会缓存在本地，超过 1GB 或 3 个月会自动清理。
    
    Args:
        paper_id: arXiv 论文 ID，如 "2301.12345"
        page: 页码，从 1 开始，默认第 1 页
        max_chars: 每页最大字符数，默认 20000，范围 1000-100000
                   你可以根据需要调整此值：
                   - 如果只需要快速浏览，可以设置较小值如 5000
                   - 如果需要完整阅读，可以设置较大值如 50000
                   - 如果 Token 预算有限，建议使用较小值分多次获取
    
    Returns:
        论文的 Markdown 内容（分页），包含：
        - 论文元信息（标题、作者、日期）
        - 摘要（Abstract）
        - 分页信息（当前页/总页数、总字符数）
        - 正文内容
        - 下一页获取提示（如有）
    """
    token = get_current_session_token()
    if not verify_mcp_token(token):
        return "认证失败：请在 MCP 客户端配置有效的 API Token"
    
    try:
        # 限制 max_chars 范围
        max_chars = max(1000, min(max_chars, 100000))
        page = max(1, page)
        
        # 1. 检查缓存
        cached = paper_cache.get(paper_id)
        content = None
        title = None
        abstract = None
        authors = None
        published = None
        source = "本地缓存"
        
        if cached and cached.markdown_path and os.path.exists(cached.markdown_path):
            # 直接读取缓存的 Markdown
            with open(cached.markdown_path, "r", encoding="utf-8") as f:
                content = f.read()
            title = cached.title
            abstract = cached.abstract if hasattr(cached, 'abstract') else None
            published = cached.published
            # 从缓存获取作者
            import json
            try:
                authors = json.loads(cached.authors) if cached.authors else []
            except:
                authors = []
        
        if not content:
            # 2. 获取论文信息
            paper_info = arxiv_search.get_paper(paper_id)
            if not paper_info:
                return f"❌ 未找到论文: {paper_id}"
            
            title = paper_info.title
            abstract = paper_info.abstract
            authors = paper_info.authors
            published = paper_info.published
            source = "新下载"
            
            # 3. 保存论文元数据到缓存
            paper_cache.save(
                arxiv_id=paper_id,
                title=title,
                abstract=abstract,
                authors=authors,
                published=published
            )
            
            # 4. 下载 PDF（自动验证和重试）
            pdf_path = paper_cache.get_pdf_path(paper_id)
            
            print(f"[Paper] 正在下载 PDF: {paper_id}")
            success = arxiv_search.download_pdf(paper_id, pdf_path)
            if not success:
                return (
                    f"❌ 下载 PDF 失败: {paper_id}\n\n"
                    f"可能原因：\n"
                    f"1. 网络连接不稳定\n"
                    f"2. arXiv 服务器暂时不可用\n"
                    f"3. 该论文 PDF 暂时无法访问\n\n"
                    f"💡 建议稍后重试"
                )
            
            # 5. 转换为 Markdown
            markdown_path = paper_cache.get_markdown_path(paper_id)
            
            print(f"[Paper] 正在转换 PDF 为 Markdown: {paper_id}")
            content = pdf_converter.convert(pdf_path, markdown_path)
            
            # 6. 更新缓存路径
            paper_cache.update_paths(paper_id, pdf_path=pdf_path, markdown_path=markdown_path)
        
        # 计算分页
        total_chars = len(content)
        total_pages = (total_chars + max_chars - 1) // max_chars  # 向上取整
        total_pages = max(1, total_pages)
        
        # 确保页码有效
        if page > total_pages:
            page = total_pages
        
        # 截取当前页内容
        start_idx = (page - 1) * max_chars
        end_idx = min(start_idx + max_chars, total_chars)
        page_content = content[start_idx:end_idx]
        
        # 构建返回内容
        lines = []
        lines.append(f"📄 **{title}**\n")
        lines.append(f"📌 arXiv ID: {paper_id}")
        if authors:
            authors_str = ', '.join(authors[:5])
            if len(authors) > 5:
                authors_str += f" 等 {len(authors)} 人"
            lines.append(f"👤 作者: {authors_str}")
        lines.append(f"📅 发布日期: {published}")
        lines.append(f"💾 来源: {source}")
        lines.append("")
        
        # 添加摘要
        if abstract:
            lines.append("## 📝 摘要")
            lines.append("")
            lines.append(abstract)
            lines.append("")
        
        # 分页信息
        lines.append("---")
        lines.append(f"📊 **分页信息**: 第 {page}/{total_pages} 页 | 总字符数: {total_chars} | 每页: {max_chars} 字符")
        if total_pages > 1:
            if page < total_pages:
                lines.append(f"💡 使用 `get_paper_content(\"{paper_id}\", page={page + 1})` 获取下一页")
            if page > 1:
                lines.append(f"💡 使用 `get_paper_content(\"{paper_id}\", page={page - 1})` 获取上一页")
        lines.append("---")
        lines.append("")
        
        # 正文内容
        lines.append("## 📖 正文内容")
        lines.append("")
        lines.append(page_content)
        
        # 如果不是最后一页，提示内容被截断
        if page < total_pages:
            lines.append("")
            lines.append("---")
            lines.append(f"⚠️ 内容已截断，使用 `get_paper_content(\"{paper_id}\", page={page + 1})` 获取下一页")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ 获取论文失败: {str(e)}"


# ==================== 工具调用映射（Web 测试用） ====================

TOOL_MAP = {
    "search_papers": lambda p: _search_papers_internal(
        p.get("query", ""),
        int(p.get("max_results", 10) or 10),
        p.get("sort_by", "relevance"),
        p.get("sort_order", "descending"),
        p.get("category", None)
    ),
    "get_paper_content": lambda p: _get_paper_content_internal(
        p.get("paper_id", ""),
        int(p.get("page", 1) or 1),
        int(p.get("max_chars", 20000) or 20000)
    ),
}


# ==================== 论文工具内部函数（Web 测试用） ====================

def _search_papers_internal(
    query: str,
    max_results: int = 10,
    sort_by: str = "smart",
    sort_order: str = "descending",
    category: Optional[str] = None
) -> str:
    """搜索论文（内部函数）"""
    try:
        max_results = min(max_results, 50)
        papers = arxiv_search.search(
            query,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
            category=category
        )
        
        if not papers:
            return (
                f"未找到与 \"{query}\" 相关的论文\n\n"
                f"💡 建议：\n"
                f"1. 尝试使用英文关键词搜索（arXiv 论文主要是英文）\n"
                f"2. 使用更通用或更具体的关键词\n"
                f"3. 检查拼写是否正确"
            )
        
        sort_by_names = {
            "smart": "智能排序（相关性+时间）",
            "relevance": "相关性",
            "submitted": "提交时间",
            "updated": "更新时间"
        }
        sort_order_names = {"descending": "降序", "ascending": "升序"}
        sort_info = f"{sort_by_names.get(sort_by, sort_by)} ({sort_order_names.get(sort_order, sort_order)})"
        
        lines = [f"📚 搜索结果：\"{query}\"（共 {len(papers)} 篇）"]
        lines.append(f"🔄 排序: {sort_info}")
        if category:
            lines.append(f"🏷️ 分类过滤: {category}")
        lines.append("")
        
        for i, paper in enumerate(papers, 1):
            abstract = paper.abstract
            if len(abstract) > 300:
                abstract = abstract[:300] + "..."
            
            authors = paper.authors[:3]
            if len(paper.authors) > 3:
                authors.append(f"等 {len(paper.authors)} 人")
            authors_str = ", ".join(authors)
            
            lines.append(f"---\n")
            lines.append(f"**{i}. {paper.title}**\n")
            lines.append(f"📌 arXiv ID: {paper.arxiv_id}")
            lines.append(f"👤 作者: {authors_str}")
            lines.append(f"📅 发布日期: {paper.published}")
            lines.append(f"🏷️ 分类: {', '.join(paper.categories[:3])}")
            lines.append(f"\n📝 摘要:\n{abstract}\n")
        
        lines.append("---")
        lines.append("\n💡 提示：")
        lines.append("• 使用 `get_paper_content(arXiv ID)` 获取论文全文")
        lines.append("• arXiv 论文主要是英文，建议使用英文关键词搜索效果更好")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ 搜索失败: {str(e)}"


def _get_paper_content_internal(paper_id: str, page: int = 1, max_chars: int = 20000) -> str:
    """获取论文全文（内部函数，支持分页）"""
    try:
        # 限制 max_chars 范围
        max_chars = max(1000, min(max_chars, 100000))
        page = max(1, page)
        
        cached = paper_cache.get(paper_id)
        content = None
        title = None
        abstract = None
        authors = None
        published = None
        source = "本地缓存"
        
        if cached and cached.markdown_path and os.path.exists(cached.markdown_path):
            with open(cached.markdown_path, "r", encoding="utf-8") as f:
                content = f.read()
            title = cached.title
            abstract = cached.abstract if hasattr(cached, 'abstract') else None
            published = cached.published
            import json
            try:
                authors = json.loads(cached.authors) if cached.authors else []
            except:
                authors = []
        
        if not content:
            paper_info = arxiv_search.get_paper(paper_id)
            if not paper_info:
                return f"❌ 未找到论文: {paper_id}"
            
            title = paper_info.title
            abstract = paper_info.abstract
            authors = paper_info.authors
            published = paper_info.published
            source = "新下载"
            
            paper_cache.save(
                arxiv_id=paper_id,
                title=title,
                abstract=abstract,
                authors=authors,
                published=published
            )
            
            pdf_path = paper_cache.get_pdf_path(paper_id)
            
            print(f"[Paper] 正在下载 PDF: {paper_id}")
            success = arxiv_search.download_pdf(paper_id, pdf_path)
            if not success:
                return (
                    f"❌ 下载 PDF 失败: {paper_id}\n\n"
                    f"可能原因：\n"
                    f"1. 网络连接不稳定\n"
                    f"2. arXiv 服务器暂时不可用\n"
                    f"3. 该论文 PDF 暂时无法访问\n\n"
                    f"💡 建议稍后重试"
                )
            
            markdown_path = paper_cache.get_markdown_path(paper_id)
            
            print(f"[Paper] 正在转换 PDF 为 Markdown: {paper_id}")
            content = pdf_converter.convert(pdf_path, markdown_path)
            
            paper_cache.update_paths(paper_id, pdf_path=pdf_path, markdown_path=markdown_path)
        
        # 计算分页
        total_chars = len(content)
        total_pages = (total_chars + max_chars - 1) // max_chars
        total_pages = max(1, total_pages)
        
        if page > total_pages:
            page = total_pages
        
        start_idx = (page - 1) * max_chars
        end_idx = min(start_idx + max_chars, total_chars)
        page_content = content[start_idx:end_idx]
        
        # 构建返回内容
        lines = []
        lines.append(f"📄 **{title}**\n")
        lines.append(f"📌 arXiv ID: {paper_id}")
        if authors:
            authors_str = ', '.join(authors[:5])
            if len(authors) > 5:
                authors_str += f" 等 {len(authors)} 人"
            lines.append(f"👤 作者: {authors_str}")
        lines.append(f"📅 发布日期: {published}")
        lines.append(f"💾 来源: {source}")
        lines.append("")
        
        if abstract:
            lines.append("## 📝 摘要")
            lines.append("")
            lines.append(abstract)
            lines.append("")
        
        lines.append("---")
        lines.append(f"📊 **分页信息**: 第 {page}/{total_pages} 页 | 总字符数: {total_chars} | 每页: {max_chars} 字符")
        if total_pages > 1:
            if page < total_pages:
                lines.append(f"💡 使用 `get_paper_content(\"{paper_id}\", page={page + 1})` 获取下一页")
            if page > 1:
                lines.append(f"💡 使用 `get_paper_content(\"{paper_id}\", page={page - 1})` 获取上一页")
        lines.append("---")
        lines.append("")
        lines.append("## 📖 正文内容")
        lines.append("")
        lines.append(page_content)
        
        if page < total_pages:
            lines.append("")
            lines.append("---")
            lines.append(f"⚠️ 内容已截断，使用 `get_paper_content(\"{paper_id}\", page={page + 1})` 获取下一页")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ 获取论文失败: {str(e)}"


# ==================== 运行服务器 ====================

def run_server():
    """运行 Web + MCP 服务器"""
    from contextlib import asynccontextmanager
    from fastapi import FastAPI, Request, Depends
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from fastapi.responses import JSONResponse, RedirectResponse
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from pydantic import BaseModel
    import uvicorn
    
    # Pydantic 模型
    class LoginRequest(BaseModel):
        username: str
        password: str
    
    class ChangePasswordRequest(BaseModel):
        new_password: str
    
    class CreateTokenRequest(BaseModel):
        name: str
    
    # MCP Session Manager
    session_manager = StreamableHTTPSessionManager(
        app=mcp._mcp_server,
        json_response=False,
        stateless=False,
    )
    
    @asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield
    
    # 创建 FastAPI 应用
    app = FastAPI(
        title=SERVER_NAME,
        description="论文搜索与阅读 MCP 服务",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan
    )
    
    # API 日志中间件
    import time as time_module
    from starlette.responses import Response
    
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        path = request.url.path
        
        # 跳过静态文件、页面请求和日志 API
        if (path.startswith("/static") or 
            path == "/favicon.ico" or 
            path.startswith("/api/logs") or
            not (path.startswith("/api") or path == "/mcp")):
            return await call_next(request)
        
        start_time = time_module.time()
        
        # 获取请求信息
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")
        method = request.method
        log_type = "mcp" if path == "/mcp" else "api"
        
        # 获取请求体
        request_body = None
        if method in ["POST", "PUT", "PATCH"] and log_type == "api":
            try:
                body = await request.body()
                if body:
                    request_body = json.loads(body.decode("utf-8"))
            except:
                pass
        
        # 调用下一个处理器
        response = await call_next(request)
        
        # 读取响应体
        response_body = None
        if response.status_code == 200:
            body_bytes = b""
            async for chunk in response.body_iterator:
                body_bytes += chunk
            
            try:
                response_body = json.loads(body_bytes.decode("utf-8"))
            except:
                response_body = body_bytes.decode("utf-8")[:500] if body_bytes else None
            
            # 重新构建响应
            response = Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
        
        # 计算耗时
        duration_ms = int((time_module.time() - start_time) * 1000)
        
        # 记录日志
        api_logger.log(
            log_type=log_type,
            method=method,
            path=path,
            request_body=request_body,
            response_status=response.status_code,
            response_body=response_body,
            duration_ms=duration_ms,
            client_ip=client_ip,
            user_agent=user_agent[:200] if user_agent else None
        )
        
        return response
    
    # 静态文件
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    # 模板
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    templates = Jinja2Templates(directory=templates_dir)
    
    # ==================== 辅助函数 ====================
    
    def check_auth(request: Request) -> bool:
        """检查是否已登录"""
        session_id = request.cookies.get("session_id")
        if not session_id:
            return False
        return auth_manager.verify_session(session_id) is not None
    
    def get_admin_id(request: Request) -> Optional[int]:
        """获取当前登录的管理员 ID"""
        session_id = request.cookies.get("session_id")
        if not session_id:
            return None
        return auth_manager.verify_session(session_id)
    
    # ==================== 页面路由 ====================
    
    @app.get("/login")
    async def login_page(request: Request):
        """登录页面"""
        if check_auth(request):
            return RedirectResponse(url="/", status_code=302)
        return templates.TemplateResponse("login.html", {"request": request})
    
    @app.get("/")
    async def index(request: Request):
        """首页"""
        if not check_auth(request):
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse("index.html", {"request": request})
    
    @app.get("/test")
    async def test_page(request: Request):
        """工具测试页面"""
        if not check_auth(request):
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse("test.html", {"request": request})
    
    @app.get("/admin")
    async def admin_page(request: Request):
        """管理页面"""
        if not check_auth(request):
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse("admin.html", {"request": request})
    
    @app.get("/logs")
    async def logs_page(request: Request):
        """日志页面"""
        if not check_auth(request):
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse("logs.html", {"request": request})
    
    # ==================== 认证 API ====================
    
    @app.post("/api/auth/login")
    async def login(data: LoginRequest, request: Request):
        """登录"""
        admin_id = auth_manager.verify_admin(data.username, data.password)
        
        if not admin_id:
            return JSONResponse({"success": False, "error": "用户名或密码错误"})
        
        session_id = auth_manager.create_session(admin_id)
        response = JSONResponse({"success": True, "message": "登录成功"})
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,
            samesite="lax"
        )
        return response
    
    @app.post("/api/auth/logout")
    async def logout(request: Request):
        """登出"""
        session_id = request.cookies.get("session_id")
        if session_id:
            auth_manager.delete_session(session_id)
        
        response = JSONResponse({"success": True, "message": "已登出"})
        response.delete_cookie("session_id")
        return response
    
    @app.post("/api/auth/change-password")
    async def change_password(data: ChangePasswordRequest, request: Request):
        """修改密码"""
        admin_id = get_admin_id(request)
        if not admin_id:
            return JSONResponse({"success": False, "error": "未登录"})
        
        if len(data.new_password) < 6:
            return JSONResponse({"success": False, "error": "密码长度至少 6 位"})
        
        success = auth_manager.change_password(admin_id, data.new_password)
        if success:
            return JSONResponse({"success": True, "message": "密码修改成功"})
        else:
            return JSONResponse({"success": False, "error": "修改失败"})
    
    # ==================== Token 管理 API ====================
    
    @app.get("/api/tokens")
    async def list_tokens(request: Request):
        """列出所有 Token"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        tokens = auth_manager.list_api_tokens()
        return JSONResponse({"success": True, "tokens": tokens})
    
    @app.post("/api/tokens")
    async def create_token(data: CreateTokenRequest, request: Request):
        """创建 Token"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        if not data.name:
            return JSONResponse({"success": False, "error": "请输入 Token 名称"})
        
        token = auth_manager.create_api_token(data.name)
        return JSONResponse({"success": True, "token": token})
    
    @app.delete("/api/tokens/{token_id}")
    async def delete_token(token_id: int, request: Request):
        """删除 Token"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        success = auth_manager.delete_api_token(token_id)
        if success:
            return JSONResponse({"success": True, "message": "Token 已删除"})
        else:
            return JSONResponse({"success": False, "error": "删除失败"})
    
    # ==================== 日志 API ====================
    
    @app.get("/api/logs")
    async def get_logs(
        request: Request,
        limit: int = 50,
        offset: int = 0,
        type: str = None,
        method: str = None,
        path: str = None
    ):
        """获取日志列表"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        logs = api_logger.get_logs(
            limit=limit,
            offset=offset,
            log_type=type,
            method=method,
            path_contains=path
        )
        stats = api_logger.get_stats()
        
        return JSONResponse({
            "success": True,
            "logs": logs,
            "stats": stats
        })
    
    @app.get("/api/logs/{log_id}")
    async def get_log_detail(log_id: int, request: Request):
        """获取日志详情"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        log = api_logger.get_log(log_id)
        if not log:
            return JSONResponse({"success": False, "error": "日志不存在"})
        
        return JSONResponse({"success": True, "log": log})
    
    @app.delete("/api/logs")
    async def clear_logs(request: Request):
        """清空日志"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        api_logger.clear_logs()
        return JSONResponse({"success": True, "message": "日志已清空"})
    
    # ==================== 工具调用 API（Web 测试用） ====================
    
    @app.post("/api/call")
    async def api_call(request: Request):
        """调用工具 API"""
        if not check_auth(request):
            return JSONResponse({"success": False, "error": "未登录"})
        
        try:
            data = await request.json()
            tool_name = data.get("tool")
            params = data.get("params", {})
            
            if tool_name not in TOOL_MAP:
                return JSONResponse({
                    "success": False,
                    "error": f"未知工具: {tool_name}"
                })
            
            result = TOOL_MAP[tool_name](params)
            
            return JSONResponse({
                "success": True,
                "result": result
            })
            
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    # ==================== MCP 路由 ====================
    
    async def handle_mcp(request: Request):
        """处理 MCP 请求"""
        # 从 header 获取 token
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            session_id = request.headers.get("mcp-session-id", "")
            client_id = session_id or (
                f"{request.client.host}:{request.client.port}" 
                if request.client else "default"
            )
            mcp_session_tokens[client_id] = token
            print(f"[MCP] 会话 {client_id[:20]}... 已认证")
        
        await session_manager.handle_request(
            request.scope, request.receive, request._send
        )
    
    app.add_api_route("/mcp", handle_mcp, methods=["GET", "POST", "DELETE"])
    
    # 启动服务
    print(f"\n{'='*50}")
    print(f"  {SERVER_NAME} 已启动")
    print(f"{'='*50}")
    print(f"  Web 界面: http://localhost:{SERVER_PORT}")
    print(f"  管理后台: http://localhost:{SERVER_PORT}/admin")
    print(f"  MCP 日志: http://localhost:{SERVER_PORT}/logs")
    print(f"  MCP 端点: http://localhost:{SERVER_PORT}/mcp")
    print(f"{'='*50}\n")
    
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    run_server()
