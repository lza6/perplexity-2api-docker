import logging
import asyncio
import random
import os
import time
import math
from playwright.async_api import async_playwright
from app.core.config import settings

logger = logging.getLogger(__name__)

class TurnstileSolver:
    async def _human_mouse_move(self, page, start_x, start_y, end_x, end_y):
        """
        模拟人类鼠标移动轨迹 (贝塞尔曲线 + 随机抖动 + 变速)
        """
        steps = random.randint(30, 60) # 步数增加，移动更平滑
        for i in range(steps):
            t = i / steps
            # 贝塞尔曲线插值
            x = start_x + (end_x - start_x) * t
            y = start_y + (end_y - start_y) * t
            
            # 添加正弦波抖动 (模拟手抖)
            x += random.uniform(-2, 2) * math.sin(t * math.pi)
            y += random.uniform(-2, 2) * math.sin(t * math.pi)
            
            await page.mouse.move(x, y)
            
            # 变速移动：中间快，两头慢
            sleep_time = random.uniform(0.001, 0.01)
            if 0.2 < t < 0.8:
                sleep_time /= 2
            await asyncio.sleep(sleep_time)
            
        # 确保最后精准到达
        await page.mouse.move(end_x, end_y)

    async def _apply_stealth(self, page):
        """注入隐身脚本，移除自动化特征"""
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter(parameter);
            };
        """)

    async def get_token(self) -> str:
        logger.info("启动 Playwright (完全拟人化模式)...")
        token_future = asyncio.get_running_loop().create_future()
        
        os.makedirs("/app/debug", exist_ok=True)
        timestamp = int(time.time())
        debug_prefix = f"/app/debug/run_{timestamp}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, # 调试时建议保持 True，依赖截图查看
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1920,1080",
                ]
            )
            
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                record_video_dir="/app/debug",
                record_video_size={"width": 1280, "height": 720}
            )
            
            page = await context.new_page()
            await self._apply_stealth(page)

            # --- 监听 Token ---
            async def handle_request(request):
                if "/api/web/generate-basic" in request.url and request.method == "POST":
                    try:
                        post_data = request.post_data_json
                        if post_data and "turnstile_token" in post_data:
                            token = post_data["turnstile_token"]
                            logger.info(f"🔥🔥🔥 捕获 Token: {token[:20]}...")
                            if not token_future.done():
                                token_future.set_result(token)
                    except:
                        pass
            page.on("request", handle_request)

            try:
                logger.info(f"访问: {settings.TARGET_URL}")
                await page.goto(settings.TARGET_URL, wait_until="domcontentloaded", timeout=60000)

                # 1. 输入 Prompt (保留原有逻辑)
                try:
                    logger.info("寻找输入框...")
                    textarea = await page.wait_for_selector('textarea', state="visible", timeout=15000)
                    
                    # 拟人化点击输入框
                    box = await textarea.bounding_box()
                    if box:
                        await self._human_mouse_move(page, 0, 0, box['x'] + box['width']/2, box['y'] + box['height']/2)
                        await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                    
                    await asyncio.sleep(0.5)
                    await page.keyboard.type("a cyberpunk cat", delay=random.randint(50, 150)) # 随机打字速度
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"输入框操作异常: {e}")

                # 2. 点击生成按钮 (保留原有逻辑)
                try:
                    logger.info("点击生成按钮...")
                    btn = await page.wait_for_selector('button:has-text("Generate")', state="visible", timeout=5000)
                    
                    # 拟人化点击按钮
                    box = await btn.bounding_box()
                    if box:
                        await self._human_mouse_move(page, 500, 500, box['x'] + box['width']/2, box['y'] + box['height']/2)
                        await asyncio.sleep(0.2)
                        await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                    else:
                        await btn.click()
                except:
                    logger.warning("未找到生成按钮")

                # 3. 验证码处理 (核心升级：反应时间 + 悬停 + 物理点击)
                logger.info("进入验证码处理流程...")
                
                start_time = time.time()
                clicked = False
                
                while not token_future.done():
                    if time.time() - start_time > 60:
                        logger.error("验证超时")
                        break
                    
                    # 检查是否有 Error
                    if await page.get_by_text("Error").is_visible():
                        logger.error("页面显示 Error，刷新重试...")
                        await page.reload()
                        clicked = False
                        start_time = time.time()
                        await asyncio.sleep(3)
                        continue

                    # 寻找 Cloudflare iframe 元素 (获取其在主页面的坐标)
                    iframe_element = await page.query_selector("iframe[src*='challenges.cloudflare.com']")
                    
                    if iframe_element:
                        box = await iframe_element.bounding_box()
                        # 确保 iframe 已经渲染出尺寸
                        if box and box['width'] > 0 and box['height'] > 0:
                            if not clicked:
                                logger.info(f"发现验证码 iframe，坐标: ({box['x']}, {box['y']})")
                                await page.screenshot(path=f"{debug_prefix}_found.png")

                                # --- 关键步骤 1: 反应时间 (Reaction Time) ---
                                reaction_time = random.uniform(1.5, 3.0)
                                logger.info(f"模拟人类反应时间: 发呆 {reaction_time:.2f} 秒...")
                                await asyncio.sleep(reaction_time)

                                # --- 关键步骤 2: 计算目标坐标 (左侧复选框位置 + 随机偏移) ---
                                # Turnstile 宽约300，高约65。复选框在左边。
                                target_x = box['x'] + 30 + random.uniform(-5, 5)
                                target_y = box['y'] + (box['height'] / 2) + random.uniform(-5, 5)
                                
                                # --- 关键步骤 3: 拟人化移动 (Human Move) ---
                                logger.info(f"移动鼠标至: ({target_x:.1f}, {target_y:.1f})")
                                # 假设当前鼠标在屏幕中间附近，或者上一次点击的位置
                                await self._human_mouse_move(page, 960, 540, target_x, target_y)

                                # --- 关键步骤 4: 悬停 (Hover) ---
                                hover_time = random.uniform(0.3, 0.8)
                                logger.info(f"悬停确认: {hover_time:.2f} 秒...")
                                await asyncio.sleep(hover_time)

                                # --- 关键步骤 5: 物理点击 (Physical Click) ---
                                logger.info("执行物理点击 (Down -> Sleep -> Up)...")
                                await page.mouse.down()
                                await asyncio.sleep(random.uniform(0.08, 0.15)) # 模拟按键时长
                                await page.mouse.up()
                                
                                clicked = True
                                logger.info("点击完成，等待验证通过...")
                                await page.screenshot(path=f"{debug_prefix}_clicked.png")
                                
                            else:
                                # 已经点过了，正在等待结果
                                pass
                        else:
                            # iframe 存在但还没展开
                            pass
                    else:
                        # 还没找到 iframe
                        pass

                    # 如果点击后 20 秒还没反应，重置状态重试
                    if clicked and (time.time() - start_time) % 20 < 1:
                         logger.info("等待过久，重置状态准备重试...")
                         clicked = False

                    await asyncio.sleep(1)

                if token_future.done():
                    return token_future.result()
                return ""

            except Exception as e:
                logger.error(f"流程出错: {e}")
                await page.screenshot(path=f"{debug_prefix}_error.png")
                return ""
            finally:
                await context.close()
                await browser.close()
                try:
                    video_files = [f for f in os.listdir("/app/debug") if f.endswith(".webm")]
                    if video_files:
                        latest = max([os.path.join("/app/debug", f) for f in video_files], key=os.path.getctime)
                        os.rename(latest, f"{debug_prefix}_recording.webm")
                except: pass