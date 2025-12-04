import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import re

class ConfigWizardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Perplexity-2API 智能配置向导 v4.0 (全能版)")
        self.root.geometry("800x650")
        
        # 样式设置
        style = ttk.Style()
        style.configure("TButton", font=("Microsoft YaHei", 10), padding=5)
        style.configure("TLabel", font=("Microsoft YaHei", 10))
        style.configure("Header.TLabel", font=("Microsoft YaHei", 16, "bold"), foreground="#2563eb")
        style.configure("Info.TLabel", font=("Microsoft YaHei", 9), foreground="#666")
        
        # --- 标题区 ---
        header_frame = ttk.Frame(root, padding="20 20 10 10")
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="🔧 Perplexity-2API 配置控制台", style="Header.TLabel").pack(anchor=tk.W)
        
        # --- 说明区 ---
        info_frame = ttk.LabelFrame(root, text="ℹ️ 支持的数据格式", padding="15")
        info_frame.pack(fill=tk.X, padx=20, pady=5)
        
        info_text = (
            "本工具支持从以下任意格式中提取凭证：\n"
            "1. HAR 文件 (JSON)\n"
            "2. PowerShell 脚本 (Invoke-WebRequest)\n"
            "3. cURL 命令\n"
            "4. 任意包含 Cookie 的文本片段"
        )
        ttk.Label(info_frame, text=info_text, style="Info.TLabel", justify=tk.LEFT).pack(anchor=tk.W)

        # --- 选项卡区 ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Tab 1: 文本粘贴 (推荐)
        self.tab_paste = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_paste, text="📋 粘贴任意内容 (推荐)")
        self.setup_paste_tab()

        # Tab 2: 文件导入
        self.tab_file = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_file, text="📂 导入 HAR 文件")
        self.setup_file_tab()

        # --- 底部状态区 ---
        self.status_frame = ttk.Frame(root, padding="20")
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(self.status_frame, text="就绪", foreground="#888")
        self.status_label.pack(side=tk.LEFT)
        
        self.write_btn = ttk.Button(self.status_frame, text="写入配置到 .env", command=self.write_to_env, state=tk.DISABLED)
        self.write_btn.pack(side=tk.RIGHT)

        # 数据存储
        self.extracted_cookie = None
        self.extracted_ua = None

    def setup_file_tab(self):
        frame = ttk.Frame(self.tab_file)
        frame.pack(fill=tk.X, pady=20)
        self.har_path_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.har_path_var, width=50).pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        ttk.Button(frame, text="浏览文件...", command=self.browse_har).pack(side=tk.LEFT)

    def setup_paste_tab(self):
        ttk.Label(self.tab_paste, text="请在此处粘贴内容 (Ctrl+V)：").pack(anchor=tk.W, pady=(0, 5))
        self.paste_text = scrolledtext.ScrolledText(self.tab_paste, height=10, font=("Consolas", 9))
        self.paste_text.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(self.tab_paste, padding="0 10 0 0")
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="智能解析", command=self.parse_paste_content).pack(side=tk.RIGHT)

    def browse_har(self):
        filename = filedialog.askopenfilename(title="选择 HAR 文件", filetypes=[("HTTP Archive", "*.har"), ("All Files", "*.*")])
        if filename:
            self.har_path_var.set(filename)
            try:
                with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read() # 直接读取为文本
                self.process_text_content(content)
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {str(e)}")

    def parse_paste_content(self):
        content = self.paste_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "请先粘贴内容")
            return
        self.process_text_content(content)

    def process_text_content(self, text):
        """
        全能解析逻辑：尝试 JSON 解析，如果失败则使用正则暴力提取
        """
        self.status_label.config(text="正在分析...", foreground="blue")
        self.root.update()

        cookie = ""
        ua = ""

        # 1. 尝试作为 JSON 解析 (HAR 格式)
        try:
            json_data = json.loads(text)
            cookie, ua = self.extract_from_json(json_data)
        except:
            pass # 不是 JSON，继续尝试其他方法

        # 2. 如果 JSON 没提取到，尝试 PowerShell 格式
        if not cookie:
            cookie = self.extract_from_powershell(text)
        
        # 3. 如果还没提取到，尝试通用正则 (Key=Value 格式)
        if not cookie:
            cookie = self.extract_from_regex(text)

        # 4. 提取 UA (如果还没找到)
        if not ua:
            ua = self.extract_ua_regex(text)

        # 5. 结果处理
        if cookie:
            # 清洗
            cookie = cookie.strip().strip('"').strip("'")
            if not ua:
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            
            self.extracted_cookie = cookie
            self.extracted_ua = ua
            
            preview = cookie[:40] + "..." + cookie[-40:] if len(cookie) > 80 else cookie
            self.status_label.config(text=f"✅ 提取成功! (长度: {len(cookie)})", foreground="green")
            
            msg = (
                f"成功提取凭证！\n\n"
                f"User-Agent: {ua[:30]}...\n"
                f"Cookie: {preview}\n\n"
                f"点击【写入配置】保存。"
            )
            messagebox.showinfo("解析成功", msg)
            self.write_btn.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="❌ 未能识别有效凭证", foreground="red")
            messagebox.showerror("解析失败", "未能从文本中提取到有效的 Perplexity Cookie。\n请确保内容包含 'pplx.visitor-id' 或 'session-token'。")

    def extract_from_json(self, data):
        """递归遍历 JSON 寻找 Cookie"""
        candidates = []
        
        def recursive_search(obj):
            if isinstance(obj, dict):
                if 'name' in obj and 'value' in obj:
                    if str(obj['name']).lower() == 'cookie':
                        candidates.append(obj['value'])
                    elif str(obj['name']).lower() == 'user-agent':
                        self.extracted_ua = obj['value']
                
                for key, value in obj.items():
                    recursive_search(value)
            elif isinstance(obj, list):
                for item in obj:
                    recursive_search(item)

        recursive_search(data)
        
        # 筛选最佳 Cookie
        best_cookie = ""
        for c in candidates:
            if "session-token" in c:
                return c, self.extracted_ua
            if len(c) > len(best_cookie):
                best_cookie = c
        
        return best_cookie, self.extracted_ua

    def extract_from_powershell(self, text):
        """从 PowerShell 脚本中提取 Cookie"""
        # 匹配 $session.Cookies.Add((New-Object System.Net.Cookie("KEY", "VALUE", ...)))
        pattern = r'New-Object System\.Net\.Cookie\("([^"]+)",\s*"([^"]+)"'
        matches = re.findall(pattern, text)
        
        if matches:
            cookie_parts = []
            for key, value in matches:
                cookie_parts.append(f"{key}={value}")
            return "; ".join(cookie_parts)
        return ""

    def extract_from_regex(self, text):
        """通用正则提取"""
        # 尝试匹配整个 Cookie 字符串 (通常在 cURL 或 Raw Header 中)
        # 寻找包含 pplx.visitor-id 的长字符串
        lines = text.splitlines()
        for line in lines:
            if "pplx.visitor-id" in line and "=" in line:
                # 尝试提取 key=value; key=value 格式
                # 简单的启发式：如果行里有 Cookie: 前缀，去掉它
                if "Cookie:" in line:
                    return line.split("Cookie:", 1)[1].strip()
                # 否则，如果这行看起来像 cookie 字符串
                if ";" in line and "=" in line:
                    return line.strip()
        return ""

    def extract_ua_regex(self, text):
        """提取 User-Agent"""
        # 匹配 User-Agent: ...
        match = re.search(r'User-Agent["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # 匹配 PowerShell 的 $session.UserAgent = "..."
        match = re.search(r'\$session\.UserAgent\s*=\s*"([^"]+)"', text)
        if match:
            return match.group(1).strip()
        return ""

    def write_to_env(self):
        env_path = os.path.join(os.getcwd(), '.env')
        
        default_lines = [
            "API_MASTER_KEY=1\n",
            "NGINX_PORT=8091\n",
            "FLARESOLVERR_URL=http://flaresolverr:8191/v1\n"
        ]

        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = default_lines

        new_lines = []
        cookie_written = False
        ua_written = False

        for line in lines:
            if line.strip().startswith("PPLX_COOKIE="):
                new_lines.append(f'PPLX_COOKIE="{self.extracted_cookie}"\n')
                cookie_written = True
            elif line.strip().startswith("PPLX_USER_AGENT="):
                new_lines.append(f'PPLX_USER_AGENT="{self.extracted_ua}"\n')
                ua_written = True
            else:
                new_lines.append(line)
        
        if not cookie_written:
            new_lines.append(f'PPLX_COOKIE="{self.extracted_cookie}"\n')
        if not ua_written:
            new_lines.append(f'PPLX_USER_AGENT="{self.extracted_ua}"\n')

        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            messagebox.showinfo("写入成功", "✅ 配置已更新！\n\n请务必执行以下命令重启服务：\ndocker-compose restart app")
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("写入失败", f"无法写入 .env 文件: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigWizardApp(root)
    root.mainloop()