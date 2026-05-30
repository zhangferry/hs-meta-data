# hs-meta-data

炉石传说元数据自动采集仓库。通过 GitHub Actions 每日自动从多个数据源抓取最新数据。

## 数据源

| 来源 | 数据 | 更新频率 |
|------|------|---------|
| [HearthstoneJSON](https://hearthstonejson.com) | 卡牌数据库 (7,935+ 张) | 版本更新时 |
| [Firestone](https://firestoneapp.com) | Meta 卡组统计 (胜率/场次) | 每日 |
| [HSReplay](https://hsreplay.net) | Archetype 定义 (748 个) | 每日 |
| [Vicious Syndicate](https://vicioussyndicate.com) | 对局匹配胜率矩阵 | 每周 |

## 目录结构

```
├── cards/           # 卡牌数据库 (zhCN, enUS)
├── meta/            # Meta 卡组统计
│   ├── standard/    # 标准模式
│   │   ├── all/     # 全段位
│   │   ├── diamond/ # 钻石
│   │   └── legend/  # 传说
│   └── wild/        # 狂野模式
├── matchup/         # 对局匹配数据
│   ├── latest.json  # 最新一期
│   └── history/     # 历史数据
├── archetypes/      # Archetype 定义
└── metadata.json    # 元信息
```

## CDN 访问

通过 jsdelivr CDN 加速访问：
```
https://cdn.jsdelivr.net/gh/{user}/hs-meta-data@latest/meta/standard/diamond/past-7.json
https://cdn.jsdelivr.net/gh/{user}/hs-meta-data@latest/cards/cards_collectible_zhCN.json
```

## 手动触发

在 GitHub Actions 页面点击 "Run workflow" 即可手动触发数据更新。
