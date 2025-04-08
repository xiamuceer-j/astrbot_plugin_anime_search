import os
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Share
import aiohttp
from bs4 import BeautifulSoup


@register("anime_search", "xiamuceer-j", "AGE动漫番剧搜索插件", "1.0.0")
class AnimeSearchPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Cookie': 'Hm_lvt_7fdef555dc32f7d31fadd14999021b7b=1743995269; HMACCOUNT=7684B2F2E92F5605; notice=202547; cleanMode=0; Hm_lpvt_7fdef555dc32f7d31fadd14999021b7b=1743995601'
        }
        self.cache_dir = os.path.join(os.getcwd(), 'search_cache')
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, user_id: str) -> str:
        return os.path.join(self.cache_dir, f"{user_id}.json")

    def _save_cache(self, user_id: str, data: dict):
        cache_path = self._get_cache_path(user_id)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_cache(self, user_id: str) -> dict:
        cache_path = self._get_cache_path(user_id)
        if not os.path.exists(cache_path):
            return None
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @filter.command("查番")
    async def search_anime(self, event: AstrMessageEvent):
        '''查询AGE动漫番剧信息\n用法：/查番 番剧名称'''
        args = event.message_str.split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("请输入要查询的番剧名称，例如：/查番 遮天")
            return

        keyword = args[1]
        try:
            html = await self._fetch_search_results(keyword)
            result = self._parse_results(html, keyword)
            anime_list = result['番剧列表']
            total = len(anime_list)

            if total == 0:
                yield event.plain_result(f"未找到与「{keyword}」相关的番剧")
                return

            if total > 2:
                page_size = 2
                total_pages = (total + page_size - 1) // page_size
                cache_data = {
                    "keyword": keyword,
                    "all_results": anime_list,
                    "total_pages": total_pages,
                    "current_page": 1,
                    "page_size": page_size
                }
                self._save_cache(event.get_sender_id(), cache_data)

                yield event.plain_result(f"🔍找到{total}条结果（第1/{total_pages}页）")
                for anime in anime_list[:page_size]:
                    yield event.chain_result(self._build_anime_message(anime))
                yield event.plain_result("输入 /下一页 继续查看，/上一页 返回")
            else:
                yield event.plain_result(f"找到{total}条结果：")
                for anime in anime_list:
                    yield event.chain_result(self._build_anime_message(anime))

        except Exception as e:
            logger.error(f"搜索失败: {str(e)}", exc_info=True)
            yield event.plain_result("番剧查询服务暂时不可用，请稍后再试")

    @filter.command("下一页")
    async def next_page(self, event: AstrMessageEvent):
        '''查看下一页搜索结果'''
        cache = self._load_cache(event.get_sender_id())
        if not cache:
            yield event.plain_result("请先使用【查番】进行搜索")
            return

        current_page = cache['current_page'] + 1
        if current_page > cache['total_pages']:
            yield event.plain_result("已经是最后一页了")
            return

        start = (current_page - 1) * cache['page_size']
        page_data = cache['all_results'][start:start + cache['page_size']]

        cache['current_page'] = current_page
        self._save_cache(event.get_sender_id(), cache)

        yield event.plain_result(f"📖第{current_page}/{cache['total_pages']}页")
        for anime in page_data:
            yield event.chain_result(self._build_anime_message(anime))
        if current_page < cache['total_pages']:
            yield event.plain_result("输入【下一页】继续查看，【上一页】返回")

    @filter.command("上一页")
    async def prev_page(self, event: AstrMessageEvent):
        '''查看上一页搜索结果'''
        cache = self._load_cache(event.get_sender_id())
        if not cache:
            yield event.plain_result("请先使用【查番】进行搜索")
            return

        current_page = cache['current_page'] - 1
        if current_page < 1:
            yield event.plain_result("已经是第一页了")
            return

        start = (current_page - 1) * cache['page_size']
        page_data = cache['all_results'][start:start + cache['page_size']]

        cache['current_page'] = current_page
        self._save_cache(event.get_sender_id(), cache)

        yield event.plain_result(f"📖第{current_page}/{cache['total_pages']}页")
        for anime in page_data:
            yield event.chain_result(self._build_anime_message(anime))
        yield event.plain_result("输入【下一页】继续查看，【上一页】返回")

    def _build_anime_message(self, anime: dict) -> list:
        components = []
        if anime.get('封面图'):
            components.append(Image(url=anime['封面图'], file=anime['封面图']))

        text_components = [
            Plain(text=f"📺 标题：{anime['标题']}"),
            Plain(text=f"⏱ 首播：{anime['首播时间']}"),
            Plain(text=f"📝 简介：{anime['简介'][:100]}..."),
            Plain(text=f"🔗 详情：{anime['详情链接']}")
        ]

        if anime.get('播放链接'):
            text_components.append(Plain(text=f"▶️ 播放：{anime['播放链接']}"))

        return components + text_components

    async def _fetch_search_results(self, keyword: str) -> str:
        url = 'https://www.agedm.org/search'
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url, params={'query': keyword, 'page': 1}) as resp:
                resp.raise_for_status()
                return await resp.text()

    def _parse_results(self, html: str, keyword: str) -> dict:
        soup = BeautifulSoup(html, 'html.parser')
        anime_list = []

        for item in soup.find_all('div', class_='cata_video_item'):
            title_tag = item.find('h5')
            if not title_tag:
                continue

            cover_img = item.find('img', class_='video_thumbs')
            play_btn = item.find('a', class_='btn-danger')

            anime = {
                '标题': title_tag.text.strip(),
                '详情链接': title_tag.a['href'] if title_tag.a else '',
                '首播时间': self._extract_detail(item, '首播时间'),
                '简介': self._extract_detail(item, '简介'),
                '封面图': cover_img['data-original'] if cover_img else '',
                '播放链接': play_btn['href'] if play_btn else ''
            }
            anime_list.append(anime)

        return {'番剧列表': anime_list}

    def _extract_detail(self, soup, field: str) -> str:
        field_span = soup.find('span', string=lambda t: t and t.strip().startswith(f"{field}："))
        if not field_span:
            return ''

        detail_div = field_span.find_parent('div', class_='video_detail_info')
        field_span.extract()
        return detail_div.get_text(strip=True)

    async def terminate(self):
        '''清理资源'''
        pass