"""
认证和授权模块

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

import os
import secrets
import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict


class AuthManager:
    """认证管理器"""
    
    def __init__(self, db_path: str, config: dict):
        self.db_path = db_path
        self.config = config
        
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self._init_auth_tables()
        self._ensure_default_admin()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_auth_tables(self):
        """初始化认证相关表"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # 管理员账号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT,
                    last_login TEXT
                )
            """)
            
            # API Token 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at TEXT,
                    last_used TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # 会话表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    admin_id INTEGER NOT NULL,
                    created_at TEXT,
                    expires_at TEXT,
                    FOREIGN KEY (admin_id) REFERENCES admins(id)
                )
            """)
            
            conn.commit()
        finally:
            conn.close()
    
    def _ensure_default_admin(self):
        """确保存在默认管理员"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admins")
            count = cursor.fetchone()[0]
            
            if count == 0:
                # 从配置读取默认密码，如果没有则生成随机密码
                default_password = self.config.get("auth", {}).get("default_password", "")
                if not default_password:
                    default_password = secrets.token_urlsafe(12)
                    print(f"\n🔐 已创建默认管理员账号:")
                    print(f"   用户名: admin")
                    print(f"   密码: {default_password}")
                    print(f"   请登录后立即修改密码!\n")
                
                password_hash = self._hash_password(default_password)
                cursor.execute("""
                    INSERT INTO admins (username, password_hash, created_at)
                    VALUES (?, ?, ?)
                """, ("admin", password_hash, datetime.now().isoformat()))
                conn.commit()
        finally:
            conn.close()
    
    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        salt = self.config.get("auth", {}).get("salt", "mcp_template_salt")
        return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    
    # ==================== 管理员认证 ====================
    
    def verify_admin(self, username: str, password: str) -> Optional[int]:
        """验证管理员登录"""
        password_hash = self._hash_password(password)
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM admins 
                WHERE username = ? AND password_hash = ?
            """, (username, password_hash))
            row = cursor.fetchone()
            
            if row:
                # 更新最后登录时间
                cursor.execute("""
                    UPDATE admins SET last_login = ? WHERE id = ?
                """, (datetime.now().isoformat(), row[0]))
                conn.commit()
                return row[0]
            
            return None
        finally:
            conn.close()
    
    def create_session(self, admin_id: int, expires_hours: int = 24) -> str:
        """创建会话"""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=expires_hours)
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (session_id, admin_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (session_id, admin_id, datetime.now().isoformat(), expires_at.isoformat()))
            conn.commit()
        finally:
            conn.close()
        
        return session_id
    
    def verify_session(self, session_id: str) -> Optional[int]:
        """验证会话"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT admin_id, expires_at FROM sessions 
                WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            
            if row:
                expires_at = datetime.fromisoformat(row[1])
                if expires_at > datetime.now():
                    return row[0]
                else:
                    # 过期，删除会话
                    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                    conn.commit()
            
            return None
        finally:
            conn.close()
    
    def delete_session(self, session_id: str):
        """删除会话（登出）"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()
    
    def change_password(self, admin_id: int, new_password: str) -> bool:
        """修改密码"""
        password_hash = self._hash_password(new_password)
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE admins SET password_hash = ? WHERE id = ?
            """, (password_hash, admin_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    # ==================== API Token 管理 ====================
    
    def create_api_token(self, name: str) -> str:
        """创建 API Token"""
        token = f"mcp_{secrets.token_urlsafe(32)}"
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_tokens (name, token, created_at, is_active)
                VALUES (?, ?, ?, 1)
            """, (name, token, datetime.now().isoformat()))
            conn.commit()
        finally:
            conn.close()
        
        return token
    
    def verify_api_token(self, token: str) -> bool:
        """验证 API Token"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM api_tokens 
                WHERE token = ? AND is_active = 1
            """, (token,))
            row = cursor.fetchone()
            
            if row:
                # 更新最后使用时间
                cursor.execute("""
                    UPDATE api_tokens SET last_used = ? WHERE id = ?
                """, (datetime.now().isoformat(), row[0]))
                conn.commit()
                return True
            
            return False
        finally:
            conn.close()
    
    def list_api_tokens(self) -> List[Dict]:
        """列出所有 API Token"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, token, created_at, last_used, is_active 
                FROM api_tokens ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            
            return [{
                "id": row[0],
                "name": row[1],
                "token": row[2][:12] + "..." if row[2] else "",
                "token_full": row[2],
                "created_at": row[3],
                "last_used": row[4],
                "is_active": bool(row[5])
            } for row in rows]
        finally:
            conn.close()
    
    def revoke_api_token(self, token_id: int) -> bool:
        """撤销 API Token"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_tokens SET is_active = 0 WHERE id = ?
            """, (token_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def delete_api_token(self, token_id: int) -> bool:
        """删除 API Token"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_tokens WHERE id = ?", (token_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
