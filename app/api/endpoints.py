from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db, engine, AsyncSessionLocal
from app.db.models import Base, IntelligenceSource, IntelligenceItem, ContractTask, ContractRisk
from app.services.crawler import crawler_service
from app.services.ai_engine import ai_engine, check_keyword_relevance
from app.services.contract_parser import contract_parser
import asyncio
from datetime import datetime
from urllib.parse import urljoin

router = APIRouter()

# --- DB INIT ---
@router.on_event("startup")
async def init_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- BACKGROUND TASK: Process Source ---
async def process_source_background(source_id: str, url: str):
    """后台处理信源爬取和AI分析"""
    async with AsyncSessionLocal() as db:
        try:
            source = await db.get(IntelligenceSource, source_id)
            if not source:
                return
            
            # 1. Crawl Seed
            markdown = await crawler_service.fetch_page(url)
            if not markdown:
                source.status = "error"
                source.error_message = "Crawl failed (Empty content)"
                await db.commit()
                return

            # 2. Smart Discovery
            discovery = await ai_engine.detect_and_extract_links(markdown, url)
            
            # 获取已采集的URL列表（用于去重）
            existing_urls_result = await db.execute(
                select(IntelligenceItem.url).where(IntelligenceItem.url.isnot(None))
            )
            existing_urls = set(row[0] for row in existing_urls_result.fetchall())
            print(f"[Dedup] Found {len(existing_urls)} existing URLs in database")
            
            items_to_process = []
            if discovery.get("page_type") == "list" and discovery.get("links"):
                # 先去重，再限制数量（这样每次都能采集新文章）
                all_links = discovery['links']
                new_links = []
                for link in all_links:
                    full_url = urljoin(url, link)
                    if full_url not in existing_urls:
                        new_links.append(full_url)
                    else:
                        print(f"[Dedup] Skipping already collected: {full_url}")
                
                # 限制每次最多采集3篇新文章
                links_to_process = new_links[:3]
                print(f"Detected List Page. Processing {len(links_to_process)} new links (from {len(all_links)} total, {len(new_links)} new)")
                items_to_process = links_to_process
            else:
                # 单篇文章也检查去重
                if url not in existing_urls:
                    items_to_process.append((url, markdown))
                else:
                    print(f"[Dedup] Skipping already collected: {url}")
            
            if not items_to_process:
                print(f"[Dedup] All links already collected, nothing new to process")
                source.status = "active"
                source.last_crawled_at = datetime.utcnow()
                await db.commit()
                return

            processed_count = 0
            errors = []

            # 并行爬取所有文章
            async def process_single_item(item):
                try:
                    if isinstance(item, str):
                        target_url = item
                        target_md = await crawler_service.fetch_page(target_url)
                        if not target_md: 
                            return None
                    else:
                        target_url, target_md = item
                    
                    # 过滤列表页 URL（不应该作为文章处理）
                    list_page_patterns = ['/news/news', '/news/events', '/index.html', '/index.htm', '/list/', '/category/', '/events/', '/archive/']
                    if any(pattern in target_url.lower() for pattern in list_page_patterns):
                        print(f"Skipping list page URL: {target_url}")
                        return None
                    
                    # Extract with URL for site-specific hints
                    data = await ai_engine.extract_intelligence(target_md, target_url)
                    if not data.get("title"): 
                        return None
                    
                    # 过滤低质量内容（列表页、无实质内容）
                    summary = data.get("summary", "")
                    main_content = data.get("main_content", "")
                    title = data.get("title", "")
                    low_quality_indicators = ["信息不足", "无法分析", "列表页", "新闻列表", "目录页", "事件列表", "无具体", "仅为事件"]
                    # 标题过滤：单词标题通常是列表页
                    generic_titles = ["news", "events", "home", "index", "list", "archive", "category", "economy", "finance", "politics", "society"]
                    if title.lower().strip() in generic_titles:
                        print(f"Skipping generic title page: {target_url} (title: {title})")
                        return None
                    # 标题过滤：包含列表页特征词的标题
                    list_title_patterns = ["latest news", "news from", "top stories", "breaking news", "headlines", "recent posts", "all news", "news list"]
                    if any(p in title.lower() for p in list_title_patterns):
                        print(f"Skipping list page title: {target_url} (title: {title})")
                        return None
                    if any(indicator in summary for indicator in low_quality_indicators):
                        print(f"Skipping low quality content: {target_url}")
                        return None
                    if len(main_content) < 100 and len(summary) < 50:
                        print(f"Skipping too short content: {target_url}")
                        return None
                    
                    # 检测原文是否是列表页内容（包含多个分类链接或多个日期行）
                    list_content_patterns = ["Categories", "[Uzbekistan]", "[Economy]", "[Finance]", "/section/1/", "/section/2/"]
                    list_pattern_count = sum(1 for p in list_content_patterns if p in main_content)
                    # 检测多个日期行（列表页特征：多篇文章标题+日期）
                    import re
                    date_lines = re.findall(r'\d{4}-\d{2}-\d{2}', main_content)
                    if len(date_lines) >= 4:  # 4个以上日期说明是列表
                        print(f"Skipping list page content (multiple dates): {target_url}")
                        return None
                    if list_pattern_count >= 3:
                        print(f"Skipping list page content: {target_url} (matched {list_pattern_count} list patterns)")
                        return None
                    
                    # 关键字过滤已禁用：采集所有文章
                    # if not check_keyword_relevance(title, summary):
                    #     print(f"Skipping irrelevant content (no keywords): {target_url} (title: {title[:30]}...)")
                    #     return None

                    clean_content = main_content
                    final_content = target_md if len(clean_content) < 200 else clean_content
                    author = data.get("author", "Unknown")
                    
                    return {
                        "title": data.get("title"),
                        "title_zh": data.get("title_zh", data.get("title")),  # 中文标题，如无则用原标题
                        "publish_date": data.get("publish_date"),
                        "content_type": data.get("content_type"),
                        "summary": data.get("summary"),
                        "risk_tags": data.get("keywords", []),
                        "risk_hint": data.get("risk_hint"),
                        "url": target_url,
                        "original_text": f"[Source: {target_url}]\n[Author: {author}]\n\n" + final_content,
                        "translated_text": data.get("translated_content", ""),
                    }
                except Exception as e:
                    print(f"Error processing {item}: {e}")
                    return None
            
            # 并行处理（最多3个并发）
            import asyncio
            semaphore = asyncio.Semaphore(3)
            
            async def limited_process(item):
                async with semaphore:
                    return await process_single_item(item)
            
            results = await asyncio.gather(*[limited_process(item) for item in items_to_process])
            
            # 保存结果
            for result in results:
                if result:
                    db_item = IntelligenceItem(
                        source_id=source.id,
                        title=result["title"],
                        title_zh=result.get("title_zh"),
                        publish_date=result["publish_date"],
                        content_type=result["content_type"],
                        summary=result["summary"],
                        risk_tags=result["risk_tags"],
                        risk_hint=result["risk_hint"],
                        url=result["url"],
                        original_text=result["original_text"],
                        translated_text=result["translated_text"],
                        relevance_score=0.9
                    )
                    db.add(db_item)
                    processed_count += 1

            source.status = "active" if processed_count > 0 else "error"
            source.last_crawled_at = datetime.utcnow()
            if not processed_count:
                source.error_message = "No articles extracted"
            
            await db.commit()
            print(f"Source {url} processed: {processed_count} items")
            
        except Exception as e:
            print(f"Background task error: {e}")
            try:
                source = await db.get(IntelligenceSource, source_id)
                if source:
                    source.status = "error"
                    source.error_message = str(e)[:200]
                    await db.commit()
            except:
                pass

# --- INTELLIGENCE ENDPOINTS ---

@router.post("/intelligence/source")
async def add_source(url: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """添加信源 - 立即返回，后台处理"""
    # 清理 URL
    url = url.strip()
    
    # 1. Check if exists
    result = await db.execute(select(IntelligenceSource).where(IntelligenceSource.url == url))
    source = result.scalars().first()
    
    if source:
        return {"status": "exists", "source_id": source.id, "message": "Source already exists"}
    
    # 2. Create source with pending status
    source = IntelligenceSource(url=url, status="processing")
    db.add(source)
    await db.commit()
    await db.refresh(source)
    
    # 3. Start background processing
    asyncio.create_task(process_source_background(source.id, url))
    
    return {"status": "processing", "source_id": source.id, "message": "Source added, processing in background"}

@router.get("/intelligence/list")
async def list_intelligence(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(IntelligenceItem, IntelligenceSource.url)
        .join(IntelligenceSource, IntelligenceItem.source_id == IntelligenceSource.id)
        .order_by(IntelligenceItem.created_at.desc())  # 按采集时间排序，最新的在前
    )
    
    response = []
    for item, url in result.all():
        data = {
            "id": item.id,
            "source_id": item.source_id,
            "source_url": item.url if item.url else url,
            "title": item.title,
            "title_zh": item.title_zh,
            "publish_date": item.publish_date,
            "content_type": item.content_type,
            "summary": item.summary,
            "risk_tags": item.risk_tags,
            "risk_hint": item.risk_hint,
            "original_text": item.original_text,
            "translated_text": item.translated_text,
            "relevance_score": item.relevance_score
        }
        response.append(data)
    return response

@router.delete("/intelligence/item/{item_id}")
async def delete_intelligence_item(item_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(IntelligenceItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}

@router.post("/intelligence/batch-delete")
async def batch_delete_intelligence_items(item_ids: list[str], db: AsyncSession = Depends(get_db)):
    """批量删除情报条目"""
    deleted_count = 0
    for item_id in item_ids:
        item = await db.get(IntelligenceItem, item_id)
        if item:
            await db.delete(item)
            deleted_count += 1
    await db.commit()
    return {"status": "deleted", "count": deleted_count}

# --- SOURCE MANAGEMENT ENDPOINTS ---

@router.get("/source/list")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IntelligenceSource))
    sources = result.scalars().all()
    return [
        {
            "id": s.id,
            "url": s.url,
            "status": s.status,
            "last_crawled_at": s.last_crawled_at,
            "error_message": s.error_message,
            "created_at": s.created_at
        }
        for s in sources
    ]

@router.delete("/source/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(IntelligenceSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)
    await db.commit()
    return {"status": "deleted"}

@router.put("/source/{source_id}")
async def update_source(source_id: str, url: str, db: AsyncSession = Depends(get_db)):
    """更新信源 URL"""
    source = await db.get(IntelligenceSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.url = url.strip()
    await db.commit()
    return {"status": "updated", "url": source.url}

@router.post("/source/{source_id}/retry")
async def retry_source(source_id: str, db: AsyncSession = Depends(get_db)):
    """重试信源 - 立即返回，后台处理"""
    source = await db.get(IntelligenceSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Update status and start background task
    source.status = "processing"
    source.error_message = None
    await db.commit()
    
    asyncio.create_task(process_source_background(source.id, source.url))
    
    return {"status": "processing", "message": "Retry started in background"}

@router.post("/source/batch-crawl")
async def batch_crawl_sources(db: AsyncSession = Depends(get_db)):
    """批量采集所有信源 - 立即返回，后台处理"""
    result = await db.execute(select(IntelligenceSource))
    sources = result.scalars().all()
    
    started_count = 0
    for source in sources:
        # 跳过正在处理的信源
        if source.status == "processing":
            continue
        
        source.status = "processing"
        source.error_message = None
        started_count += 1
        asyncio.create_task(process_source_background(source.id, source.url))
    
    await db.commit()
    
    return {
        "status": "processing", 
        "message": f"Started crawling {started_count} sources in background",
        "count": started_count
    }

# --- CONTRACT ENDPOINTS ---


@router.post("/contract/upload")
async def upload_contract(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    print(f"[Contract] Received file: {file.filename}, content_type: {file.content_type}")
    
    task = ContractTask(filename=file.filename, status="processing")
    db.add(task)
    await db.commit()
    await db.refresh(task)
    print(f"[Contract] Created task: {task.id}")
    
    try:
        print(f"[Contract] Parsing file: {file.filename}")
        text = await contract_parser.parse_file(file)
        if not text or len(text) < 50:
            raise Exception(f"文件解析失败或内容过短 (长度: {len(text) if text else 0})")
        
        print(f"[Contract] Parsed {len(text)} chars, starting AI analysis...")
        safe_text = contract_parser.desensitize(text)
        
        chunk_size = 6000
        chunks = [safe_text[i:i+chunk_size] for i in range(0, len(safe_text), chunk_size)]
        
        all_ai_risks = []
        overall_levels = []
        
        for i, chunk in enumerate(chunks[:3]):
            print(f"[Contract] Analyzing chunk {i+1}/{min(len(chunks), 3)}...")
            ai_result = await ai_engine.analyze_contract_clause(
                chunk, 
                context=f"{task.filename} (第{i+1}部分，共{min(len(chunks), 3)}部分)",
                contract_type=""
            )
            if ai_result.get("risks"):
                all_ai_risks.extend(ai_result["risks"])
            if ai_result.get("overall_risk_level"):
                overall_levels.append(ai_result["overall_risk_level"])
        
        print(f"[Contract] Found {len(all_ai_risks)} risks")
        
        seen_clauses = set()
        risk_count = 0
        for risk in all_ai_risks:
            clause_text = risk.get("clause_text", "")
            clause_key = clause_text[:80] if clause_text else ""
            if clause_key and clause_key not in seen_clauses:
                seen_clauses.add(clause_key)
                risk_count += 1
                clause_id = risk.get("clause_id", "")
                if not clause_id or clause_id == "无":
                    clause_id = f"风险点-{risk_count}"
                
                db.add(ContractRisk(
                    task_id=task.id,
                    clause_text=clause_text,
                    clause_id=clause_id,
                    risk_category=risk.get("risk_category"),
                    risk_level=risk.get("risk_level", "Low"),
                    risk_reason=risk.get("risk_reason"),
                    explanation=risk.get("explanation"),
                    confidence=risk.get("confidence", 0.0)
                ))
        
        if "High" in overall_levels or any(r.get("risk_level") == "High" for r in all_ai_risks):
            task.overall_risk_level = "High"
        elif "Medium" in overall_levels or any(r.get("risk_level") == "Medium" for r in all_ai_risks):
            task.overall_risk_level = "Medium"
        else:
            task.overall_risk_level = "Low"
        
        task.status = "done"
        await db.commit()
        print(f"[Contract] Analysis complete: {task.overall_risk_level}")
        
    except Exception as e:
        print(f"[Contract] ERROR: {e}")
        task.status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    return {"task_id": task.id, "status": "done"}

@router.get("/contract/{task_id}/result")
async def get_contract_result(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(ContractTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await db.execute(select(ContractRisk).where(ContractRisk.task_id == task_id))
    risks = result.scalars().all()
    return {"task": task, "risks": risks}

@router.get("/contract/list")
async def list_contract_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContractTask).order_by(ContractTask.upload_time.desc()))
    tasks = result.scalars().all()
    return [
        {
            "id": t.id,
            "filename": t.filename,
            "status": t.status,
            "overall_risk_level": t.overall_risk_level,
            "created_at": t.upload_time
        }
        for t in tasks
    ]

@router.delete("/contract/{task_id}")
async def delete_contract_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(ContractTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.execute(ContractRisk.__table__.delete().where(ContractRisk.task_id == task_id))
    await db.delete(task)
    await db.commit()
    return {"status": "deleted"}
