#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent管理命令行工具
用户可以通过命令行注册、管理A2A Agent
"""

import asyncio
import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.agent_registry import get_agent_registry

async def add_agent(url: str, agent_id: str = None):
    """添加Agent"""
    registry = get_agent_registry()
    
    print(f"🔄 正在添加Agent: {url}")
    success = await registry.add_agent_by_card_url(url, agent_id)
    
    if success:
        print(f"✅ 成功添加Agent!")
        # 显示Agent信息
        if agent_id:
            agent_info = await registry.get_agent_by_id(agent_id)
        else:
            # 如果没有指定ID，获取最新添加的Agent
            all_agents = await registry.get_all_agents()
            agent_info = list(all_agents.values())[-1] if all_agents else None
        
        if agent_info:
            print(f"   名称: {agent_info.get('name')}")
            print(f"   ID: {agent_info.get('agent_id')}")
            print(f"   URL: {agent_info.get('url')}")
            print(f"   能力: {agent_info.get('capabilities', [])}")
    else:
        print(f"❌ 添加Agent失败")

async def list_agents():
    """列出所有Agent"""
    registry = get_agent_registry()
    
    print("📋 已注册的Agent:")
    all_agents = await registry.get_all_agents()
    
    if not all_agents:
        print("   (无已注册的Agent)")
        return
    
    for agent_id, agent_info in all_agents.items():
        status = "✅ 启用" if agent_info.get('enabled', True) else "❌ 禁用"
        name = agent_info.get('name', 'Unknown')
        url = agent_info.get('url', agent_info.get('agent_card_url', 'N/A'))
        
        print(f"   [{agent_id}] {name} - {status}")
        print(f"      URL: {url}")
        
        if 'capabilities' in agent_info:
            capabilities = agent_info.get('capabilities', [])
            print(f"      能力: {capabilities}")
        print()

async def remove_agent(agent_id: str):
    """移除Agent"""
    registry = get_agent_registry()
    
    print(f"🗑️  正在移除Agent: {agent_id}")
    success = registry.remove_agent(agent_id)
    
    if success:
        print(f"✅ 成功移除Agent: {agent_id}")
    else:
        print(f"❌ 移除失败，Agent {agent_id} 不存在")

async def enable_agent(agent_id: str):
    """启用Agent"""
    registry = get_agent_registry()
    
    success = registry.enable_agent(agent_id)
    print(f"{'✅ 已启用' if success else '❌ 启用失败'} Agent: {agent_id}")

async def disable_agent(agent_id: str):
    """禁用Agent"""
    registry = get_agent_registry()
    
    success = registry.disable_agent(agent_id)
    print(f"{'✅ 已禁用' if success else '❌ 禁用失败'} Agent: {agent_id}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='A2A Agent管理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 添加Agent
    add_parser = subparsers.add_parser('add', help='添加新的Agent')
    add_parser.add_argument('url', help='Agent Card URL')
    add_parser.add_argument('--id', help='指定Agent ID (可选)')
    
    # 列出Agent
    subparsers.add_parser('list', help='列出所有Agent')
    
    # 移除Agent
    remove_parser = subparsers.add_parser('remove', help='移除Agent')
    remove_parser.add_argument('agent_id', help='要移除的Agent ID')
    
    # 启用Agent
    enable_parser = subparsers.add_parser('enable', help='启用Agent')
    enable_parser.add_argument('agent_id', help='要启用的Agent ID')
    
    # 禁用Agent
    disable_parser = subparsers.add_parser('disable', help='禁用Agent')
    disable_parser.add_argument('agent_id', help='要禁用的Agent ID')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'add':
            await add_agent(args.url, args.id)
        elif args.command == 'list':
            await list_agents()
        elif args.command == 'remove':
            await remove_agent(args.agent_id)
        elif args.command == 'enable':
            await enable_agent(args.agent_id)
        elif args.command == 'disable':
            await disable_agent(args.agent_id)
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
