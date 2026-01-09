"""
B站视频搜索模块
使用 bilibili-api-python 库进行关键词搜索
"""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def search_bilibili_videos(
    keyword: str,
    count: int = 5,
    order: str = "totalrank"
) -> List[Dict[str, any]]:
    """
    搜索B站视频

    Args:
        keyword: 搜索关键词
        count: 返回结果数量，默认5个
        order: 排序方式
            - "totalrank": 综合排序（默认）
            - "pubdate": 最新发布
            - "click": 最多播放
            - "dm": 最多弹幕

    Returns:
        视频信息列表，每个元素包含:
        - url: 视频链接
        - title: 视频标题
        - bvid: 视频BV号
        - duration: 视频时长（秒）
        - play: 播放量
        - author: UP主名称
    """
    try:
        from bilibili_api import search, sync
    except ImportError:
        logger.error("未安装 bilibili-api-python 库")
        logger.error("请运行: pip install bilibili-api-python")
        return []

    logger.info(f"搜索B站视频: 关键词='{keyword}', 数量={count}, 排序={order}")

    try:
        # 映射排序方式
        order_map = {
            "totalrank": search.OrderVideo.TOTALRANK,  # 综合排序
            "pubdate": search.OrderVideo.PUBDATE,      # 最新发布
            "click": search.OrderVideo.CLICK,          # 最多播放
            "dm": search.OrderVideo.DM                 # 最多弹幕
        }

        order_type = order_map.get(order, search.OrderVideo.TOTALRANK)

        # 异步搜索函数
        async def _search():
            result = await search.search_by_type(
                keyword=keyword,
                search_type=search.SearchObjectType.VIDEO,
                order_type=order_type,
                page=1
            )
            return result

        # 同步调用
        result = sync(_search())

        if not result or 'result' not in result:
            logger.warning(f"搜索无结果: {keyword}")
            return []

        videos = result['result']

        if not videos:
            logger.warning(f"搜索无结果: {keyword}")
            return []

        # 提取视频信息
        video_list = []
        for i, video in enumerate(videos[:count]):
            try:
                bvid = video.get('bvid', '')
                if not bvid:
                    continue

                video_info = {
                    'url': f"https://www.bilibili.com/video/{bvid}",
                    'title': video.get('title', '未知标题'),
                    'bvid': bvid,
                    'duration': _parse_duration(video.get('duration', '0:00')),
                    'play': video.get('play', 0),
                    'author': video.get('author', '未知UP主')
                }
                video_list.append(video_info)

            except Exception as e:
                logger.warning(f"解析视频信息失败: {e}")
                continue

        logger.info(f"搜索完成，找到 {len(video_list)} 个视频")
        return video_list

    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []

def _parse_duration(duration_str: str) -> int:
    """
    解析时长字符串为秒数
    例如: "10:30" -> 630, "1:05:20" -> 3920
    """
    try:
        parts = duration_str.split(':')
        if len(parts) == 2:
            # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            return 0
    except:
        return 0

def format_duration(seconds: int) -> str:
    """
    格式化秒数为时长字符串
    例如: 630 -> "10:30", 3920 -> "1:05:20"
    """
    if seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"

def format_play_count(count: int) -> str:
    """
    格式化播放量
    例如: 10000 -> "1.0万", 1000000 -> "100万"
    """
    if count >= 10000:
        return f"{count / 10000:.1f}万"
    else:
        return str(count)
