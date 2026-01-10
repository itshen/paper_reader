"""
数据模型定义

时间查询和基础计算 MCP 服务
（本服务不需要复杂的数据模型，保留此文件供扩展使用）

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
MIT License
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TimeInfo:
    """时间信息"""
    datetime: datetime
    timezone: str
    offset: float  # UTC 偏移（小时）
    weekday: int   # 0-6
    timestamp: int


@dataclass
class CalculationResult:
    """计算结果"""
    expression: str
    result: float
    formatted: str
