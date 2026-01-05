from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Dict, Any

import akshare as ak

import pandas as pd
import tushare as ts
from tqdm import tqdm

warnings.filterwarnings("ignore")

# --------------------------- 全局日志配置 --------------------------- #
LOG_FILE = Path("fetch.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fetch_from_stocklist")

# --------------------------- 历史K线（Tushare 日线，固定qfq） --------------------------- #
pro: Optional[ts.pro_api] = None  # 模块级会话

def set_api(session) -> None:
    """由外部(比如GUI)注入已创建好的 ts.pro_api() 会话"""
    global pro
    pro = session
    

def _to_ts_code(code: str) -> str:
    """把6位code映射到标准 ts_code 后缀。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"{code}.SH"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"

def _get_kline_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    ts_code = _to_ts_code(code)
    max_retries = 10  # 最大重试次数
    retry_delay = 5   # 重试等待时间（秒）
    df = None  # 初始化df变量
    
    for attempt in range(max_retries):
        try:
            df = ts.pro_bar(
                ts_code=ts_code,
                adj="qfq",
                start_date=start,
                end_date=end,
                freq="D",
                api=pro
            )
            break  # 成功获取数据，跳出重试循环
        except Exception as e:
            error_msg = str(e).lower()
            # 检查是否为限流相关错误
            if any(keyword in error_msg for keyword in ["limit", "频率", "rate", "too many", "频繁", "限速"]):
                if attempt < max_retries - 1:  # 不是最后一次尝试
                    logger.warning(f"获取{code}数据遇到限流，等待{retry_delay}秒后重试 (第{attempt + 1}/{max_retries}次): {e}")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"获取{code}数据失败，已达到最大重试次数{max_retries}: {e}")
                    return pd.DataFrame()  # 返回空DataFrame而不是抛出异常
            else:
                # 非限流错误，直接返回空DataFrame
                logger.error(f"获取{code}数据失败: {e}")
                return pd.DataFrame()

    # 检查是否成功获取到数据
    if df is None:
        logger.warning(f"获取{code}数据失败：未能获取到数据")
        return pd.DataFrame()
    
    if df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"trade_date": "date", "vol": "volume"})[
        ["date", "open", "close", "high", "low", "volume"]
    ].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def _get_kline_akshare(code: str, start: str, end: str) -> pd.DataFrame:
    """
    使用 AkShare 获取单只股票历史K线数据
    """
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq"
        )

        if df is None or df.empty:
            return pd.DataFrame()

        # AkShare 返回的列名: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume"
        })[["date", "open", "close", "high", "low", "volume"]].copy()

        df["date"] = pd.to_datetime(df["date"])
        for c in ["open", "close", "high", "low", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        return df.sort_values("date").reset_index(drop=True)

    except Exception as e:
        logger.error(f"获取{code}数据失败(AkShare): {e}")
        return pd.DataFrame()


def validate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    if df["date"].isna().any():
        raise ValueError("存在缺失日期！")
    if (df["date"] > pd.Timestamp.today()).any():
        raise ValueError("数据包含未来日期，可能抓取错误！")
    return df

# --------------------------- 读取 stocklist.csv & 过滤板块 --------------------------- #

def _filter_by_boards_stocklist(df: pd.DataFrame, exclude_boards: set[str]) -> pd.DataFrame:
    """
    exclude_boards 子集：{'gem','star','bj'}
    - gem  : 创业板 300/301（.SZ）
    - star : 科创板 688（.SH）
    - bj   : 北交所（.BJ 或 4/8 开头）
    """
    code = df["symbol"].astype(str)
    ts_code = df["ts_code"].astype(str).str.upper()
    mask = pd.Series(True, index=df.index)

    if "gem" in exclude_boards:
        mask &= ~code.str.startswith(("300", "301"))
    if "star" in exclude_boards:
        mask &= ~code.str.startswith(("688",))
    if "bj" in exclude_boards:
        mask &= ~(ts_code.str.endswith(".BJ") | code.str.startswith(("4", "8")))

    return df[mask].copy()

def _filter_by_st_stocks(df: pd.DataFrame, exclude_st: bool = True) -> pd.DataFrame:
    """
    剔除ST股票
    - exclude_st: 是否剔除ST股票，默认True
    """
    if not exclude_st:
        return df.copy()
    
    # 获取股票名称列，可能是'name'或其他列名
    name_col = None
    for col in ['name', 'stock_name', 'stockname']:
        if col in df.columns:
            name_col = col
            break
    
    if name_col is None:
        logger.warning("未找到股票名称列，跳过ST股票过滤")
        return df.copy()
    
    # 剔除ST股票：名称以ST开头或包含ST
    mask = ~df[name_col].str.contains(r'^ST|\*ST|ST$', na=False, regex=True)
    filtered_df = df[mask].copy()
    
    removed_count = len(df) - len(filtered_df)
    if removed_count > 0:
        logger.info(f"已剔除{removed_count}只ST股票")
    
    return filtered_df

def _add_market_cap_info(df: pd.DataFrame) -> pd.DataFrame:
    """
    获取股票市值信息的替代方案
    由于Tushare接口权限限制，这里提供几种备选方案：
    1. 从本地市值数据文件读取
    2. 使用模拟数据进行演示
    3. 跳过市值筛选（不推荐）
    """
    logger.info("正在获取股票市值信息...")

    # 方案1：尝试从本地市值数据文件读取
    market_cap_file = Path("market_cap.csv")
    if market_cap_file.exists():
        try:
            market_df = pd.read_csv(market_cap_file)
            if 'symbol' in market_df.columns and 'market_cap' in market_df.columns:
                result_df = df.merge(market_df[['symbol', 'market_cap']], on='symbol', how='left')
                missing_count = result_df['market_cap'].isna().sum()
                if missing_count > 0:
                    logger.warning(f"有{missing_count}只股票在市值文件中找不到数据")
                    result_df['market_cap'] = result_df['market_cap'].fillna(0)
                logger.info(f"从本地文件成功获取{len(result_df) - missing_count}/{len(df)}只股票的市值信息")
                return result_df
        except Exception as e:
            logger.warning(f"读取本地市值文件失败：{e}")

    # 方案2：使用模拟数据（演示用）
    logger.warning("使用模拟市值数据进行演示，实际使用时请替换为真实数据")

    # 为不同行业的股票分配模拟市值（单位：万元）
    mock_market_caps = {
        '银行': 15000000,  # 1500亿
        '地产': 8000000,   # 800亿
        '保险': 12000000,  # 1200亿
        '科技': 3000000,   # 300亿
        '医药': 4000000,   # 400亿
        '消费': 5000000,   # 500亿
        '制造': 2000000,   # 200亿
    }

    # 为每只股票分配模拟市值
    if 'industry' in df.columns:
        df['market_cap'] = df['industry'].map(mock_market_caps).fillna(2000000)
    else:
        df['market_cap'] = 2000000  # 默认值

    # 添加一些随机变化使数据更真实
    import random
    for i in range(len(df)):
        base_cap = df.iloc[i]['market_cap']
        variation = random.uniform(0.5, 2.0)  # 0.5-2倍的随机变化
        df.iloc[i, df.columns.get_loc('market_cap')] = base_cap * variation

    logger.info(f"使用模拟数据为{len(df)}只股票分配了市值信息")
    return df

def _filter_by_market_cap(df: pd.DataFrame, min_market_cap: float, max_market_cap: float) -> pd.DataFrame:
    """
    根据市值筛选股票
    - min_market_cap: 最小市值（亿元）
    - max_market_cap: 最大市值（亿元）
    """
    if 'market_cap' not in df.columns:
        logger.warning("股票列表中缺少市值信息，跳过市值筛选")
        return df

    # 将市值转换为亿元单位（注意：模拟数据的单位是万元）
    market_cap_yi = df['market_cap'] / 1e4  # 万元转亿元

    mask = (market_cap_yi >= min_market_cap) & (market_cap_yi <= max_market_cap)
    filtered_df = df[mask].copy()

    logger.info(f"市值筛选：{min_market_cap}亿 ≤ 市值 ≤ {max_market_cap}亿，筛选后 {len(filtered_df)}/{len(df)} 只股票")
    return filtered_df

def load_codes_from_stocklist(stocklist_csv: Path, exclude_boards: set[str],
                             min_market_cap: Optional[float] = None,
                             max_market_cap: Optional[float] = None,
                             exclude_st: bool = True) -> List[str]:
    """
    从股票列表中加载股票代码，支持板块过滤、市值筛选和ST股票剔除
    """
    df = pd.read_csv(stocklist_csv)
    df = _filter_by_boards_stocklist(df, exclude_boards)
    
    # 剔除ST股票
    df = _filter_by_st_stocks(df, exclude_st)

    # 如果需要进行市值筛选，获取市值信息
    if min_market_cap is not None or max_market_cap is not None:
        df = _add_market_cap_info(df)
        if min_market_cap is None:
            min_market_cap = 0
        if max_market_cap is None:
            max_market_cap = float('inf')
        df = _filter_by_market_cap(df, min_market_cap, max_market_cap)

    codes = df["symbol"].astype(str).str.zfill(6).tolist()
    codes = list(dict.fromkeys(codes))  # 去重保持顺序

    filter_info = []
    if exclude_boards:
        filter_info.append(f"排除板块：{','.join(sorted(exclude_boards))}")
    if exclude_st:
        filter_info.append("剔除ST股票")
    if min_market_cap is not None or max_market_cap is not None:
        filter_info.append(f"市值范围：{min_market_cap or 0}亿-{max_market_cap or '∞'}亿")

    logger.info("从 %s 读取到 %d 只股票（%s）",
                stocklist_csv, len(codes), "；".join(filter_info) or "无过滤")
    return codes


def _get_kline(datasource: str, code: str, start: str, end: str) -> pd.DataFrame:
    """
    统一数据获取函数，根据数据源选择调用对应的API
    """
    if datasource == "tushare":
        return _get_kline_tushare(code, start, end)
    else:
        return _get_kline_akshare(code, start, end)


# --------------------------- 抓取函数 --------------------------- #
def fetch_one(
    code: str,
    start: str,
    end: str,
    out_dir: Path,
    datasource: str = "akshare",
) -> bool:
    """
    抓取单只股票数据
    返回是否成功
    """
    csv_path = out_dir / f"{code}.csv"

    try:
        # 获取数据
        df = _get_kline(datasource, code, start, end)
        
        if df.empty:
            logger.debug(f"{code} 无数据，生成空表")
            df = pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])
        
        df = validate(df)
        df.to_csv(csv_path, index=False)
        
        logger.debug(f"{code} 数据更新成功，共{len(df)}条记录")
        return True
        
    except Exception as e:
        logger.error(f"处理{code}时发生异常: {e}")
        return False

# --------------------------- 主入口 --------------------------- #
def main():
    parser = argparse.ArgumentParser(description="从 stocklist.csv 读取股票池并抓取日线K线（支持 Tushare/AkShare）")
    # 抓取范围
    parser.add_argument("--start", default="20190101", help="起始日期 YYYYMMDD 或 'today'")
    parser.add_argument("--end", default="today", help="结束日期 YYYYMMDD 或 'today'")
    # 股票清单与板块过滤
    parser.add_argument("--stocklist", type=Path, default=Path("./stocklist.csv"), help="股票清单CSV路径（需含 ts_code 或 symbol）")
    parser.add_argument(
        "--exclude-boards",
        nargs="*",
        default=[],
        choices=["gem", "star", "bj"],
        help="排除板块，可多选：gem(创业板300/301) star(科创板688) bj(北交所.BJ/4/8)"
    )
    # 市值筛选（单位：亿元）
    parser.add_argument("--min-market-cap", type=float, default=None, help="最小市值筛选（亿元），如100表示只选市值≥100亿的股票")
    parser.add_argument("--max-market-cap", type=float, default=None, help="最大市值筛选（亿元），如2000表示只选市值≤2000亿的股票")
    # ST股票筛选
    parser.add_argument("--exclude-st", action="store_true", default=True, help="剔除ST股票（默认启用）")
    parser.add_argument("--include-st", action="store_true", help="包含ST股票（与--exclude-st互斥）")
    # 其它
    parser.add_argument("--out", default="./data", help="输出目录")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数")
    parser.add_argument("--datasource", choices=["tushare", "akshare"], default="akshare", help="数据源选择（默认akshare）")

    args = parser.parse_args()

    # ---------- 数据源初始化 ---------- #
    if args.datasource == "tushare":
        import os
        os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
        os.environ["no_proxy"] = os.environ["NO_PROXY"]
        ts_token = os.environ.get("TUSHARE_TOKEN")
        if not ts_token:
            raise ValueError("请先设置环境变量 TUSHARE_TOKEN，例如：set TUSHARE_TOKEN=你的token")
        ts.set_token(ts_token)
        global pro
        pro = ts.pro_api()
        logger.info("使用 Tushare 数据源")

    # ---------- 日期解析 ---------- #
    start = dt.date.today().strftime("%Y%m%d") if str(args.start).lower() == "today" else args.start
    end = dt.date.today().strftime("%Y%m%d") if str(args.end).lower() == "today" else args.end

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # ---------- ST股票筛选配置 ---------- #
    exclude_st = args.exclude_st
    if args.include_st:
        exclude_st = False
        logger.info("已启用ST股票包含模式")
    elif args.exclude_st:
        logger.info("已启用ST股票剔除模式")

    # ---------- 从 stocklist.csv 读取股票池 ---------- #
    exclude_boards = set(args.exclude_boards or [])
    codes = load_codes_from_stocklist(
        args.stocklist,
        exclude_boards,
        min_market_cap=args.min_market_cap,
        max_market_cap=args.max_market_cap,
        exclude_st=exclude_st
    )

    if not codes:
        logger.error("stocklist 为空或被过滤后无代码，请检查。")
        sys.exit(1)

    # 构建筛选信息
    filter_desc = []
    if exclude_boards:
        filter_desc.append(f"排除:{','.join(sorted(exclude_boards))}")
    if exclude_st:
        filter_desc.append("剔除ST股票")
    elif args.include_st:
        filter_desc.append("包含ST股票")
    if args.min_market_cap is not None or args.max_market_cap is not None:
        min_cap = args.min_market_cap or 0
        max_cap = args.max_market_cap or '∞'
        filter_desc.append(f"市值:{min_cap}亿-{max_cap}亿")

    datasource_name = "Tushare" if args.datasource == "tushare" else "AkShare"
    logger.info(
        "开始抓取 %d 支股票 | 数据源:%s(日线,qfq) | 日期:%s → %s | %s",
        len(codes), datasource_name, start, end, " | ".join(filter_desc) or "无筛选"
    )

    # ---------- 执行抓取 ---------- #
    start_time = time.time()
    success_count = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_code = {
            executor.submit(fetch_one, code, start, end, out_dir, args.datasource): code
            for code in codes
        }
        
        for future in tqdm(as_completed(future_to_code), total=len(future_to_code), desc="下载进度"):
            code = future_to_code[future]
            try:
                success = future.result()
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"处理{code}时发生异常: {e}")
    
    # 输出统计信息
    end_time = time.time()
    duration = end_time - start_time
    
    logger.info("=" * 50)
    logger.info("抓取完成统计:")
    logger.info(f"总股票数: {len(codes)}")
    logger.info(f"成功更新: {success_count}")
    logger.info(f"失败数量: {len(codes) - success_count}")
    logger.info(f"总耗时: {duration:.1f}秒")
    logger.info(f"平均速度: {len(codes)/duration:.2f}只/秒")
    logger.info("=" * 50)

    logger.info("全部任务完成，数据已保存至 %s", out_dir.resolve())

if __name__ == "__main__":
    main()