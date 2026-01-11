import json
import re
import yaml
import os
from urllib.parse import urlparse
from openai import AsyncOpenAI
from app.core.config import settings

# Initialize Client - DeepSeek compatible endpoint
client = AsyncOpenAI(
    api_key=settings.DEEPSEEK_API_KEY or "sk-placeholder", 
    base_url=settings.DEEPSEEK_BASE_URL
)

# 使用配置中的模型
MODEL = settings.DEEPSEEK_MODEL

# ============================================================
# 站点提示词配置 - 从 YAML 文件加载
# ============================================================
SITE_PROMPTS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'site_prompts.yaml')
_site_prompts_cache = {}
_site_prompts_mtime = 0

def load_site_prompts() -> dict:
    """加载站点提示词配置，支持热加载"""
    global _site_prompts_cache, _site_prompts_mtime
    
    try:
        # 检查文件是否更新
        current_mtime = os.path.getmtime(SITE_PROMPTS_FILE)
        if current_mtime != _site_prompts_mtime:
            with open(SITE_PROMPTS_FILE, 'r', encoding='utf-8') as f:
                _site_prompts_cache = yaml.safe_load(f) or {}
            _site_prompts_mtime = current_mtime
            print(f"[Config] Loaded site prompts: {list(_site_prompts_cache.keys())}")
        return _site_prompts_cache
    except Exception as e:
        print(f"[Config] Failed to load site_prompts.yaml: {e}")
        return get_default_prompts()

def get_default_prompts() -> dict:
    """返回默认配置（当YAML加载失败时使用）"""
    return {
        "_default": {
            "name": "通用",
            "link_hints": "优先提取包含 /news/、/article/、年份数字的链接，忽略导航和javascript链接",
            "content_hints": "识别文章标题、发布日期、正文内容"
        }
    }

def get_site_config(url: str) -> dict:
    """根据URL获取对应的站点配置"""
    prompts = load_site_prompts()
    
    try:
        domain = urlparse(url).netloc.lower()
        domain = re.sub(r'^www\.', '', domain)
        
        # 精确匹配
        if domain in prompts:
            return prompts[domain]
        
        # 主域名匹配（如 lk.mofcom.gov.cn -> mofcom.gov.cn）
        parts = domain.split('.')
        for i in range(len(parts)):
            parent_domain = '.'.join(parts[i:])
            if parent_domain in prompts:
                return prompts[parent_domain]
        
        return prompts.get("_default", get_default_prompts()["_default"])
    except:
        return prompts.get("_default", get_default_prompts()["_default"])


def get_filter_keywords() -> list:
    """获取过滤关键字列表"""
    prompts = load_site_prompts()
    keywords_config = prompts.get("_keywords", {})
    
    all_keywords = []
    all_keywords.extend(keywords_config.get("chinese", []))
    all_keywords.extend(keywords_config.get("english", []))
    
    # 转小写用于匹配
    return [k.lower() for k in all_keywords]


def check_keyword_relevance(title: str, summary: str) -> bool:
    """检查标题或摘要是否包含相关关键字"""
    keywords = get_filter_keywords()
    if not keywords:
        return True  # 没有配置关键字则不过滤
    
    text = (title + " " + summary).lower()
    return any(kw in text for kw in keywords)


class AIEngine:
    
    @staticmethod
    async def analyze_relevance(text: str) -> dict:
        """
        Uses DeepSeek to check if text is relevant to Strategic Risk.
        """
        if not text:
            return {"value_level": "Low", "reason": "Empty text"}
            
        system_prompt = """
        You are a Strategic Risk Analyst. Analyze the input text and determine if it contains high-value strategic risk intelligence (e.g. policy changes, geopolitical shifts, economic laws). 
        Return JSON: {"value_level": "High" or "Low", "reason": "short explanation"}
        """
        
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text[:4000]} # Truncate for Lite check
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"value_level": "Low", "reason": str(e)}

    @staticmethod
    async def extract_intelligence(text: str, url: str = "") -> dict:
        """
        Uses DeepSeek to extract structured intelligence.
        Uses site-specific hints for better extraction.
        """
        # 获取站点特定配置
        site_config = get_site_config(url) if url else SITE_PROMPTS["_default"]
        content_hints = site_config.get("content_hints", "")
        
        system_prompt = f"""
你是一个数据提取专家和风险分析师。
我将提供从网页爬取的原始 Markdown 文本，其中包含噪音（导航菜单、广告、侧边栏）。

{content_hints}

【你的任务】
提取关键情报并输出结构化 JSON。

【关键规则】
1. **内容清洗**：移除所有导航、"相关新闻"、"订阅"、广告和页脚
2. **正文保留**：必须在 'main_content' 字段返回完整、未删节的文章正文。不要总结正文内容
3. **语言处理**：'main_content' 保持原文语言，'summary' 和 'risk_hint' 用中文
4. **日期解析**：注意不同地区的日期格式！
   - "08/01/2026" 或 "08/01/26" 表示 2026年1月8日（日/月/年 或 月/日/年格式，根据上下文判断）
   - "January 8, 2026" 表示 2026年1月8日
   - "2026-01-08" 表示 2026年1月8日
   - 输出必须是 YYYY-MM-DD 格式

【输出 JSON 格式】
{{
    "title": "文章原标题",
    "title_zh": "文章标题的中文翻译（如原标题已是中文则保持不变）",
    "publish_date": "YYYY-MM-DD（如无则为 null，注意正确解析日期格式）",
    "author": "作者名（如无则为 Unknown）",
    "content_type": "News/Policy/Regulation/Analysis",
    "keywords": ["标签1", "标签2", "标签3"],
    "summary": "中文摘要（100字以内）",
    "risk_hint": "中文风险提示（一句话分析战略风险含义）",
    "main_content": "完整清洗后的文章正文（保留 Markdown 格式）",
    "translated_content": "'main_content' 的高质量中文翻译（保持 markdown 结构）",
    "confidence": 0.0-1.0
}}
"""
        
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text[:16000]}  # 增加到16000字符以支持长文章
                ],
                response_format={"type": "json_object"},
                timeout=120  # 增加超时时间
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Extraction Error: {e}")
            return {}

    @staticmethod
    async def detect_and_extract_links(markdown: str, url: str) -> dict:
        """
        Analyzes page type and extracts relevant article links if it's a list page.
        Uses site-specific prompts for better accuracy.
        """
        import re
        
        # 获取站点特定配置
        site_config = get_site_config(url)
        site_name = site_config.get("name", "通用")
        link_hints = site_config.get("link_hints", "")
        
        # 预处理：提取所有链接
        all_links = re.findall(r'\[([^\]]*)\]\((https?://[^)]+)\)', markdown)
        filtered_links = [(text, href) for text, href in all_links 
                          if 'javascript' not in href and '#' not in href]
        
        # 特殊处理：gov.uz 网站 - 提取相对路径的新闻链接
        if 'gov.uz' in url:
            # 提取相对路径链接
            relative_links = re.findall(r'\[([^\]]*)\]\((/en/[^)]+/news/view/\d+)\)', markdown)
            if relative_links:
                news_links = [f"https://gov.uz{href}" for text, href in relative_links]
                # 去重
                news_links = list(dict.fromkeys(news_links))
                print(f"[{site_name}] Found {len(news_links)} news links")
                return {
                    "page_type": "list",
                    "links": news_links[:10],
                    "reason": f"乌兹别克斯坦政府网站，提取到 {len(news_links)} 个新闻链接"
                }
        
        # 特殊处理：商务部网站 - 直接提取子域名的文章链接
        if 'mofcom.gov.cn' in url:
            subdomain_art_links = [
                href.split('"')[0].strip()  # 去掉可能的引号后缀和空格
                for text, href in filtered_links 
                if 'mofcom.gov.cn' in href 
                and 'www.mofcom' not in href 
                and '/art/' in href
            ]
            # 清理链接
            subdomain_art_links = [link for link in subdomain_art_links if link.endswith('.html')]
            if subdomain_art_links:
                print(f"[{site_name}] Found {len(subdomain_art_links)} subdomain article links")
                return {
                    "page_type": "list",
                    "links": subdomain_art_links[:15],
                    "reason": f"商务部境外风险预警页面，提取到 {len(subdomain_art_links)} 个子域名文章链接"
                }
        
        # 构建链接列表文本供 AI 分析
        links_text = "\n".join([f"- {text}: {href}" for text, href in filtered_links[:100]])
        
        system_prompt = f"""
你是一个网页结构分析专家。分析给定的网页内容，判断页面类型并提取文章链接。

【目标URL】{url}
【站点】{site_name}

{link_hints}

【页面类型判断规则】
1. **列表页特征**：
   - URL 较短，包含 index、list、category、section 等
   - 页面有多个重复结构的链接块
   - 包含分页元素

2. **文章页特征**：
   - URL 较长，包含文章标题slug或唯一ID
   - 有大段连续的正文内容
   - 有明确的标题、日期、作者

【链接提取规则 - 重要！】
1. **只提取文章链接**：
   - 链接指向具体文章/新闻/公告
   - 链接URL通常包含日期、ID或标题slug
   
2. **必须忽略的链接**：
   - javascript:; 或 javascript:void(0)
   - # 开头的锚点链接
   - 导航菜单链接（首页、关于我们、联系方式等）
   - 登录、注册、订阅链接
   - 社交媒体分享链接
   - 分类/标签/作者页面链接
   - 图片/视频/下载链接

3. **提取数量**：最多提取 5-10 个最相关的文章链接

【输出格式】
返回 JSON：
{{
    "page_type": "list" 或 "article",
    "links": ["完整URL1", "完整URL2", ...],
    "reason": "简短说明判断依据"
}}

注意：links 数组中的URL必须是完整的（包含协议和域名），如果原文是相对路径，请补全。
"""
        
        try:
            # 构建用户消息：包含页面摘要和完整链接列表
            user_content = f"""请分析以下网页：

【页面URL】{url}

【页面中提取的所有链接】（已过滤无效链接）
{links_text}

【页面内容摘要】
{markdown[:3000]}
"""
            
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                timeout=60  # 60秒超时
            )
            result = json.loads(response.choices[0].message.content)
            
            # 过滤无效链接
            if result.get("links"):
                valid_links = []
                for link in result["links"]:
                    # 跳过无效链接
                    if not link or link.startswith("javascript:") or link.startswith("#"):
                        continue
                    if "login" in link.lower() or "register" in link.lower():
                        continue
                    valid_links.append(link)
                result["links"] = valid_links[:10]  # 最多10个
            
            print(f"[{site_name}] Page type: {result.get('page_type')}, Links: {len(result.get('links', []))}")
            return result
        except Exception as e:
            print(f"Discovery Error: {e}")
            return {"page_type": "article", "links": []}

    @staticmethod
    async def analyze_contract_clause(clause_text: str, context: str = "", contract_type: str = "") -> dict:
        """
        Analyzes a contract clause for risks using specialized prompt for international energy projects.
        Returns multiple risk points with detailed analysis.
        """
        system_prompt = """
# 角色设定
你是投资方的国际合同法专家，拥有20年跨境项目经验，擅长识别：
- 境外新能源合同中的结构性不利条款
- 表面中性、实质风险极高的"隐性毒丸条款"
- 条款组合产生的系统性风险

你的职责是：**深度识别风险、精准定位条款、详细解释影响**，而不是给出法律结论。找出有风险点的条款并加以详细说明，是什么风险，会有什么后果。

# 强制约束（必须遵守）
1. 你不是律师，不得输出法律结论或责任判断
2. 你的输出仅作为风险提示，供人工复核
3. 必须引用原文关键表述作为证据
4. 若信息不足，应明确说明"信息不足，无法判断"
5. 所有输出必须使用中文
6. 只报告真正的风险点，不要为了凑数而报告无关紧要的条款

# 审核关注维度（按优先级排序）

## 高优先级（必须重点审查）
1. **单方权利条款** - 单方解约、单方调价、单方变更
2. **责任分配失衡** - 免责条款、无限责任、违约金不对等
3. **定价与金融风险** - 汇率风险承担、币种错配、价格调整机制

## 中优先级
4. **政府承诺风险** - 承诺是否有法律约束力、政策免责
5. **担保与履约保障** - 担保方式、担保失效条件
6. **不可抗力滥用** - 定义是否过宽、是否包含政策变更

## 低优先级（仅在明显异常时报告）
7. **争议解决** - 管辖地、仲裁方式
8. **合同转让** - 转让限制

# 分析要求
1. **精准定位**：必须逐字引用合同原文中的风险条款，不得改写或概括
2. **条款编号**：如果原文有条款编号（如"第X条"、"X.X"），必须一并引用
3. **深度分析**：解释该条款为什么对投资方不利
4. **影响评估**：说明可能造成的实际商业影响
5. **只报告真正的风险**：如果条款是行业惯例或对双方公平，不要报告

# 输出格式（严格遵守）
返回 JSON 格式，包含多个风险点：
{
    "risks": [
        {
            "risk_category": "风险类别",
            "risk_level": "High / Medium / Low",
            "clause_id": "原文条款编号（如'第7条'、'7.1'，若无编号则填'无'）",
            "clause_text": "逐字引用的原文条款（完整引用，不要省略或改写）",
            "risk_reason": "一句话说明风险点",
            "explanation": "详细分析：1）条款含义 2）对投资方的不利影响 3）可能的商业后果",
            "confidence": 0.0-1.0
        }
    ],
    "overall_risk_level": "High / Medium / Low",
    "summary": "整体风险评估摘要（2-3句话）"
}

# 特殊情况处理
- 若未发现明显风险：返回空的 risks 数组，overall_risk_level: "Low"
- 若信息不足：在 summary 中说明
- 最多返回 5 个最重要的风险点，按严重程度排序
"""
        
        # Build user content
        user_content = f"【合同名称】{context}\n"
        if contract_type:
            user_content += f"【合同类型】{contract_type}\n"
        user_content += f"\n【合同条款内容】\n{clause_text}"
        
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.3  # Lower temperature for more consistent analysis
            )
            result = json.loads(response.choices[0].message.content)
            
            # Ensure required fields exist
            if "risks" not in result:
                result["risks"] = []
            if "overall_risk_level" not in result:
                result["overall_risk_level"] = "Low"
            if "summary" not in result:
                result["summary"] = "分析完成"
                
            return result
        except Exception as e:
            return {
                "risks": [],
                "overall_risk_level": "Low", 
                "summary": f"分析过程出错: {str(e)}"
            }
            
ai_engine = AIEngine()
