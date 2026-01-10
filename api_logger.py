# -*- coding: utf-8 -*-
"""
API 请求日志模块
记录所有 API 和 MCP 请求，最多保留 1000 条

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class APILogger:
    """API 日志记录器"""
    
    def __init__(self, db_path: str = "data/api_logs.db", max_records: int = 1000):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.MAX_RECORDS = max_records
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    title TEXT,
                    request_headers TEXT,
                    request_body TEXT,
                    response_status INTEGER,
                    response_body TEXT,
                    duration_ms INTEGER,
                    client_ip TEXT,
                    user_agent TEXT,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_logs_timestamp 
                ON api_logs(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_logs_type 
                ON api_logs(type)
            """)
            conn.commit()
    
    def log(
        self,
        log_type: str,  # 'api' 或 'mcp'
        method: str,
        path: str,
        title: str = None,
        request_headers: Dict = None,
        request_body: Any = None,
        response_status: int = None,
        response_body: Any = None,
        duration_ms: int = None,
        client_ip: str = None,
        user_agent: str = None,
        error: str = None
    ):
        """记录 API 请求"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                headers_json = json.dumps(request_headers, ensure_ascii=False) if request_headers else None
                request_json = self._safe_json(request_body)
                response_json = self._safe_json(response_body)
                
                conn.execute("""
                    INSERT INTO api_logs (
                        timestamp, type, method, path, title,
                        request_headers, request_body, response_status, response_body,
                        duration_ms, client_ip, user_agent, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    log_type,
                    method,
                    path,
                    title,
                    headers_json,
                    request_json,
                    response_status,
                    response_json,
                    duration_ms,
                    client_ip,
                    user_agent,
                    error
                ))
                conn.commit()
                
                self._cleanup_old_records(conn)
                
        except Exception as e:
            logger.error(f"记录 API 日志失败: {e}")
    
    def _safe_json(self, data: Any) -> Optional[str]:
        """安全地序列化 JSON"""
        if data is None:
            return None
        try:
            if isinstance(data, str):
                try:
                    json.loads(data)
                    return data
                except:
                    return json.dumps(data, ensure_ascii=False)
            return json.dumps(data, ensure_ascii=False, default=str)
        except:
            return str(data)
    
    def _cleanup_old_records(self, conn: sqlite3.Connection):
        """清理超出限制的旧记录"""
        cursor = conn.execute("SELECT COUNT(*) FROM api_logs")
        count = cursor.fetchone()[0]
        
        if count > self.MAX_RECORDS:
            delete_count = count - self.MAX_RECORDS
            conn.execute("""
                DELETE FROM api_logs WHERE id IN (
                    SELECT id FROM api_logs ORDER BY id ASC LIMIT ?
                )
            """, (delete_count,))
            conn.commit()
            logger.info(f"清理了 {delete_count} 条旧的 API 日志")
    
    def get_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        log_type: str = None,
        method: str = None,
        path_contains: str = None
    ) -> List[Dict]:
        """获取日志列表"""
        query = "SELECT * FROM api_logs WHERE 1=1"
        params = []
        
        if log_type:
            query += " AND type = ?"
            params.append(log_type)
        
        if method:
            query += " AND method = ?"
            params.append(method.upper())
        
        if path_contains:
            query += " AND path LIKE ?"
            params.append(f"%{path_contains}%")
        
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log = dict(row)
                for field in ['request_headers', 'request_body', 'response_body']:
                    if log[field]:
                        try:
                            log[field] = json.loads(log[field])
                        except:
                            pass
                logs.append(log)
            
            return logs
    
    def get_log(self, log_id: int) -> Optional[Dict]:
        """获取单条日志详情"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM api_logs WHERE id = ?", (log_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            log = dict(row)
            for field in ['request_headers', 'request_body', 'response_body']:
                if log[field]:
                    try:
                        log[field] = json.loads(log[field])
                    except:
                        pass
            return log
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}
            
            cursor = conn.execute("SELECT COUNT(*) FROM api_logs")
            stats['total'] = cursor.fetchone()[0]
            
            cursor = conn.execute("""
                SELECT type, COUNT(*) as count 
                FROM api_logs 
                GROUP BY type
            """)
            stats['by_type'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor = conn.execute("""
                SELECT method, COUNT(*) as count 
                FROM api_logs 
                GROUP BY method
            """)
            stats['by_method'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor = conn.execute("""
                SELECT COUNT(*) FROM api_logs 
                WHERE response_status >= 400 OR error IS NOT NULL
            """)
            stats['errors'] = cursor.fetchone()[0]
            
            cursor = conn.execute("""
                SELECT COUNT(*) FROM api_logs 
                WHERE timestamp > datetime('now', '-1 day')
            """)
            stats['last_24h'] = cursor.fetchone()[0]
            
            return stats
    
    def clear_logs(self):
        """清空所有日志"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM api_logs")
            conn.commit()
        logger.info("已清空所有 API 日志")
