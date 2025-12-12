"""
Cookie 管理与登录模块
"""
import os
import time
import logging


class CookieManager:
    """Cookie 管理器，支持本地文件读取和浏览器登录获取"""
    
    def __init__(self, cookie_file: str = 'cookie.txt'):
        """
        初始化 Cookie 管理器
        
        Args:
            cookie_file: Cookie 文件路径
        """
        self.cookie_file = cookie_file
        self._cookies = None
    
    def cookie_exists(self) -> bool:
        """检查本地 Cookie 文件是否存在"""
        return os.path.exists(self.cookie_file)
    
    def read_cookie(self) -> str:
        """
        读取 Cookie 文件内容
        
        Returns:
            Cookie 字符串
            
        Raises:
            FileNotFoundError: Cookie 文件不存在
        """
        if not self.cookie_exists():
            raise FileNotFoundError(f"未找到 {self.cookie_file}，请先登录获取 Cookie")
        
        with open(self.cookie_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    
    def parse_cookie(self) -> dict:
        """
        解析 Cookie 字符串为字典
        
        Returns:
            Cookie 字典
        """
        cookie_text = self.read_cookie()
        cookie_items = [item.strip().split('=', 1) for item in cookie_text.split(';') if item]
        return {k.strip(): v.strip() for k, v in cookie_items}
    
    def save_cookie(self, cookies: dict) -> None:
        """
        保存 Cookie 到文件
        
        Args:
            cookies: Cookie 字典
        """
        cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
        with open(self.cookie_file, 'w', encoding='utf-8') as f:
            f.write(cookie_str)
        logging.info(f"Cookie 已保存到 {self.cookie_file}")
    
    def _try_launch_browser(self):
        """
        尝试启动可用的浏览器
        
        按优先级尝试：Edge -> Chrome -> Safari (仅 macOS)
        
        Returns:
            (driver, browser_name) 或 (None, None)
        """
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        import platform
        
        system = platform.system()
        browsers_to_try = []
        
        # macOS 优先使用 Edge（因为用户有 Edge）
        if system == 'Darwin':
            browsers_to_try = [
                ('edge', 'Microsoft Edge'),
                ('chrome', 'Google Chrome'),
                ('safari', 'Safari')
            ]
        else:
            browsers_to_try = [
                ('chrome', 'Google Chrome'),
                ('edge', 'Microsoft Edge')
            ]
        
        for browser_type, browser_name in browsers_to_try:
            try:
                logging.info(f"尝试启动 {browser_name}...")
                
                if browser_type == 'edge':
                    from selenium.webdriver.edge.options import Options as EdgeOptions
                    options = EdgeOptions()
                    
                    if system == 'Darwin':
                        options.add_argument('--no-sandbox')
                        options.add_argument('--disable-dev-shm-usage')
                        options.add_argument('--disable-gpu')
                    else:
                        options.add_argument('--start-maximized')
                    if system == 'Darwin':
                        options.add_argument('--disable-blink-features=AutomationControlled')
                        options.add_experimental_option('excludeSwitches', ['enable-automation'])
                        options.add_experimental_option('useAutomationExtension', False)
                    else:
                        # Windows 简化配置，优先保证能启动
                        options.add_experimental_option("detach", True)
                        options.add_argument('--start-maximized')
                    
                    driver = webdriver.Edge(options=options)
                    logging.info(f"✅ 成功启动 {browser_name}")
                    return driver, browser_name
                    
                elif browser_type == 'chrome':
                    from selenium.webdriver.chrome.options import Options as ChromeOptions
                    options = ChromeOptions()
                    
                    if system == 'Darwin':
                        options.add_argument('--no-sandbox')
                        options.add_argument('--disable-dev-shm-usage')
                        options.add_argument('--disable-gpu')
                    if system == 'Darwin':
                        options.add_argument('--disable-blink-features=AutomationControlled')
                        options.add_experimental_option('excludeSwitches', ['enable-automation'])
                        options.add_experimental_option('useAutomationExtension', False)
                    else:
                        # Windows 简化配置，优先保证能启动
                        options.add_experimental_option("detach", True)
                        options.add_argument('--start-maximized')
                    
                    driver = webdriver.Chrome(options=options)
                    logging.info(f"✅ 成功启动 {browser_name}")
                    return driver, browser_name
                    
                elif browser_type == 'safari':
                    # Safari 不需要太多选项
                    driver = webdriver.Safari()
                    logging.info(f"✅ 成功启动 {browser_name}")
                    return driver, browser_name
                    
            except WebDriverException as e:
                logging.warning(f"❌ {browser_name} 启动失败: {str(e)[:100]}")
                continue
            except Exception as e:
                logging.warning(f"❌ {browser_name} 启动失败: {str(e)[:100]}")
                continue
        
        return None, None
    
    def login_via_browser(self, timeout: int = 300) -> bool:
        """
        通过浏览器登录网易云音乐获取 Cookie
        
        自动检测并使用可用的浏览器（Edge/Chrome/Safari）
        
        Args:
            timeout: 登录超时时间（秒），默认 5 分钟
            
        Returns:
            是否登录成功
        """
        try:
            from selenium import webdriver
            from selenium.common.exceptions import WebDriverException
        except ImportError as e:
            error_msg = "请先安装 selenium: pip3 install selenium"
            logging.error(error_msg)
            raise ImportError(error_msg) from e
        
        import platform
        
        logging.info("正在打开浏览器，请登录网易云音乐...")
        
        driver = None
        browser_name = None
        
        try:
            # 尝试启动浏览器
            driver, browser_name = self._try_launch_browser()
            
            if driver is None:
                raise Exception(
                    "无法启动任何浏览器。请确保已安装以下浏览器之一：\n"
                    "- Microsoft Edge (推荐)\n"
                    "- Google Chrome\n"
                    f"{'- Safari (macOS 自带)' if platform.system() == 'Darwin' else ''}\n"
                    "\n然后运行: pip3 install --upgrade selenium"
                )
            
            logging.info(f"{browser_name} 已启动，正在加载网易云音乐...")
            driver.get("https://music.163.com/")
            logging.info(f"页面加载完成，请在 {browser_name} 中登录...")
            
            start_time = time.time()
            logged_in = False
            last_check_time = 0
            
            # 等待用户登录，检测 MUSIC_U Cookie
            while time.time() - start_time < timeout:
                try:
                    current_time = time.time()
                    
                    # 每 2 秒检查一次，避免频繁检查
                    if current_time - last_check_time < 2:
                        time.sleep(0.5)
                        continue
                    
                    last_check_time = current_time
                    
                    cookies = driver.get_cookies()
                    cookie_dict = {c['name']: c['value'] for c in cookies}
                    
                    # MUSIC_U 是登录成功后的关键 Cookie
                    if 'MUSIC_U' in cookie_dict and cookie_dict['MUSIC_U']:
                        logging.info("检测到登录成功！")
                        self.save_cookie(cookie_dict)
                        self._cookies = cookie_dict
                        logged_in = True
                        break
                    
                    # 每 30 秒输出一次等待日志
                    elapsed = int(current_time - start_time)
                    if elapsed > 0 and elapsed % 30 == 0:
                        remaining = int(timeout - elapsed)
                        logging.info(f"等待登录中... (剩余 {remaining} 秒)")
                
                except Exception as e:
                    logging.warning(f"检查登录状态时出错: {e}")
                    time.sleep(2)
            
            if not logged_in:
                logging.warning("登录超时，未检测到登录")
                return False
            
            logging.info("登录流程完成")
            return True
            
        except Exception as e:
            error_msg = f"浏览器登录失败：{str(e)}"
            logging.error(error_msg)
            # 将错误信息传递给调用者
            raise Exception(error_msg) from e
        finally:
            if driver:
                try:
                    logging.info("正在关闭浏览器...")
                    driver.quit()
                    logging.info("浏览器已关闭")
                except Exception as e:
                    logging.warning(f"关闭浏览器时出错: {e}")
    
    def get_cookies(self) -> dict:
        """
        获取 Cookie，优先从缓存获取
        
        Returns:
            Cookie 字典
        """
        if self._cookies:
            return self._cookies
        
        if self.cookie_exists():
            self._cookies = self.parse_cookie()
            return self._cookies
        
        raise FileNotFoundError("Cookie 不存在，请先登录")
    
    def clear_cache(self) -> None:
        """清除 Cookie 缓存"""
        self._cookies = None
    
    def delete_cookie_file(self) -> None:
        """删除本地 Cookie 文件"""
        if self.cookie_exists():
            os.remove(self.cookie_file)
            logging.info(f"已删除 {self.cookie_file}")
        self.clear_cache()
