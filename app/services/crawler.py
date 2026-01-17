from crawl4ai import AsyncWebCrawler
from app.core.config import settings
import logging
import re

logger = logging.getLogger(__name__)

# 全局爬虫实例，避免重复创建浏览器
_crawler_instance = None
_playwright_browser = None

class CrawlerService:
    
    @staticmethod
    async def get_crawler():
        """获取或创建全局爬虫实例"""
        global _crawler_instance
        if _crawler_instance is None:
            _crawler_instance = AsyncWebCrawler(verbose=False, headless=settings.CRAWL_HEADLESS)
            await _crawler_instance.start()
        return _crawler_instance
    
    @staticmethod
    async def fetch_page(url: str) -> str:
        """
        Fetches a page and returns its content as Markdown.
        Uses optimized Playwright settings.
        """
        # gov.uz 网站使用专门的 Playwright 爬取（低内存模式下使用普通爬虫）
        if 'gov.uz' in url and not settings.LOW_MEMORY_MODE:
            return await CrawlerService._fetch_with_playwright(url)
        
        try:
            crawler = await CrawlerService.get_crawler()
            
            result = await crawler.arun(
                url=url,
                bypass_cache=True,
                wait_until="domcontentloaded",
                page_timeout=30000,
                excluded_tags=['nav', 'footer', 'header', 'aside', 'script', 'style', 'img', 'video', 'canvas', 'svg', 'form', 'iframe', 'button', 'input'],
                word_count_threshold=20
            )
            if not result.success:
                logger.error(f"Failed to crawl {url}: {result.error_message}")
                return ""
            
            markdown = result.markdown
            
            # 商务部网站特殊处理：提取文章正文
            if 'mofcom.gov.cn' in url and '/art/' in url:
                markdown = CrawlerService._extract_mofcom_article(markdown)
            
            return markdown
        except Exception as e:
            logger.error(f"Exception during crawl: {str(e)}")
            return ""
    
    @staticmethod
    async def _fetch_with_playwright(url: str) -> str:
        """
        使用 Playwright 直接爬取动态加载的网站
        """
        global _playwright_browser
        
        try:
            from playwright.async_api import async_playwright
            import html2text
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=settings.CRAWL_HEADLESS,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US'
                )
                page = await context.new_page()
                
                print(f"[Playwright] Navigating to {url}")
                
                # 使用 domcontentloaded 而不是 networkidle，避免超时
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                except Exception as nav_err:
                    print(f"[Playwright] Navigation warning: {nav_err}")
                    # 即使超时也继续尝试获取内容
                
                # 等待内容加载 - 增加等待时间
                await page.wait_for_timeout(8000)
                
                # 尝试等待新闻列表或文章内容出现
                try:
                    await page.wait_for_selector('article, .news-item, .news-list, .content, main, .article-content, .news-content, body', timeout=15000)
                except Exception:
                    print(f"[Playwright] Selector wait timeout, continuing anyway")
                
                # 滚动页面触发懒加载
                try:
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
                    await page.wait_for_timeout(3000)
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(3000)
                except Exception:
                    pass
                
                # gov.uz 特殊处理：尝试提取文章主体内容
                html_content = ""
                if 'gov.uz' in url and '/news/view/' in url:
                    try:
                        # 尝试获取文章主体区域
                        article_content = await page.evaluate('''() => {
                            // 尝试多种选择器找到文章内容
                            const selectors = [
                                '.news-content',
                                '.article-content', 
                                '.content-body',
                                'article',
                                '.main-content',
                                '[class*="news"]',
                                '[class*="article"]'
                            ];
                            
                            for (const sel of selectors) {
                                const el = document.querySelector(sel);
                                if (el && el.innerText.length > 500) {
                                    return el.outerHTML;
                                }
                            }
                            
                            // 如果找不到特定容器，获取整个 body
                            return document.body.outerHTML;
                        }''')
                        if article_content:
                            html_content = article_content
                    except Exception:
                        pass
                
                if not html_content:
                    html_content = await page.content()
                
                await browser.close()
                
                # 转换为 Markdown
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0
                markdown = h.handle(html_content)
                
                # gov.uz 后处理：只对文章页清理导航噪音
                if 'gov.uz' in url and '/news/view/' in url:
                    markdown = CrawlerService._clean_gov_uz_content(markdown)
                
                print(f"[Playwright] Crawled {len(markdown)} chars from {url}")
                return markdown
                
        except Exception as e:
            logger.error(f"[Playwright] Exception: {str(e)}")
            return ""
    
    @staticmethod
    def _clean_gov_uz_content(markdown: str) -> str:
        """
        清理 gov.uz 页面的导航噪音，提取文章正文
        """
        lines = markdown.split('\n')
        
        # 查找文章开始位置（通常是 ## 标题 + 日期）
        article_start = -1
        for i, line in enumerate(lines):
            # 查找文章标题行（## 开头，后面几行有日期）
            if line.startswith('## ') and not any(nav in line.lower() for nav in ['site map', 'hotline', 'about', 'contact']):
                # 检查后面几行是否有日期
                for j in range(i, min(i+5, len(lines))):
                    if re.search(r'\d{4}-\d{2}-\d{2}', lines[j]):
                        article_start = i
                        break
                if article_start >= 0:
                    break
        
        if article_start < 0:
            # 备选：查找 "Dear friends" 或类似开头
            for i, line in enumerate(lines):
                if 'Dear friends' in line or 'Dear colleagues' in line or '**Dear' in line:
                    article_start = max(0, i - 5)  # 往前几行可能有标题
                    break
        
        if article_start >= 0:
            # 从文章开始位置截取
            content_lines = lines[article_start:]
            
            # 查找文章结束位置（通常是页脚导航）
            article_end = len(content_lines)
            for i, line in enumerate(content_lines):
                # 检测页脚开始
                if any(footer in line.lower() for footer in ['#### site map', '### hotline', '### - about', 'copyright', '© 20']):
                    article_end = i
                    break
            
            content_lines = content_lines[:article_end]
            return '\n'.join(content_lines)
        
        return markdown
    
    @staticmethod
    def _extract_mofcom_article(markdown: str) -> str:
        """
        从商务部网站提取文章正文，去除导航噪音
        """
        # 查找文章元信息（来源、日期）
        source_match = re.search(r'来源[：:]\s*([^\n]+)', markdown)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2})', markdown)
        
        if source_match:
            start_idx = source_match.end()
            if date_match and date_match.start() > source_match.end():
                start_idx = date_match.end()
            
            content = markdown[start_idx:]
            
            # 截断到常见的页脚/广告标记
            end_markers = [
                '### 驻在国', '### 投资合作', '### 关于我们', 
                '智能问答', '网站管理', 
                '![](https://www.mofcom',  # 广告图片
                '![](https://www.ciie',    # 进博会图片
                '* [首页](https://www.ciie',  # 进博会广告
                '* [参会报名]',  # 广交会广告
                '[首页](https://www.ciie',
            ]
            
            min_idx = len(content)
            for marker in end_markers:
                idx = content.find(marker)
                if idx > 0 and idx < min_idx:
                    min_idx = idx
            
            if min_idx < len(content):
                content = content[:min_idx]
            
            content = content.strip()
            if len(content) > 30:
                source = source_match.group(1).strip() if source_match else "商务部"
                source = re.sub(r'\s*类型[：:].+', '', source)
                date = date_match.group(1) if date_match else ""
                
                return f"""来源: {source}
日期: {date}

{content}
"""
        
        return markdown

crawler_service = CrawlerService()
