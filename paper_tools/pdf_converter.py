"""
PDF 转 Markdown 模块

使用 markitdown 库将 PDF 转换为 Markdown
如果 markitdown 失败，使用 pymupdf 作为备用方案

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import os
from typing import Optional


class PDFConverter:
    """PDF 转 Markdown 转换器"""
    
    def __init__(self):
        self._markitdown = None
        self._pymupdf_available = False
        
        # 尝试导入 markitdown
        try:
            from markitdown import MarkItDown
            self._markitdown = MarkItDown()
        except ImportError:
            print("[PDFConverter] markitdown 未安装")
        
        # 检查 pymupdf 是否可用（备用方案）
        try:
            import pymupdf
            self._pymupdf_available = True
        except ImportError:
            pass
    
    def convert(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        将 PDF 转换为 Markdown
        
        Args:
            pdf_path: PDF 文件路径
            output_path: 输出 Markdown 文件路径（可选）
        
        Returns:
            Markdown 内容
        
        Raises:
            FileNotFoundError: PDF 文件不存在
            Exception: 转换失败
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        # 检查文件大小
        file_size = os.path.getsize(pdf_path)
        if file_size < 1000:  # 小于 1KB，可能是损坏的文件
            raise Exception(f"PDF 文件可能损坏（大小仅 {file_size} 字节）")
        
        markdown_content = None
        error_msg = None
        
        # 方法 1: 尝试使用 markitdown
        if self._markitdown:
            try:
                result = self._markitdown.convert(pdf_path)
                markdown_content = result.text_content
                if markdown_content and len(markdown_content.strip()) > 100:
                    print(f"[PDFConverter] markitdown 转换成功")
            except Exception as e:
                error_msg = str(e)
                print(f"[PDFConverter] markitdown 转换失败: {e}")
        
        # 方法 2: 如果 markitdown 失败，尝试使用 pymupdf
        if not markdown_content and self._pymupdf_available:
            try:
                markdown_content = self._convert_with_pymupdf(pdf_path)
                if markdown_content:
                    print(f"[PDFConverter] pymupdf 转换成功")
            except Exception as e:
                print(f"[PDFConverter] pymupdf 转换失败: {e}")
        
        # 如果都失败了
        if not markdown_content or len(markdown_content.strip()) < 50:
            raise Exception(
                f"PDF 转换失败，可能是扫描版 PDF 或格式不支持。\n"
                f"原始错误: {error_msg or '无法提取文本内容'}"
            )
        
        # 如果指定了输出路径，保存文件
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        
        return markdown_content
    
    def _convert_with_pymupdf(self, pdf_path: str) -> str:
        """使用 pymupdf 提取 PDF 文本"""
        import pymupdf
        
        doc = pymupdf.open(pdf_path)
        text_parts = []
        
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            if text.strip():
                text_parts.append(f"## Page {page_num}\n\n{text}")
        
        doc.close()
        
        return "\n\n---\n\n".join(text_parts)
    
    def convert_to_file(self, pdf_path: str, output_path: str) -> bool:
        """
        将 PDF 转换为 Markdown 并保存到文件
        
        Args:
            pdf_path: PDF 文件路径
            output_path: 输出 Markdown 文件路径
        
        Returns:
            是否成功
        """
        try:
            self.convert(pdf_path, output_path)
            return True
        except Exception as e:
            print(f"[PDFConverter] 转换失败: {e}")
            return False
