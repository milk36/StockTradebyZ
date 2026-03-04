"""
Z哥B1战法回测脚本
基于zgnb_zk_results.log文件进行T+1买入、T+2卖出的回测验证

使用方式:
    python backtest_zgnb.py --data-dir ./data
    python backtest_zgnb.py --data-dir ./data --log-file zgnb_zk_results.log
    python backtest_zgnb.py --data-dir ./data --output-dir ./my_results
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ==================== 日志配置 ====================
# 设置UTF-8编码输出
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("backtest_zgnb.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ==================== 数据类定义 ====================

@dataclass
class BacktestResult:
    """单次回测结果"""
    code: str
    select_date: pd.Timestamp
    buy_date: Optional[pd.Timestamp]
    sell_date: Optional[pd.Timestamp]
    buy_price: Optional[float]
    sell_price: Optional[float]
    return_pct: Optional[float]
    status: str  # success/no_data/no_t1/no_t2


# ==================== 日志解析函数 ====================

def get_available_dates(log_file: Path) -> List[pd.Timestamp]:
    """
    获取日志文件中所有可用的选股日期

    Parameters
    ----------
    log_file : Path
        日志文件路径

    Returns
    -------
    List[pd.Timestamp]
        所有可用的选股日期列表（按出现顺序）
    """
    if not log_file.exists():
        raise FileNotFoundError(f"日志文件不存在: {log_file}")

    dates = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('交易日:'):
                date_str = line.split(':', 1)[1].strip()
                dates.append(pd.to_datetime(date_str))

    return dates


def parse_log_file(log_file: Path, target_date: Optional[pd.Timestamp] = None) -> Tuple[pd.Timestamp, List[str]]:
    """
    解析 zgnb_zk_results.log 文件

    Parameters
    ----------
    log_file : Path
        日志文件路径
    target_date : Optional[pd.Timestamp]
        目标选股日期，None 表示使用最后一个日期

    Returns
    -------
    Tuple[pd.Timestamp, List[str]]
        (选股日期, 股票代码列表)

    Raises
    ------
    FileNotFoundError
        日志文件不存在
    ValueError
        无法解析选股日期或目标日期不存在
    """
    if not log_file.exists():
        raise FileNotFoundError(f"日志文件不存在: {log_file}")

    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析所有选股结果块
    blocks = []
    current_block = []
    in_result = False

    for line in content.split('\n'):
        if line.startswith('========================================') and not in_result:
            in_result = True
            current_block = []
        elif in_result:
            current_block.append(line)
            # 遇到下一个分隔符表示块结束
            if line.startswith('========================================') and len(current_block) > 1:
                blocks.append(current_block[:-1])  # 去掉最后的分隔线
                current_block = []

    # 如果没有找到标准格式，尝试解析整个文件
    if not blocks:
        blocks = [content.split('\n')]

    # 找到目标日期的块
    target_block = None
    selected_date = None

    if target_date is None:
        # 使用最后一个块
        if blocks:
            target_block = blocks[-1]
    else:
        # 查找匹配的日期
        target_date_str = target_date.strftime('%Y-%m-%d')
        for block in blocks:
            for line in block:
                if line.startswith('交易日:'):
                    date_str = line.split(':', 1)[1].strip()
                    if date_str == target_date_str:
                        target_block = block
                        selected_date = target_date
                        break
            if target_block is not None:
                break

    if target_block is None:
        available_dates = get_available_dates(log_file)
        date_list = ', '.join([d.strftime('%Y-%m-%d') for d in available_dates])
        raise ValueError(
            f"无法找到目标日期: {target_date.strftime('%Y-%m-%d') if target_date else 'None'}\n"
            f"日志文件中可用的日期: {date_list}"
        )

    # 从目标块中提取信息
    # 提取选股日期
    for line in target_block:
        if line.startswith('交易日:'):
            if selected_date is None:
                date_str = line.split(':', 1)[1].strip()
                selected_date = pd.to_datetime(date_str)
            break

    # 提取股票代码
    stocks = []
    in_stock_section = False
    for line in target_block:
        if '符合条件的股票:' in line:
            in_stock_section = True
            continue
        if in_stock_section:
            if line.startswith('==='):
                break
            if line.strip():
                stocks.extend([s.strip() for s in line.split(',') if s.strip()])

    return selected_date, stocks


# ==================== 回测引擎 ====================

class BacktestEngine:
    """回测引擎"""

    def __init__(self, data_dir: Path, log_file: Path, target_date: Optional[pd.Timestamp] = None):
        """
        初始化回测引擎

        Parameters
        ----------
        data_dir : Path
            K线数据目录
        log_file : Path
            选股结果日志文件
        target_date : Optional[pd.Timestamp]
            目标选股日期，None 表示使用日志中最后一个日期
        """
        self.data_dir = Path(data_dir)
        self.log_file = Path(log_file)
        self.target_date = target_date
        self.results: List[BacktestResult] = []

    def parse_log_file(self) -> Tuple[pd.Timestamp, List[str]]:
        """解析日志文件，返回选股日期和股票代码列表"""
        return parse_log_file(self.log_file, self.target_date)

    def run_backtest(self) -> List[BacktestResult]:
        """
        执行回测

        Returns
        -------
        List[BacktestResult]
            回测结果列表
        """
        select_date, stocks = self.parse_log_file()

        logger.info(f"选股日期: {select_date.strftime('%Y-%m-%d')}")
        logger.info(f"开始回测 {len(stocks)} 只股票...")

        self.results = []
        for code in stocks:
            result = self.backtest_single_stock(code, select_date)
            self.results.append(result)

        return self.results

    def backtest_single_stock(self, code: str, select_date: pd.Timestamp) -> BacktestResult:
        """
        对单只股票进行回测

        回测逻辑:
        - T: 选股日期
        - T+1: 开盘价买入
        - T+2: 收盘价卖出

        Parameters
        ----------
        code : str
            股票代码
        select_date : pd.Timestamp
            选股日期

        Returns
        -------
        BacktestResult
            回测结果
        """
        csv_path = self.data_dir / f"{code}.csv"

        # 检查数据文件是否存在
        if not csv_path.exists():
            return BacktestResult(
                code=code,
                select_date=select_date,
                buy_date=None,
                sell_date=None,
                buy_price=None,
                sell_price=None,
                return_pct=None,
                status='no_data'
            )

        # 读取K线数据
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            logger.warning(f"读取 {code} 数据失败: {e}")
            return BacktestResult(
                code=code,
                select_date=select_date,
                buy_date=None,
                sell_date=None,
                buy_price=None,
                sell_price=None,
                return_pct=None,
                status='no_data'
            )

        # 确保数据格式正确
        if 'date' not in df.columns:
            return BacktestResult(
                code=code,
                select_date=select_date,
                buy_date=None,
                sell_date=None,
                buy_price=None,
                sell_price=None,
                return_pct=None,
                status='no_data'
            )

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        # 找到选股日期位置
        select_idx = df[df['date'] == select_date].index
        if len(select_idx) == 0:
            return BacktestResult(
                code=code,
                select_date=select_date,
                buy_date=None,
                sell_date=None,
                buy_price=None,
                sell_price=None,
                return_pct=None,
                status='no_data'
            )

        select_pos = select_idx[0]

        # 检查T+1是否存在
        if select_pos + 1 >= len(df):
            return BacktestResult(
                code=code,
                select_date=select_date,
                buy_date=None,
                sell_date=None,
                buy_price=None,
                sell_price=None,
                return_pct=None,
                status='no_t1'
            )

        # 检查T+2是否存在
        if select_pos + 2 >= len(df):
            return BacktestResult(
                code=code,
                select_date=select_date,
                buy_date=None,
                sell_date=None,
                buy_price=None,
                sell_price=None,
                return_pct=None,
                status='no_t2'
            )

        # T+1开盘买入
        buy_row = df.iloc[select_pos + 1]
        buy_date = buy_row['date']
        buy_price = float(buy_row['open'])

        # T+2收盘卖出
        sell_row = df.iloc[select_pos + 2]
        sell_date = sell_row['date']
        sell_price = float(sell_row['close'])

        # 计算收益率
        return_pct = (sell_price - buy_price) / buy_price * 100

        return BacktestResult(
            code=code,
            select_date=select_date,
            buy_date=buy_date,
            sell_date=sell_date,
            buy_price=buy_price,
            sell_price=sell_price,
            return_pct=return_pct,
            status='success'
        )

    def generate_summary_stats(self) -> Dict:
        """
        生成汇总统计信息

        Returns
        -------
        Dict
            统计信息字典
        """
        # 筛选成功执行的交易
        success_results = [r for r in self.results if r.status == 'success']

        if not success_results:
            return {
                'total': len(self.results),
                'success': 0,
                'avg_return': None,
                'median_return': None,
                'max_return': None,
                'min_return': None,
                'win_rate': None,
                'profit_count': 0,
                'loss_count': 0
            }

        returns = [r.return_pct for r in success_results]
        profit_results = [r for r in success_results if r.return_pct > 0]
        loss_results = [r for r in success_results if r.return_pct <= 0]

        return {
            'total': len(self.results),
            'success': len(success_results),
            'no_data': len([r for r in self.results if r.status == 'no_data']),
            'no_t1': len([r for r in self.results if r.status == 'no_t1']),
            'no_t2': len([r for r in self.results if r.status == 'no_t2']),
            'avg_return': np.mean(returns),
            'median_return': np.median(returns),
            'max_return': np.max(returns),
            'min_return': np.min(returns),
            'win_rate': len(profit_results) / len(success_results) * 100,
            'profit_count': len(profit_results),
            'loss_count': len(loss_results)
        }

    def save_results_to_csv(self, output_dir: Path) -> Path:
        """
        保存回测结果到CSV文件

        Parameters
        ----------
        output_dir : Path
            输出目录

        Returns
        -------
        Path
            保存的CSV文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 准备数据
        data = []
        for r in self.results:
            data.append({
                'code': r.code,
                'select_date': r.select_date.strftime('%Y-%m-%d') if r.select_date else None,
                'buy_date': r.buy_date.strftime('%Y-%m-%d') if r.buy_date else None,
                'sell_date': r.sell_date.strftime('%Y-%m-%d') if r.sell_date else None,
                'buy_price': r.buy_price,
                'sell_price': r.sell_price,
                'return_pct': r.return_pct,
                'status': r.status
            })

        df = pd.DataFrame(data)

        # 生成文件名
        select_date, _ = self.parse_log_file()
        filename = f"backtest_detail_{select_date.strftime('%Y%m%d')}.csv"
        output_path = output_dir / filename

        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"回测明细已保存至: {output_path}")

        return output_path

    def save_results_to_log(self, output_dir: Path) -> Path:
        """
        保存回测结果到日志文件

        Parameters
        ----------
        output_dir : Path
            输出目录

        Returns
        -------
        Path
            保存的日志文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        select_date, _ = self.parse_log_file()
        stats = self.generate_summary_stats()

        # 生成日志内容
        lines = []
        lines.append("=" * 40)
        lines.append("回测报告 - Z哥B1战法")
        lines.append("=" * 40)
        lines.append(f"选股日期: {select_date.strftime('%Y-%m-%d')} (来自 {self.log_file.name})")
        lines.append(f"数据目录: {self.data_dir}")
        lines.append("")
        lines.append(f"总交易次数: {stats['total']}")
        lines.append(f"  - 成功执行: {stats['success']}")
        lines.append(f"  - 无数据: {stats['no_data']}")
        lines.append(f"  - 无T+1: {stats['no_t1']}")
        lines.append(f"  - 无T+2: {stats['no_t2']}")

        if stats['success'] > 0:
            lines.append("")
            lines.append(f"平均收益率: {stats['avg_return']:.2f}%")
            lines.append(f"收益率中位数: {stats['median_return']:.2f}%")
            lines.append(f"最大收益: {stats['max_return']:.2f}%")
            lines.append(f"最大亏损: {stats['min_return']:.2f}%")
            lines.append(f"胜率: {stats['win_rate']:.2f}%")
            lines.append(f"盈利股票: {stats['profit_count']} 只")
            lines.append(f"亏损股票: {stats['loss_count']} 只")

            lines.append("")
            lines.append("个股明细 (按收益率排序):")
            lines.append(f"{'代码':<10} {'买入日期':<12} {'卖出日期':<12} {'买入价':<8} {'卖出价':<8} {'收益率':<10}")
            lines.append("-" * 70)

            # 按收益率从高到低排序
            sorted_results = sorted(
                [r for r in self.results if r.status == 'success'],
                key=lambda x: x.return_pct or 0,
                reverse=True
            )
            failed_results = [r for r in self.results if r.status != 'success']

            for r in sorted_results:
                return_str = f"{r.return_pct:+.2f}%"
                lines.append(f"{r.code:<10} {r.buy_date.strftime('%Y-%m-%d'):<12} "
                           f"{r.sell_date.strftime('%Y-%m-%d'):<12} "
                           f"{r.buy_price:<8.2f} {r.sell_price:<8.2f} {return_str:<10}")

            # 失败的结果放在最后
            for r in failed_results:
                status_msg = {
                    'no_data': '无数据',
                    'no_t1': '无T+1',
                    'no_t2': '无T+2'
                }.get(r.status, r.status)
                lines.append(f"{r.code:<10} {'-':<12} {'-':<12} {'-':<8} {'-':<8} {status_msg:<10}")

        lines.append("=" * 40)

        # 写入文件
        output_path = output_dir / "backtest_results.log"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info(f"回测报告已保存至: {output_path}")
        return output_path

    def print_console_report(self):
        """打印控制台报告"""
        stats = self.generate_summary_stats()
        select_date, _ = self.parse_log_file()

        print("\n" + "=" * 40)
        print("回测报告 - Z哥B1战法")
        print("=" * 40)
        print(f"选股日期: {select_date.strftime('%Y-%m-%d')} (来自 {self.log_file.name})")
        print(f"数据目录: {self.data_dir}")
        print()
        print(f"总交易次数: {stats['total']}")
        print(f"  - 成功执行: {stats['success']}")
        print(f"  - 无数据: {stats['no_data']}")
        print(f"  - 无T+1: {stats['no_t1']}")
        print(f"  - 无T+2: {stats['no_t2']}")

        if stats['success'] > 0:
            print()
            print(f"平均收益率: {stats['avg_return']:.2f}%")
            print(f"收益率中位数: {stats['median_return']:.2f}%")
            print(f"最大收益: {stats['max_return']:.2f}%")
            print(f"最大亏损: {stats['min_return']:.2f}%")
            print(f"胜率: {stats['win_rate']:.2f}%")
            print(f"盈利股票: {stats['profit_count']} 只")
            print(f"亏损股票: {stats['loss_count']} 只")

            # 打印个股明细（按收益率从高到低排序）
            print()
            print("个股明细 (按收益率排序):")
            print(f"{'代码':<10} {'买入日期':<12} {'卖出日期':<12} {'买入价':<8} {'卖出价':<8} {'收益率':<10}")
            print("-" * 70)

            # 按收益率从高到低排序
            sorted_results = sorted(
                [r for r in self.results if r.status == 'success'],
                key=lambda x: x.return_pct or 0,
                reverse=True
            )
            failed_results = [r for r in self.results if r.status != 'success']

            for r in sorted_results:
                return_str = f"{r.return_pct:+.2f}%"
                print(f"{r.code:<10} {r.buy_date.strftime('%Y-%m-%d'):<12} "
                      f"{r.sell_date.strftime('%Y-%m-%d'):<12} "
                      f"{r.buy_price:<8.2f} {r.sell_price:<8.2f} {return_str:<10}")

            # 失败的结果放在最后
            for r in failed_results:
                status_msg = {
                    'no_data': '无数据',
                    'no_t1': '无T+1',
                    'no_t2': '无T+2'
                }.get(r.status, r.status)
                print(f"{r.code:<10} {'-':<12} {'-':<12} {'-':<8} {'-':<8} {status_msg:<10}")

        print("=" * 40)


# ==================== 主函数 ====================

def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="Z哥B1战法回测脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s --data-dir ./data
  %(prog)s --data-dir ./data --log-file zgnb_zk_results.log
  %(prog)s --data-dir ./data --date 2026-01-20
  %(prog)s --data-dir ./data --output-dir ./my_results

回测逻辑:
  T: 选股日期（从日志文件读取）
  T+1: 开盘价买入
  T+2: 收盘价卖出
  收益率 = (卖出价 - 买入价) / 买入价 × 100%%
        """
    )

    parser.add_argument(
        '--data-dir',
        default='./data',
        help='K线数据目录 (默认: ./data)'
    )
    parser.add_argument(
        '--log-file',
        default='zgnb_zk_results.log',
        help='选股结果日志文件 (默认: zgnb_zk_results.log)'
    )
    parser.add_argument(
        '--date',
        default=None,
        help='指定回测日期 (YYYY-MM-DD)，不指定则使用日志中最后一个日期'
    )
    parser.add_argument(
        '--list-dates',
        action='store_true',
        help='列出日志文件中所有可用的日期'
    )
    parser.add_argument(
        '--output-dir',
        default='./backtest_results',
        help='输出目录 (默认: ./backtest_results)'
    )

    args = parser.parse_args()

    # 验证数据目录存在
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error(f"数据目录不存在: {data_dir}")
        sys.exit(1)

    # 验证日志文件存在
    log_file = Path(args.log_file)
    if not log_file.exists():
        logger.error(f"日志文件不存在: {log_file}")
        sys.exit(1)

    try:
        # 列出可用日期
        if args.list_dates:
            available_dates = get_available_dates(log_file)
            if not available_dates:
                print(f"日志文件中没有找到任何选股日期: {log_file}")
            else:
                print(f"日志文件中可用的选股日期:")
                for d in available_dates:
                    print(f"  - {d.strftime('%Y-%m-%d')}")
            return

        # 解析目标日期
        target_date = None
        if args.date:
            try:
                target_date = pd.to_datetime(args.date)
            except Exception as e:
                logger.error(f"日期格式错误: {args.date}, 请使用 YYYY-MM-DD 格式")
                sys.exit(1)

        # 创建回测引擎
        engine = BacktestEngine(data_dir, log_file, target_date)

        # 执行回测
        engine.run_backtest()

        # 打印报告
        engine.print_console_report()

        # 保存结果到日志文件和CSV
        output_dir = Path(args.output_dir)
        engine.save_results_to_log(output_dir)
        engine.save_results_to_csv(output_dir)

    except FileNotFoundError as e:
        logger.error(e)
        sys.exit(1)
    except ValueError as e:
        logger.error(e)
        sys.exit(1)
    except Exception as e:
        logger.error(f"回测执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
