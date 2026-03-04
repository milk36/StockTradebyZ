# fetch_kline.py - 数据获取模块

## 概述

数据获取模块负责从多个数据源（AkShare/Tushare/Mootdx）获取A股历史K线数据，支持按市值筛选、多线程下载、自动增量更新等功能。

## 架构设计

```
fetch_kline.py
├── 数据源适配器
│   ├── AkShare数据源
│   │   ├── --akshare-source tx   - 腾讯接口（默认）
│   │   ├── --akshare-source em   - 东方财富
│   │   └── --akshare-source cdr  - 新浪
│   ├── Tushare数据源
│   │   └── 需要设置Token
│   └── Mootdx数据源
│       └── 需先运行 bestip 探测
│
├── 股票筛选
│   ├── --stocklist        - 指定股票列表文件
│   ├── --min-market-cap   - 最小市值筛选
│   ├── --max-market-cap   - 最大市值筛选
│   └── --exclude-boards   - 排除板块（gem/star/bj）
│
├── 下载控制
│   ├── --start / --end    - 日期范围
│   ├── --workers          - 并发线程数
│   ├── --rate-limit-interval - 请求间隔（秒）
│   └── --force-reload     - 强制全量重新下载
│
└── 增量更新
    ├── 自动检测本地CSV
    ├── 跳过已有数据的股票
    └── 仅下载新增数据
```

## 命令行参数

```
usage: fetch_kline.py [options]

必需参数:
  --start START           开始日期 YYYYMMDD
  --end END               结束日期 YYYYMMDD (可用 "today")

可选参数:
  --datasource {akshare,tushare,mootdx}
                          数据源选择 (默认: akshare)
  --akshare-source {tx,em,cdr}
                          AkShare数据源 (默认: tx)
  --stocklist STOCKLIST   股票列表文件
  --exclude-boards EXCLUDE_BOARDS
                          排除板块，逗号分隔 (gem/star/bj)
  --min-market-cap MIN    最小市值（亿元）
  --max-market-cap MAX    最大市值（亿元）
  --out OUT               输出目录 (默认: ./data)
  --workers N             并发线程数 (默认: 15)
  --rate-limit-interval SEC
                          请求间隔秒数 (默认: 0.5)
  --force-reload          强制全量重新下载
```

## 数据源对比

| 数据源 | 优点 | 缺点 | 推荐度 |
|--------|------|------|--------|
| AkShare (腾讯) | 免费无需注册 | 可能有频率限制 | ⭐⭐⭐⭐⭐ |
| AkShare (东财) | 数据较新 | 偶尔不稳定 | ⭐⭐⭐⭐ |
| AkShare (新浪) | 备用源 | 数据可能延迟 | ⭐⭐⭐ |
| Tushare | 数据质量高 | 需要Token且有积分限制 | ⭐⭐⭐ |
| Mootdx | 速度快 | 需要探测最佳IP | ⭐⭐⭐ |

## 使用示例

### 首次全量下载

```bash
# 下载市值50-2500亿的主板和创业板股票
python fetch_kline.py \
    --start 20250101 \
    --end today \
    --stocklist ./stocklist.csv \
    --exclude-boards bj \
    --out ./data \
    --workers 15 \
    --min-market-cap 50 \
    --max-market-cap 2500

# 排除创业板和科创板
python fetch_kline.py \
    --start 20250101 \
    --end today \
    --stocklist ./stocklist.csv \
    --exclude-boards gem star bj \
    --out ./data \
    --workers 15 \
    --min-market-cap 50 \
    --max-market-cap 2500
```

### 日常增量更新

```bash
# 自动跳过已有数据，仅下载新增（2-5分钟）
python fetch_kline.py \
    --start 20250101 \
    --end today \
    --stocklist ./stocklist.csv \
    --exclude-boards bj \
    --out ./data \
    --workers 15
```

### 强制全量重新下载

```bash
# 覆盖已有数据
python fetch_kline.py \
    --start 20250101 \
    --end today \
    --stocklist ./stocklist.csv \
    --exclude-boards bj \
    --out ./data \
    --workers 15 \
    --force-reload
```

### 使用不同数据源

```bash
# 使用Tushare（需先设置Token）
python fetch_kline.py --datasource tushare --start 20250101 --end today ...

# 使用东方财富
python fetch_kline.py --akshare-source em --start 20250101 --end today ...

# 使用新浪
python fetch_kline.py --akshare-source cdr --start 20250101 --end today ...
```

### 调整请求间隔（限流时使用）

```bash
# 遇到API限流时增大间隔
python fetch_kline.py \
    --start 20250101 \
    --end today \
    --stocklist ./stocklist.csv \
    --exclude-boards bj \
    --out ./data \
    --workers 10 \
    --rate-limit-interval 2.0
```

## 股票列表文件

`stocklist.csv` 格式（可选）：

```csv
code,name
600000,浦发银行
600001,邯郸钢铁
600003,ST东北高速
...
```

如果不指定 `--stocklist`，程序会自动获取全部A股列表。

## 增量更新机制

### 工作原理

```
1. 扫描本地CSV文件
   ↓
2. 对比每个股票的最新日期
   ↓
3. 如果本地数据>=目标日期，跳过
   ↓
4. 如果本地数据<目标日期，仅下载缺失部分
   ↓
5. 追加到本地CSV文件
```

### 性能对比

| 场景 | 全量下载 | 增量更新 |
|------|----------|----------|
| 5000只股票 | ~40分钟 | ~2-5分钟 |
| 1000只股票 | ~8分钟 | ~30秒-1分钟 |

## 板块代码说明

| 代码 | 板块 | 说明 |
|------|------|------|
| gem | 创业板 | 30xxxx |
| star | 科创板 | 68xxxx |
| bj | 北交所 | 4xxxx, 8xxxx |

## 输出文件格式

每只股票一个CSV文件：`{股票代码}.csv`

```csv
date,open,close,high,low,volume
2025-01-01,10.5,10.8,10.3,10.6,1000000
2025-01-02,10.6,10.9,10.5,10.7,1100000
...
```

## Tushare配置

如需使用Tushare数据源，需要：

1. 注册Tushare账号：https://tushare.pro
2. 获取API Token
3. 在 `fetch_kline.py` 中设置Token（约第307行）：

```python
# 设置Tushare Token
ts.set_token('你的Token')
pro = ts.pro_api()
```

## Mootdx配置

如需使用Mootdx数据源，需要：

1. 先探测最佳IP：

```bash
python -m mootdx bestip -vv
```

2. 然后运行下载：

```bash
python fetch_kline.py --datasource mootdx --frequency 4 --out ./data --workers 10
```

## 日志和错误处理

### 日志文件

- `fetch.log` - 数据获取日志

### 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 连接超时 | 网络问题或API限制 | 减少并发数，增大请求间隔 |
| 数据为空 | 股票退市或停牌 | 忽略，正常现象 |
| Token无效 | Tushare Token错误 | 检查Token设置 |
| 内存不足 | 数据量太大 | 减少并发数，分批下载 |

## 性能优化建议

1. **并发数**: 默认15，网络好时可增加到20-30
2. **请求间隔**: 默认0.5秒，限流时可增大到1-2秒
3. **增量更新**: 日常更新务必使用增量模式
4. **分批下载**: 股票过多时按市值分批下载

## 注意事项

1. **交易时间**: 建议在收盘后（15:00后）更新数据
2. **数据质量**: 定期抽查数据完整性
3. **存储空间**: 5000只股票约需500MB-1GB空间
4. **备份**: 定期备份data目录
5. **合规使用**: 遵守数据源的使用条款
