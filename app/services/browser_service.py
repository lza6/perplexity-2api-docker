import logging
import asyncio
import os
import time
import random
import re
from typing import Dict
from playwright.async_api import async_playwright, Page
from app.core.config import settings

logger = logging.getLogger(__name__)

class BrowserService:
    def __init__(self):
        self.cached_cookies: Dict[str, str] = {}
        self.cached_user_agent: str = settings.PPLX_USER_AGENT
        self.last_refresh_time = 0
        self.refresh_interval = 300 # 5分钟内不重复刷新

    async def initialize_session(self):
        """初始化：解析 .env 中的 Cookie"""
        logger.info("🚀 正在初始化浏览器服务...")
        initial_cookies_list = settings.get_initial_cookies_dict()
        self.cached_cookies = {c["name"]: c["value"] for c in initial_cookies_list}
        
        # 启动时尝试预热
        try:
            await self.refresh_context(force=True)
        except Exception as e:
            logger.error(f"❌ 初始预热失败: {e}")

    async def _handle_cf_challenge(self, page: Page):
        """
        [核心逻辑] 专门处理 Cloudflare 盾牌 (无截图版)
        """
        try:
            title = await page.title()
            if "Just a moment" not in title and "Cloudflare" not in title:
                return

            logger.warning(f"🛡️ 检测到 Cloudflare 盾牌 (标题: {title})，正在尝试自动突破...")
            
            for i in range(10):
                # 查找所有包含 challenges 的 iframe
                frames = page.frames
                challenge_frame = next((f for f in frames if "challenges" in f.url), None)

                if challenge_frame:
                    logger.info("⚔️ 发现验证框，正在模拟人工点击...")
                    
                    element = await page.query_selector("iframe[src*='challenges']")
                    if element:
                        box = await element.bounding_box()
                        if box:
                            x = box["x"] + (box["width"] / 2) + random.randint(-10, 10)
                            y = box["y"] + (box["height"] / 2) + random.randint(-5, 5)

                            await page.mouse.move(x, y, steps=random.randint(10, 20))
                            await asyncio.sleep(random.uniform(0.2, 0.5))
                            await page.mouse.down()
                            await asyncio.sleep(random.uniform(0.05, 0.15))
                            await page.mouse.up()
                            
                            logger.info("✅ 点击完成，等待跳转...")
                            try:
                                await page.wait_for_load_state("networkidle", timeout=15000)
                            except:
                                pass
                            return
                await asyncio.sleep(1)
            
            logger.warning("⚠️ 未找到验证框，尝试等待自动跳转...")

        except Exception as e:
            logger.error(f"❌ 处理盾牌时出错: {e}")

    def _update_env_file(self, new_cookies: Dict[str, str]):
        """
        [持久化] 将最新的 Cookie 写回 .env 文件
        """
        try:
            # 构造 Cookie 字符串
            cookie_str = "; ".join([f"{k}={v}" for k, v in new_cookies.items()])
            env_path = ".env" # 容器内路径，映射到宿主机
            
            if not os.path.exists(env_path):
                return

            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            new_lines = []
            updated = False
            for line in lines:
                if line.startswith("PPLX_COOKIE="):
                    new_lines.append(f'PPLX_COOKIE="{cookie_str}"\n')
                    updated = True
                else:
                    new_lines.append(line)
            
            if not updated:
                new_lines.append(f'PPLX_COOKIE="{cookie_str}"\n')

            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            logger.info("💾 最新 Cookie 已自动保存到 .env 文件 (持久化成功)")
            
        except Exception as e:
            logger.error(f"❌ 保存 Cookie 到文件失败: {e}")

    async def refresh_context(self, force=False):
        """
        启动浏览器，访问页面，过盾，更新 Cookie
        """
        if not force and (time.time() - self.last_refresh_time < self.refresh_interval) and self.cached_cookies:
            return True

        logger.info("🔄 启动浏览器进行会话保活/续期...")
        
        async with async_playwright() as p:
            # 移除 record_video_dir，不录屏
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = await browser.new_context(
                user_agent=self.cached_user_agent,
                viewport={"width": 1280, "height": 720}
            )

            if self.cached_cookies:
                cookie_list = [
                    {"name": k, "value": v, "url": "https://www.perplexity.ai"}
                    for k, v in self.cached_cookies.items()
                ]
                try:
                    await context.add_cookies(cookie_list)
                except Exception:
                    pass

            page = await context.new_page()

            try:
                await page.goto(settings.TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                
                # 处理盾牌
                await self._handle_cf_challenge(page)

                # 检查结果
                title = await page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    logger.error("❌ 过盾失败，仍在盾牌页面。")
                    return False

                # 提取并更新 Cookie
                cookies = await context.cookies()
                new_cookies = {c["name"]: c["value"] for c in cookies}
                
                if "pplx.visitor-id" in new_cookies:
                    self.cached_cookies = new_cookies
                    self.last_refresh_time = time.time()
                    logger.info(f"✅ Cookie 刷新成功! 数量: {len(self.cached_cookies)}")
                    
                    # [关键] 自动写回文件
                    self._update_env_file(new_cookies)
                    
                    return True
                else:
                    logger.error("❌ 未找到关键 Cookie，可能验证未通过。")
                    return False

            except Exception as e:
                logger.error(f"❌ 浏览器操作异常: {e}")
                return False
            finally:
                await context.close()
                await browser.close()

    def get_headers(self) -> Dict[str, str]:
        return {
            "Host": "www.perplexity.ai",
            "User-Agent": self.cached_user_agent,
            "Accept": "text/event-stream",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "Origin": settings.TARGET_URL,
            "Referer": f"{settings.TARGET_URL}/search/new",
            "Priority": "u=1, i",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-perplexity-request-reason": "perplexity-query-state-provider"
        }

    def get_cookies(self) -> Dict[str, str]:
        return self.cached_cookies