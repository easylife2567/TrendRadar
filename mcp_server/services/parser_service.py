"""
数据解析服务

v2.0.0: 仅支持 SQLite 数据库，移除 TXT 文件支持
新存储结构：output/{type}/{date}.db
"""

import re
import sqlite3
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

import yaml

from ..utils.errors import FileParseError, DataNotFoundError, InvalidParameterError
from .cache_service import get_cache


class ParserService:
    """数据解析服务类"""

    def __init__(self, project_root: str = None, readonly: bool = False, data_root: str = None):
        """
        初始化解析服务

        Args:
            project_root: 项目根目录，默认为当前目录的父目录
            readonly: 只读模式（Web 层使用）。以 mode=ro URI 打开 SQLite，
                      任何查询都不会产生写副作用（包括不会误建空库）
            data_root: 数据根目录覆盖（D9②）。仅影响 output/ 数据查找，
                       不影响 config/ 等代码仓资源；默认跟随 project_root
        """
        if project_root is None:
            current_file = Path(__file__)
            self.project_root = current_file.parent.parent.parent
        else:
            self.project_root = Path(project_root)

        self.data_root = Path(data_root) if data_root else self.project_root
        self.readonly = readonly

        self.cache = get_cache()

        # frequency_words.txt mtime 缓存
        self._freq_words_cache: Optional[List[Dict]] = None
        self._freq_words_mtime: float = 0.0

    @staticmethod
    def clean_title(title: str) -> str:
        """清理标题文本"""
        title = re.sub(r'\s+', ' ', title)
        title = title.strip()
        return title

    def get_date_folder_name(self, date: datetime = None) -> str:
        """
        获取日期字符串（ISO 格式）

        Args:
            date: 日期对象，默认为今天

        Returns:
            日期字符串（YYYY-MM-DD）
        """
        if date is None:
            date = datetime.now()
        return date.strftime("%Y-%m-%d")

    def _get_db_path(self, date: datetime = None, db_type: str = "news") -> Optional[Path]:
        """
        获取数据库文件路径

        新结构：{data_root}/output/{type}/{date}.db

        Args:
            date: 日期对象，默认为今天
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            数据库文件路径，如果不存在则返回 None
        """
        date_str = self.get_date_folder_name(date)
        db_path = self.data_root / "output" / db_type / f"{date_str}.db"
        if db_path.exists():
            return db_path
        return None

    def _open_sqlite(self, db_path: Path) -> sqlite3.Connection:
        """
        统一的 SQLite 连接工厂

        readonly=True 时以 file:...?mode=ro 只读 URI 打开（D5：新闻库严格只读）：
        - 路径经 urllib.parse.quote URL 编码，空格/中文/特殊字符不破坏 URI 语义
        - 不用 immutable=1：管线会持续写库，其缓存假设不成立
        - 库文件不存在时 connect 直接抛 OperationalError，不会静默误建空库

        Args:
            db_path: 数据库文件路径

        Returns:
            已设置 row_factory 的连接
        """
        if self.readonly:
            uri = "file:" + urllib.parse.quote(str(db_path.resolve())) + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        else:
            conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connect_readonly(self, date: datetime = None, db_type: str = "news"):
        """
        以只读模式打开某日数据库的上下文（供数据服务层做自定义查询）

        无论 self.readonly 为何值都强制只读打开，供只读语义明确的自定义查询使用。

        Args:
            date: 日期对象，默认为今天
            db_type: 数据库类型 ("news" 或 "rss")

        Yields:
            sqlite3.Connection（row_factory 已设置）

        Raises:
            DataNotFoundError: 数据库文件不存在
        """
        db_path = self._get_db_path(date, db_type)
        if db_path is None:
            date_str = self.get_date_folder_name(date)
            raise DataNotFoundError(f"未找到 {date_str} 的 {db_type} 数据库")
        uri = "file:" + urllib.parse.quote(str(db_path.resolve())) + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _read_from_sqlite(
        self,
        date: datetime = None,
        platform_ids: Optional[List[str]] = None,
        db_type: str = "news"
    ) -> Optional[Tuple[Dict, Dict, Dict]]:
        """
        从 SQLite 数据库读取数据

        Args:
            date: 日期对象，默认为今天
            platform_ids: 平台ID列表，None表示所有平台
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            (all_titles, id_to_name, all_timestamps) 元组，如果数据库不存在返回 None
        """
        db_path = self._get_db_path(date, db_type)
        if db_path is None:
            return None

        all_titles = {}
        id_to_name = {}
        all_timestamps = {}

        try:
            conn = self._open_sqlite(db_path)
            cursor = conn.cursor()

            if db_type == "news":
                return self._read_news_from_sqlite(cursor, platform_ids, all_titles, id_to_name, all_timestamps)
            elif db_type == "rss":
                return self._read_rss_from_sqlite(cursor, platform_ids, all_titles, id_to_name, all_timestamps)

        except Exception as e:
            print(f"Warning: 从 SQLite 读取数据失败: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def _read_news_from_sqlite(
        self,
        cursor,
        platform_ids: Optional[List[str]],
        all_titles: Dict,
        id_to_name: Dict,
        all_timestamps: Dict
    ) -> Optional[Tuple[Dict, Dict, Dict]]:
        """从热榜数据库读取数据"""
        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='news_items'
        """)
        if not cursor.fetchone():
            return None

        # 构建查询
        if platform_ids:
            placeholders = ','.join(['?' for _ in platform_ids])
            query = f"""
                SELECT n.id, n.platform_id, p.name as platform_name, n.title,
                       n.rank, n.url, n.mobile_url,
                       n.first_crawl_time, n.last_crawl_time, n.crawl_count
                FROM news_items n
                LEFT JOIN platforms p ON n.platform_id = p.id
                WHERE n.platform_id IN ({placeholders})
            """
            cursor.execute(query, platform_ids)
        else:
            cursor.execute("""
                SELECT n.id, n.platform_id, p.name as platform_name, n.title,
                       n.rank, n.url, n.mobile_url,
                       n.first_crawl_time, n.last_crawl_time, n.crawl_count
                FROM news_items n
                LEFT JOIN platforms p ON n.platform_id = p.id
            """)

        rows = cursor.fetchall()

        # 收集所有 news_item_id 用于查询历史排名
        news_ids = [row['id'] for row in rows]
        rank_history_map = {}

        if news_ids:
            placeholders = ",".join("?" * len(news_ids))
            cursor.execute(f"""
                SELECT news_item_id, rank FROM rank_history
                WHERE news_item_id IN ({placeholders})
                ORDER BY news_item_id, crawl_time
            """, news_ids)

            for rh_row in cursor.fetchall():
                news_id = rh_row['news_item_id']
                rank = rh_row['rank']
                if news_id not in rank_history_map:
                    rank_history_map[news_id] = []
                rank_history_map[news_id].append(rank)

        for row in rows:
            news_id = row['id']
            platform_id = row['platform_id']
            platform_name = row['platform_name'] or platform_id
            title = row['title']

            if platform_id not in id_to_name:
                id_to_name[platform_id] = platform_name

            if platform_id not in all_titles:
                all_titles[platform_id] = {}

            ranks = rank_history_map.get(news_id, [row['rank']])

            all_titles[platform_id][title] = {
                "id": news_id,
                "ranks": ranks,
                "url": row['url'] or "",
                "mobileUrl": row['mobile_url'] or "",
                "first_time": row['first_crawl_time'] or "",
                "last_time": row['last_crawl_time'] or "",
                "count": row['crawl_count'] or 1,
            }

        # 获取抓取时间作为 timestamps
        cursor.execute("""
            SELECT crawl_time, created_at FROM crawl_records
            ORDER BY crawl_time
        """)
        for row in cursor.fetchall():
            crawl_time = row['crawl_time']
            created_at = row['created_at']
            try:
                ts = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").timestamp()
            except (ValueError, TypeError):
                ts = datetime.now().timestamp()
            all_timestamps[f"{crawl_time}.db"] = ts

        if not all_titles:
            return None

        return (all_titles, id_to_name, all_timestamps)

    def _read_rss_from_sqlite(
        self,
        cursor,
        feed_ids: Optional[List[str]],
        all_items: Dict,
        id_to_name: Dict,
        all_timestamps: Dict
    ) -> Optional[Tuple[Dict, Dict, Dict]]:
        """从 RSS 数据库读取数据"""
        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='rss_items'
        """)
        if not cursor.fetchone():
            return None

        # 构建查询
        if feed_ids:
            placeholders = ','.join(['?' for _ in feed_ids])
            query = f"""
                SELECT i.id, i.feed_id, f.name as feed_name, i.title,
                       i.url, i.published_at, i.summary, i.author,
                       i.first_crawl_time, i.last_crawl_time, i.crawl_count
                FROM rss_items i
                LEFT JOIN rss_feeds f ON i.feed_id = f.id
                WHERE i.feed_id IN ({placeholders})
                ORDER BY i.published_at DESC
            """
            cursor.execute(query, feed_ids)
        else:
            cursor.execute("""
                SELECT i.id, i.feed_id, f.name as feed_name, i.title,
                       i.url, i.published_at, i.summary, i.author,
                       i.first_crawl_time, i.last_crawl_time, i.crawl_count
                FROM rss_items i
                LEFT JOIN rss_feeds f ON i.feed_id = f.id
                ORDER BY i.published_at DESC
            """)

        rows = cursor.fetchall()

        for row in rows:
            feed_id = row['feed_id']
            feed_name = row['feed_name'] or feed_id
            title = row['title']

            if feed_id not in id_to_name:
                id_to_name[feed_id] = feed_name

            if feed_id not in all_items:
                all_items[feed_id] = {}

            all_items[feed_id][title] = {
                "url": row['url'] or "",
                "published_at": row['published_at'] or "",
                "summary": row['summary'] or "",
                "author": row['author'] or "",
                "first_time": row['first_crawl_time'] or "",
                "last_time": row['last_crawl_time'] or "",
                "count": row['crawl_count'] or 1,
            }

        # 获取抓取时间
        cursor.execute("""
            SELECT crawl_time, created_at FROM rss_crawl_records
            ORDER BY crawl_time
        """)
        for row in cursor.fetchall():
            crawl_time = row['crawl_time']
            created_at = row['created_at']
            try:
                ts = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").timestamp()
            except (ValueError, TypeError):
                ts = datetime.now().timestamp()
            all_timestamps[f"{crawl_time}.db"] = ts

        if not all_items:
            return None

        return (all_items, id_to_name, all_timestamps)

    def read_all_titles_for_date(
        self,
        date: datetime = None,
        platform_ids: Optional[List[str]] = None,
        db_type: str = "news"
    ) -> Tuple[Dict, Dict, Dict]:
        """
        读取指定日期的所有数据（带缓存）

        Args:
            date: 日期对象，默认为今天
            platform_ids: 平台/Feed ID列表，None表示所有
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            (all_titles, id_to_name, all_timestamps) 元组

        Raises:
            DataNotFoundError: 数据不存在
        """
        date_str = self.get_date_folder_name(date)
        platform_key = ','.join(sorted(platform_ids)) if platform_ids else 'all'
        cache_key = f"read_all:{db_type}:{date_str}:{platform_key}"

        is_today = (date is None) or (date.date() == datetime.now().date())
        ttl = 900 if is_today else 900

        cached = self.cache.get(cache_key, ttl=ttl)
        if cached:
            return cached

        result = self._read_from_sqlite(date, platform_ids, db_type)
        if result:
            self.cache.set(cache_key, result)
            return result

        raise DataNotFoundError(
            f"未找到 {date_str} 的 {db_type} 数据",
            suggestion="请先运行爬虫或检查日期是否正确"
        )

    def parse_yaml_config(self, config_path: str = None) -> dict:
        """
        解析YAML配置文件

        Args:
            config_path: 配置文件路径，默认为 config/config.yaml

        Returns:
            配置字典

        Raises:
            FileParseError: 配置文件解析错误
        """
        if config_path is None:
            config_path = self.project_root / "config" / "config.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileParseError(str(config_path), "配置文件不存在")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            return config_data
        except Exception as e:
            raise FileParseError(str(config_path), str(e))

    def parse_frequency_words(self, words_file: str = None) -> List[Dict]:
        """
        解析关键词配置文件（带 mtime 缓存）

        仅当 frequency_words.txt 被修改时才重新解析，避免循环内重复 IO。

        复用 trendradar.core.frequency 的解析逻辑，支持：
        - # 开头的注释行
        - 空行分隔词组
        - [组别名] 作为词组第一行，给整组指定别名
        - +前缀必须词、!前缀过滤词、@数量限制
        - /pattern/ 正则表达式语法
        - => 别名 显示名称语法
        - [GLOBAL_FILTER] 全局过滤区域

        显示名称优先级：组别名 > 行别名拼接 > 关键词拼接

        Args:
            words_file: 关键词文件路径，默认为 config/frequency_words.txt

        Returns:
            词组列表

        Raises:
            FileParseError: 文件解析错误
        """
        import os
        from trendradar.core.frequency import load_frequency_words

        if words_file is None:
            words_file = str(self.project_root / "config" / "frequency_words.txt")
        else:
            words_file = str(words_file)

        try:
            current_mtime = os.path.getmtime(words_file)

            if self._freq_words_cache is not None and current_mtime == self._freq_words_mtime:
                return self._freq_words_cache

            word_groups, filter_words, global_filters = load_frequency_words(words_file)
            self._freq_words_cache = word_groups
            self._freq_words_mtime = current_mtime
            return word_groups
        except FileNotFoundError:
            return []
        except Exception as e:
            raise FileParseError(words_file, str(e))

    def get_available_dates(self, db_type: str = "news") -> List[str]:
        """
        获取可用的日期列表

        Args:
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            日期字符串列表（YYYY-MM-DD 格式，降序排列）
        """
        db_dir = self.data_root / "output" / db_type
        if not db_dir.exists():
            return []

        dates = []
        for db_file in db_dir.glob("*.db"):
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})\.db$', db_file.name)
            if date_match:
                dates.append(date_match.group(1))

        return sorted(dates, reverse=True)

    def get_available_date_range(self, db_type: str = "news") -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        获取可用的日期范围

        Args:
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            (最早日期, 最新日期) 元组，如果没有数据则返回 (None, None)
        """
        dates = self.get_available_dates(db_type)
        if not dates:
            return (None, None)

        earliest = datetime.strptime(dates[-1], "%Y-%m-%d")
        latest = datetime.strptime(dates[0], "%Y-%m-%d")
        return (earliest, latest)

    # ============================================
    # Web 层下沉查询（design/03 §2.4/§2.5，P1 差异#11）
    # ============================================

    def get_rank_history(
        self,
        date: datetime = None,
        news_id: int = None,
        include_title_changes: bool = True,
    ) -> Dict:
        """
        查询单条新闻的排名轨迹（含可选的标题变更历史）

        注意：rank_history.crawl_time 为 "HH-MM" 短格式（如 "00-47"），
        当日内字典序即时间序，直接按值排序即可。

        Args:
            date: 日期对象，默认为今天
            news_id: news_items.id
            include_title_changes: 是否附带标题变更历史

        Returns:
            {"news": {...}, "rank_history": [...], "title_changes": [...]}

        Raises:
            DataNotFoundError: 数据库不存在或新闻条目不存在
        """
        if news_id is None:
            raise DataNotFoundError("缺少 news_id，无法查询排名轨迹")

        date_str = self.get_date_folder_name(date)
        with self.connect_readonly(date, "news") as conn:
            item = conn.execute(
                "SELECT * FROM news_items WHERE id = ?", (news_id,)
            ).fetchone()
            if item is None:
                raise DataNotFoundError(f"{date_str} 数据库中不存在 id={news_id} 的新闻")

            rank_rows = conn.execute(
                "SELECT rank, crawl_time FROM rank_history "
                "WHERE news_item_id = ? ORDER BY crawl_time, id",
                (news_id,),
            ).fetchall()

            title_rows = []
            if include_title_changes:
                try:
                    title_rows = conn.execute(
                        "SELECT old_title, new_title, changed_at FROM title_changes "
                        "WHERE news_item_id = ? ORDER BY changed_at",
                        (news_id,),
                    ).fetchall()
                except sqlite3.OperationalError:
                    # 旧库可能无 title_changes 表，降级为空
                    title_rows = []

        return {
            "news": dict(item),
            "rank_history": [
                {"rank": row["rank"], "crawl_time": row["crawl_time"]}
                for row in rank_rows
            ],
            "title_changes": [dict(row) for row in title_rows],
        }

    def get_source_health(self, date: datetime = None, db_type: str = "news") -> Dict:
        """
        查询某日的采集源健康度（每次采集对各平台的 success/failed）

        Args:
            date: 日期对象，默认为今天
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            {
              "date": "YYYY-MM-DD",
              "crawls": [{"crawl_time": "00-47", "sources": [{"platform_id", "platform_name", "status"}]}],
              "platforms": {"weibo": {"success": 12, "failed": 1}, ...},
              "summary": {"crawl_count": n, "total_checks": n, "failed_checks": n}
            }

        Raises:
            DataNotFoundError: 数据库不存在
        """
        date_str = self.get_date_folder_name(date)
        with self.connect_readonly(date, db_type) as conn:
            # 旧库可能无 crawl_source_status 表
            try:
                rows = conn.execute(
                    """
                    SELECT cr.crawl_time, css.platform_id, p.name AS platform_name, css.status
                    FROM crawl_records cr
                    JOIN crawl_source_status css ON css.crawl_record_id = cr.id
                    LEFT JOIN platforms p ON p.id = css.platform_id
                    ORDER BY cr.crawl_time, css.platform_id
                    """
                ).fetchall()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    return {
                        "date": date_str,
                        "crawls": [],
                        "platforms": {},
                        "summary": {"crawl_count": 0, "total_checks": 0, "failed_checks": 0},
                    }
                raise

        crawls: Dict[str, List[Dict]] = {}
        platforms: Dict[str, Dict[str, int]] = {}
        total_checks = 0
        failed_checks = 0
        for row in rows:
            crawls.setdefault(row["crawl_time"], []).append({
                "platform_id": row["platform_id"],
                "platform_name": row["platform_name"] or row["platform_id"],
                "status": row["status"],
            })
            stats = platforms.setdefault(row["platform_id"], {"success": 0, "failed": 0})
            stats[row["status"]] = stats.get(row["status"], 0) + 1
            total_checks += 1
            if row["status"] == "failed":
                failed_checks += 1

        return {
            "date": date_str,
            "crawls": [
                {"crawl_time": ct, "sources": crawls[ct]} for ct in sorted(crawls)
            ],
            "platforms": platforms,
            "summary": {
                "crawl_count": len(crawls),
                "total_checks": total_checks,
                "failed_checks": failed_checks,
            },
        }

    def get_keyword_hit_series(
        self,
        date: datetime = None,
        words: List[str] = None,
        granularity: str = "hour",
        db_type: str = "news",
    ) -> Dict:
        """
        查询关注词在某日的逐时段命中数（仪表盘「关注词热度曲线」数据源）

        逐词 LIKE 匹配 news_items.title 后统计 rank_history 出现次数；
        crawl_time 为 "HH-MM" 短格式，hour 粒度按前两位分桶。

        Args:
            date: 日期对象，默认为今天
            words: 关注词列表（非空；超过 50 个截断）
            granularity: "hour"（按小时分桶）或 "raw"（按每次采集点）
            db_type: 数据库类型 ("news" 或 "rss")

        Returns:
            {
              "date": "YYYY-MM-DD",
              "granularity": "hour",
              "buckets": ["00:00", "01:00", ...]（升序，全词共用的横轴）,
              "series": [{"word": "关键词", "counts": [3, 0, ...]}]（与 buckets 对齐）
            }

        Raises:
            DataNotFoundError: 数据库不存在
            InvalidParameterError: words 为空或 granularity 未知
        """
        if not words or not [w for w in words if str(w).strip()]:
            raise InvalidParameterError("words 不能为空，须提供至少一个关注词")
        if granularity not in ("hour", "raw"):
            raise InvalidParameterError(f"granularity 仅支持 hour|raw，收到: {granularity}")

        clean_words = [str(w).strip() for w in words if str(w).strip()][:50]
        if not clean_words:
            raise InvalidParameterError("words 不能为空，须提供至少一个关注词")

        def _bucket_expr() -> str:
            if granularity == "hour":
                # "00-47" -> "00"；substr 结果即桶 key
                return "substr(rh.crawl_time, 1, 2)"
            return "rh.crawl_time"

        date_str = self.get_date_folder_name(date)
        bucket_map: Dict[str, Dict[str, int]] = {}  # word -> {bucket_key: hits}
        with self.connect_readonly(date, db_type) as conn:
            for word in clean_words:
                # LIKE 通配符转义，防止用户词含 %/_ 引发全表匹配
                escaped = (
                    word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                rows = conn.execute(
                    f"""
                    SELECT { _bucket_expr() } AS bucket,
                           COUNT(DISTINCT rh.news_item_id) AS hits
                    FROM rank_history rh
                    JOIN news_items ni ON ni.id = rh.news_item_id
                    WHERE ni.title LIKE ? ESCAPE '\\'
                    GROUP BY bucket
                    """,
                    (f"%{escaped}%",),
                ).fetchall()
                bucket_map[word] = {row["bucket"]: row["hits"] for row in rows}

        buckets = sorted({b for counts in bucket_map.values() for b in counts})
        if granularity == "hour":
            buckets = [f"{b}:00" for b in buckets]

        series = []
        for word in clean_words:
            counts = bucket_map[word]
            if granularity == "hour":
                values = [counts.get(b[:2], 0) for b in buckets]
            else:
                values = [counts.get(b, 0) for b in buckets]
            series.append({"word": word, "counts": values})

        return {
            "date": date_str,
            "granularity": granularity,
            "buckets": buckets,
            "series": series,
        }

    def get_last_crawl_time(self, date: datetime = None, db_type: str = "news") -> Optional[str]:
        """
        读取某日最近一次采集时间（crawl_records.crawl_time，"HH-MM" 短格式）

        无论 self.readonly 为何值都以只读 URI打开，
        库不存在/表缺失时返回 None（不抛错、不误建空库）。
        """
        db_path = self._get_db_path(date, db_type)
        if db_path is None:
            return None
        uri = "file:" + urllib.parse.quote(str(db_path.resolve())) + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            try:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT crawl_time FROM crawl_records ORDER BY crawl_time DESC LIMIT 1"
                ).fetchone()
                return row["crawl_time"] if row else None
            finally:
                conn.close()
        except sqlite3.Error:
            return None
