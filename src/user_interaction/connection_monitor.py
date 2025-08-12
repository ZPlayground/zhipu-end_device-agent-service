#!/usr/bin/env python3
"""
WebSocket连接状态监控面板
WebSocket Connection Status Monitor

提供实时连接状态监控和统计信息显示，包括：
1. 连接状态实时更新
2. 重连尝试监控
3. 数据传输统计
4. 连接健康度分析
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import threading
import sys
import os

# 尝试导入第三方库，如果没有则使用基础功能
try:
    import rich
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.progress import Progress, BarColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("⚠️ Rich库未安装，将使用基础文本显示")

from src.user_interaction.websocket_reconnector import WebSocketReconnector, ConnectionState

logger = logging.getLogger(__name__)


class ConnectionMonitor:
    """连接状态监控器"""
    
    def __init__(self):
        self.monitors: Dict[str, Dict[str, Any]] = {}
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.update_interval = 2.0  # 2秒更新一次
        
        if RICH_AVAILABLE:
            self.console = Console()
        
        logger.info("🖥️ 连接状态监控器初始化完成")
    
    def add_connection(self, name: str, reconnector: WebSocketReconnector):
        """添加连接到监控列表"""
        self.monitors[name] = {
            "reconnector": reconnector,
            "start_time": datetime.now(),
            "last_update": datetime.now(),
            "connection_history": [],
            "error_history": [],
            "performance_metrics": {
                "avg_response_time": 0.0,
                "data_throughput": 0.0,
                "error_rate": 0.0
            }
        }
        logger.info(f"📊 添加连接监控: {name}")
    
    def remove_connection(self, name: str):
        """从监控列表移除连接"""
        if name in self.monitors:
            del self.monitors[name]
            logger.info(f"🗑️ 移除连接监控: {name}")
    
    async def start_monitoring(self):
        """启动监控"""
        if self.is_monitoring:
            logger.warning("⚠️ 监控已在运行")
            return
        
        self.is_monitoring = True
        logger.info("🚀 启动连接状态监控")
        
        if RICH_AVAILABLE:
            await self._start_rich_monitoring()
        else:
            await self._start_basic_monitoring()
    
    async def stop_monitoring(self):
        """停止监控"""
        if self.is_monitoring:
            self.is_monitoring = False
            if self.monitor_task:
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
            logger.info("🛑 连接监控已停止")
    
    async def _start_rich_monitoring(self):
        """启动Rich界面监控"""
        with Live(self._create_rich_layout(), refresh_per_second=0.5, screen=True) as live:
            while self.is_monitoring:
                try:
                    # 更新监控数据
                    self._update_monitoring_data()
                    
                    # 更新显示
                    live.update(self._create_rich_layout())
                    
                    await asyncio.sleep(self.update_interval)
                except Exception as e:
                    logger.error(f"❌ 监控更新异常: {e}")
                    await asyncio.sleep(1)
    
    async def _start_basic_monitoring(self):
        """启动基础文本监控"""
        while self.is_monitoring:
            try:
                self._update_monitoring_data()
                self._print_basic_status()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"❌ 监控更新异常: {e}")
                await asyncio.sleep(1)
    
    def _update_monitoring_data(self):
        """更新监控数据"""
        current_time = datetime.now()
        
        for name, monitor_data in self.monitors.items():
            reconnector = monitor_data["reconnector"]
            
            # 获取连接统计
            stats = reconnector.get_connection_stats()
            
            # 更新连接历史
            connection_event = {
                "timestamp": current_time,
                "state": stats["current_state"],
                "is_connected": reconnector.is_connected(),
                "is_healthy": reconnector.is_healthy(),
                "retry_count": stats["retry_count"]
            }
            
            monitor_data["connection_history"].append(connection_event)
            
            # 保持历史记录数量
            if len(monitor_data["connection_history"]) > 100:
                monitor_data["connection_history"] = monitor_data["connection_history"][-100:]
            
            # 计算性能指标
            self._calculate_performance_metrics(monitor_data, stats)
            
            monitor_data["last_update"] = current_time
    
    def _calculate_performance_metrics(self, monitor_data: Dict, stats: Dict):
        """计算性能指标"""
        history = monitor_data["connection_history"]
        
        if len(history) < 2:
            return
        
        # 计算连接稳定性
        recent_history = history[-20:]  # 最近20个记录
        connected_count = sum(1 for h in recent_history if h["is_connected"])
        connection_stability = connected_count / len(recent_history) if recent_history else 0
        
        # 计算数据吞吐量
        if stats["total_uptime_seconds"] > 0:
            throughput = (stats["bytes_sent"] + stats["bytes_received"]) / stats["total_uptime_seconds"]
        else:
            throughput = 0
        
        # 计算错误率
        if stats["total_connections"] > 0:
            error_rate = stats["failed_connections"] / stats["total_connections"]
        else:
            error_rate = 0
        
        monitor_data["performance_metrics"].update({
            "connection_stability": connection_stability,
            "data_throughput": throughput,
            "error_rate": error_rate,
            "success_rate": stats["success_rate"]
        })
    
    def _create_rich_layout(self) -> Layout:
        """创建Rich显示布局"""
        layout = Layout()
        
        # 创建主要区域
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        # 分割主区域
        layout["main"].split_row(
            Layout(name="connections"),
            Layout(name="details")
        )
        
        # 头部
        layout["header"].update(Panel(
            Text("🔗 WebSocket连接监控面板", style="bold blue"),
            title="Connection Monitor"
        ))
        
        # 连接列表
        layout["connections"].update(self._create_connections_table())
        
        # 详细信息
        layout["details"].update(self._create_details_panel())
        
        # 底部
        layout["footer"].update(Panel(
            Text(f"🕐 最后更新: {datetime.now().strftime('%H:%M:%S')} | 监控中: {len(self.monitors)} 个连接", style="dim"),
            title="Status"
        ))
        
        return layout
    
    def _create_connections_table(self) -> Table:
        """创建连接状态表格"""
        table = Table(title="📊 连接状态")
        table.add_column("连接名称", style="cyan")
        table.add_column("状态", style="green")
        table.add_column("健康度", style="yellow")
        table.add_column("重连次数", style="red")
        table.add_column("运行时间", style="blue")
        table.add_column("成功率", style="magenta")
        
        for name, monitor_data in self.monitors.items():
            reconnector = monitor_data["reconnector"]
            stats = reconnector.get_connection_stats()
            
            # 状态显示
            state = stats["current_state"]
            state_color = {
                "connected": "green",
                "connecting": "yellow",
                "reconnecting": "orange",
                "disconnected": "red",
                "failed": "red",
                "stopped": "gray"
            }.get(state, "white")
            
            # 健康度
            health = "🟢 健康" if reconnector.is_healthy() else "🔴 异常"
            
            # 运行时间
            uptime_seconds = stats.get("current_uptime_seconds", 0)
            uptime = self._format_duration(uptime_seconds)
            
            # 成功率
            success_rate = f"{stats['success_rate']:.1f}%"
            
            table.add_row(
                name,
                f"[{state_color}]{state}[/{state_color}]",
                health,
                str(stats["total_reconnections"]),
                uptime,
                success_rate
            )
        
        return table
    
    def _create_details_panel(self) -> Panel:
        """创建详细信息面板"""
        if not self.monitors:
            return Panel("暂无连接", title="📋 详细信息")
        
        # 选择第一个连接显示详细信息
        name, monitor_data = next(iter(self.monitors.items()))
        reconnector = monitor_data["reconnector"]
        stats = reconnector.get_connection_stats()
        metrics = monitor_data["performance_metrics"]
        
        details_text = f"""
🔗 连接: {name}
📍 状态: {stats['current_state']}
⏱️ 重试计数: {stats['retry_count']}/{stats['max_retries']}
📊 总连接数: {stats['total_connections']}
✅ 成功连接: {stats['successful_connections']}
❌ 失败连接: {stats['failed_connections']}
🔄 重连次数: {stats['total_reconnections']}
⏰ 当前连接时长: {self._format_duration(stats.get('current_uptime_seconds', 0))}
📈 总运行时长: {self._format_duration(stats.get('total_uptime_seconds', 0))}

📡 数据传输:
  📤 发送: {stats['data_sent_count']} 条 ({self._format_bytes(stats['bytes_sent'])})
  📥 接收: {stats['data_received_count']} 条 ({self._format_bytes(stats['bytes_received'])})
  📊 吞吐量: {self._format_bytes(metrics.get('data_throughput', 0))}/s

🏥 健康指标:
  🎯 连接稳定性: {metrics.get('connection_stability', 0):.1%}
  📉 错误率: {metrics.get('error_rate', 0):.1%}
  🔋 成功率: {stats['success_rate']:.1f}%
        """
        
        return Panel(details_text.strip(), title="📋 详细信息")
    
    def _print_basic_status(self):
        """打印基础状态信息"""
        os.system('cls' if os.name == 'nt' else 'clear')  # 清屏
        
        print("=" * 80)
        print("🔗 WebSocket连接监控面板")
        print("=" * 80)
        print(f"🕐 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 监控连接: {len(self.monitors)} 个")
        print()
        
        for name, monitor_data in self.monitors.items():
            reconnector = monitor_data["reconnector"]
            stats = reconnector.get_connection_stats()
            
            print(f"📡 连接: {name}")
            print(f"   状态: {stats['current_state']}")
            print(f"   健康: {'🟢 健康' if reconnector.is_healthy() else '🔴 异常'}")
            print(f"   重连: {stats['total_reconnections']} 次")
            print(f"   成功率: {stats['success_rate']:.1f}%")
            print(f"   运行时长: {self._format_duration(stats.get('current_uptime_seconds', 0))}")
            print()
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时间长度"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"
    
    def _format_bytes(self, bytes_count: int) -> str:
        """格式化字节数"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024:
                return f"{bytes_count:.1f}{unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f}TB"
    
    def get_summary_report(self) -> Dict[str, Any]:
        """获取监控摘要报告"""
        total_connections = len(self.monitors)
        if total_connections == 0:
            return {"total_connections": 0, "summary": "无连接"}
        
        # 统计所有连接
        total_stats = {
            "total_connections": total_connections,
            "healthy_connections": 0,
            "connected_count": 0,
            "total_reconnections": 0,
            "total_data_sent": 0,
            "total_data_received": 0,
            "avg_success_rate": 0.0,
            "avg_uptime": 0.0
        }
        
        for name, monitor_data in self.monitors.items():
            reconnector = monitor_data["reconnector"]
            stats = reconnector.get_connection_stats()
            
            if reconnector.is_healthy():
                total_stats["healthy_connections"] += 1
            if reconnector.is_connected():
                total_stats["connected_count"] += 1
            
            total_stats["total_reconnections"] += stats["total_reconnections"]
            total_stats["total_data_sent"] += stats["bytes_sent"]
            total_stats["total_data_received"] += stats["bytes_received"]
            total_stats["avg_success_rate"] += stats["success_rate"]
            total_stats["avg_uptime"] += stats.get("total_uptime_seconds", 0)
        
        # 计算平均值
        total_stats["avg_success_rate"] /= total_connections
        total_stats["avg_uptime"] /= total_connections
        
        return total_stats


async def demo_connection_monitor():
    """演示连接监控功能"""
    monitor = ConnectionMonitor()
    
    # 创建测试连接
    test_urls = [
        "ws://localhost:8000/api/terminal-devices/ws/test_device_1",
        "ws://localhost:8000/api/terminal-devices/ws/test_device_2"
    ]
    
    reconnectors = []
    
    try:
        logger.info("🚀 启动连接监控演示")
        
        # 创建测试连接
        for i, url in enumerate(test_urls):
            reconnector = WebSocketReconnector(
                url=url,
                max_retries=5,
                initial_retry_delay=1.0,
                max_retry_delay=30.0
            )
            
            monitor.add_connection(f"测试设备_{i+1}", reconnector)
            reconnectors.append(reconnector)
        
        # 启动监控
        monitor_task = asyncio.create_task(monitor.start_monitoring())
        
        # 模拟连接尝试
        for i, reconnector in enumerate(reconnectors):
            asyncio.create_task(reconnector.connect())
            await asyncio.sleep(1)  # 错开连接时间
        
        # 运行监控
        logger.info("🖥️ 监控面板运行中... (按 Ctrl+C 退出)")
        await asyncio.sleep(60)  # 运行1分钟
        
    except KeyboardInterrupt:
        logger.info("🛑 收到退出信号")
    finally:
        # 清理资源
        logger.info("🧹 清理监控资源...")
        await monitor.stop_monitoring()
        
        for reconnector in reconnectors:
            await reconnector.disconnect()
        
        logger.info("✅ 监控演示结束")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_connection_monitor())
