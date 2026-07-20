#!/usr/bin/env python3
"""
同步所有本地仓库到最新状态

使用方式:
  python sync_all.py
  python sync_all.py --api http://localhost:8000
  python sync_all.py --repos WeFi-HLB/ai-ocr WeFi-HLB/fps-tp
  python sync_all.py --timeout 7200
  python sync_all.py --no-wait

特点:
  - 利用现有的 API 和优化参数
  - 自动更新数据库 (synced_at, synced_at)
  - 实时显示同步进度
  - 完整的错误处理和报告
"""

import argparse
import requests
import time
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RepositorySyncer:
    """仓库同步客户端"""

    def __init__(self, api_base: str = "http://localhost:8000"):
        self.api_base = api_base.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 10

    def get_all_repos(self) -> List[Dict[str, Any]]:
        """获取所有仓库列表"""
        url = f"{self.api_base}/api/repos"
        logger.info(f"获取仓库列表: {url}")
        try:
            response = self.session.get(url)
            response.raise_for_status()
            repos = response.json()
            logger.info(f"✓ 获取到 {len(repos)} 个仓库")
            return repos
        except Exception as e:
            logger.error(f"❌ 获取仓库列表失败: {e}")
            sys.exit(1)

    def trigger_sync(self, repo_names: List[str] = None) -> Dict[str, Any]:
        """触发同步"""
        url = f"{self.api_base}/api/repos/sync"
        body = repo_names or []  # 空列表表示全量同步

        if body:
            logger.info(f"触发同步指定的 {len(body)} 个仓库")
        else:
            logger.info("触发全量同步")

        try:
            response = self.session.post(url, json=body)
            response.raise_for_status()
            result = response.json()
            queued = result.get('queued', [])
            logger.info(f"✓ 已队列 {len(queued)} 个仓库")
            return result
        except Exception as e:
            logger.error(f"❌ 触发同步失败: {e}")
            sys.exit(1)

    def get_sync_status(self) -> Dict[str, Dict[str, Any]]:
        """获取同步状态"""
        url = f"{self.api_base}/api/repos/sync/status"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"❌ 获取同步状态失败: {e}")
            return {}

    def print_progress(self, status: Dict, total: int):
        """打印同步进度（实时更新的进度条）"""
        done = sum(1 for s in status.values() if s['status'] in ['done', 'failed'])
        syncing = sum(1 for s in status.values() if s['status'] == 'syncing')
        queued = sum(1 for s in status.values() if s['status'] == 'queued')

        # 绘制进度条
        bar_width = 40
        filled = int(bar_width * done / total)
        bar = '█' * filled + '░' * (bar_width - filled)

        # 使用 \r 实现实时更新
        print(f"\r[{bar}] {done}/{total} "
              f"(完成: {done}, 同步中: {syncing}, 队列: {queued})",
              end='', flush=True)

    def wait_for_completion(self, timeout: int = 3600, poll_interval: int = 2):
        """等待所有同步任务完成"""
        start_time = time.time()

        # 获取初始状态确定总数
        status = self.get_sync_status()
        if not status:
            logger.error("❌ 无同步任务")
            return False

        total = len(status)
        logger.info(f"\n📊 开始同步 {total} 个仓库...")
        logger.info(f"⏱️  超时设置: {timeout} 秒 ({timeout//3600}h {(timeout%3600)//60}m)")
        print()

        while True:
            elapsed = time.time() - start_time

            # 检查超时
            if elapsed > timeout:
                logger.warning(f"\n⏰ 超时！已等待 {int(elapsed)} 秒")
                self.print_failed_repos(status)
                return False

            # 获取状态
            status = self.get_sync_status()
            if not status:
                break

            # 显示进度
            self.print_progress(status, total)

            # 检查是否完成
            all_done = all(s['status'] in ['done', 'failed'] for s in status.values())
            if all_done:
                print()  # 换行
                break

            time.sleep(poll_interval)

        return self.print_summary(status)

    def print_failed_repos(self, status: Dict):
        """打印失败的仓库"""
        failed = {name: s for name, s in status.items() if s['status'] == 'failed'}
        if failed:
            print("\n❌ 失败的仓库:")
            for name, s in failed.items():
                error = s.get('error', 'Unknown error')
                # 只显示前 100 个字符的错误
                error_short = error[:100] + ('...' if len(error) > 100 else '')
                print(f"  • {name}")
                print(f"    └─ {error_short}")

    def print_summary(self, status: Dict) -> bool:
        """打印总结"""
        done = sum(1 for s in status.values() if s['status'] == 'done')
        failed = sum(1 for s in status.values() if s['status'] == 'failed')
        total = len(status)
        success_rate = (done / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("📈 同步完成")
        print("="*70)
        print(f"总数:        {total:>3} 个仓库")
        print(f"成功:        {done:>3} ✓")
        print(f"失败:        {failed:>3} ✗")
        print(f"成功率:      {success_rate:>6.1f}%")
        print("="*70)

        self.print_failed_repos(status)

        return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description='同步所有本地仓库到最新状态',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python sync_all.py                                    # 全量同步
  python sync_all.py --repos WeFi-HLB/ai-ocr           # 同步指定仓库
  python sync_all.py --api http://192.168.1.100:8000   # 连接远程 API
  python sync_all.py --timeout 7200                    # 2 小时超时
  python sync_all.py --no-wait                         # 触发后不等待
        '''
    )

    parser.add_argument(
        '--api',
        default='http://localhost:8000',
        help='API 服务器地址 (默认: http://localhost:8000)'
    )
    parser.add_argument(
        '--repos',
        nargs='+',
        help='仅同步指定的仓库 (格式: org/repo) (默认: 全量同步)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=3600,
        help='同步超时时间（秒，默认: 3600=1小时）'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=2,
        help='轮询间隔（秒，默认: 2）'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        help='触发同步后不等待完成'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # 创建同步客户端
    syncer = RepositorySyncer(args.api)

    print()
    logger.info(f"🔗 连接到: {args.api}")

    # 获取仓库列表
    repos = syncer.get_all_repos()

    # 触发同步
    if args.repos:
        result = syncer.trigger_sync(args.repos)
    else:
        result = syncer.trigger_sync()

    if args.no_wait:
        logger.info("⏭️  不等待，直接返回")
        return True

    # 等待完成
    success = syncer.wait_for_completion(
        timeout=args.timeout,
        poll_interval=args.poll_interval
    )

    print()
    return success


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ 未捕获的异常: {e}", exc_info=True)
        sys.exit(1)
