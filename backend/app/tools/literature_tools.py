import json
import re
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from app.agent.tool_registry import register_tool
from app.core.paths import GENERATED_DIR

LITERATURE_DIR = Path(GENERATED_DIR) / "literature"
LITERATURE_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_HEADERS = {
    "User-Agent": "BioAI-Agent/1.0 (iGEM literature tool)"
}

def _safe_get(url: str, params: dict = None, timeout: int = 20):
    resp = requests.get(url, params=params, timeout=timeout, headers=REQUEST_HEADERS)
    resp.raise_for_status()
    return resp

def _clamp_max_results(max_results: int, lower: int = 1, upper: int = 10):
    try:
        value = int(max_results)
    except Exception:
        value = 5
    return max(lower, min(value, upper))

def _normalize_text(text, limit: int = 1200):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:limit]

def _build_result(
    source: str,
    title: str = "",
    authors: str = "",
    journal: str = "",
    year: str = "",
    doi: str = "",
    pmid: str = "",
    pmcid: str = "",
    abstract: str = "",
    url: str = "",
    pdf_url: str = ""
):
    links = {}
    if url:
        links["primary"] = url
    if doi:
        links["doi"] = f"https://doi.org/{doi}"
    if pmid:
        links["pubmed"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    if pmcid:
        links["pmc"] = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    if pdf_url:
        links["pdf"] = pdf_url

    return {
        "source": source,
        "title": _normalize_text(title, 500),
        "authors": _normalize_text(authors, 500),
        "journal": _normalize_text(journal, 300),
        "year": str(year or ""),
        "doi": doi or "",
        "pmid": pmid or "",
        "pmcid": pmcid or "",
        "abstract_preview": _normalize_text(abstract, 1200),
        "url": url or "",
        "pdf_url": pdf_url or "",
        "links": links
    }

def _search_europe_pmc(query: str, max_results: int = 5):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results,
        "resultType": "core"
    }
    resp = _safe_get(url, params=params)
    data = resp.json()

    results = []
    for item in data.get("resultList", {}).get("result", []):
        doi = item.get("doi", "")
        pmid = item.get("pmid", "")
        pmcid = item.get("pmcid", "")
        pdf_url = ""

        if pmcid:
            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"

        primary_url = ""
        if pmid:
            primary_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        elif doi:
            primary_url = f"https://doi.org/{doi}"
        elif pmcid:
            primary_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"

        results.append(_build_result(
            source="Europe PMC",
            title=item.get("title", ""),
            authors=item.get("authorString", ""),
            journal=item.get("journalTitle", ""),
            year=item.get("pubYear", ""),
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            abstract=item.get("abstractText", ""),
            url=primary_url,
            pdf_url=pdf_url
        ))
    return results

def _search_crossref(query: str, max_results: int = 5):
    url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "rows": max_results
    }
    resp = _safe_get(url, params=params)
    data = resp.json()

    results = []
    for item in data.get("message", {}).get("items", []):
        title_list = item.get("title", []) or [""]
        title = title_list[0] if title_list else ""

        authors_raw = item.get("author", [])
        authors = ", ".join(
            [
                " ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
                for a in authors_raw[:10]
            ]
        )

        journal_list = item.get("container-title", []) or [""]
        journal = journal_list[0] if journal_list else ""

        year = ""
        issued = item.get("issued", {}).get("date-parts", [])
        if issued and issued[0]:
            year = str(issued[0][0])

        doi = item.get("DOI", "")
        primary_url = item.get("URL", "") or (f"https://doi.org/{doi}" if doi else "")

        abstract = item.get("abstract", "")
        if abstract:
            abstract = re.sub(r"<[^>]+>", " ", abstract)

        pdf_url = ""
        for link in item.get("link", []) or []:
            if "pdf" in str(link.get("content-type", "")).lower():
                pdf_url = link.get("URL", "")
                break

        results.append(_build_result(
            source="Crossref",
            title=title,
            authors=authors,
            journal=journal,
            year=year,
            doi=doi,
            abstract=abstract,
            url=primary_url,
            pdf_url=pdf_url
        ))
    return results

def _search_arxiv(query: str, max_results: int = 5):
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results
    }
    resp = _safe_get(url, params=params)
    root = ET.fromstring(resp.text)

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom"
    }

    results = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns)
        summary = entry.findtext("atom:summary", default="", namespaces=ns)

        authors = []
        for author in entry.findall("atom:author", ns):
            name = author.findtext("atom:name", default="", namespaces=ns)
            if name:
                authors.append(name)

        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = published[:4] if published else ""
        primary_url = entry.findtext("atom:id", default="", namespaces=ns)

        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
                break

        results.append(_build_result(
            source="arXiv",
            title=title,
            authors=", ".join(authors),
            journal="arXiv preprint",
            year=year,
            abstract=summary,
            url=primary_url,
            pdf_url=pdf_url
        ))
    return results

def _search_biorxiv(query: str, max_results: int = 5, server: str = "biorxiv"):
    """
    server: biorxiv / medrxiv
    API 文档风格：
    https://api.biorxiv.org/details/biorxiv/<interval>/<cursor>
    这里用最近 9999 天 + cursor=0 的方式取一批，再本地筛关键词
    """
    url = f"https://api.biorxiv.org/details/{server}/9999/0"
    resp = _safe_get(url, timeout=30)
    data = resp.json()

    query_lower = query.lower().strip()
    collection = data.get("collection", []) or []

    scored = []
    for item in collection:
        title = str(item.get("title", "")).strip()
        abstract = str(item.get("abstract", "")).strip()
        authors = str(item.get("authors", "")).strip()
        category = str(item.get("category", "")).strip()
        doi = str(item.get("doi", "")).strip()
        version = str(item.get("version", "")).strip()
        date = str(item.get("date", "")).strip()
        year = date[:4] if date else ""

        hay = f"{title} {abstract} {authors} {category}".lower()
        score = 0
        for token in query_lower.split():
            if token in hay:
                score += 1

        if score > 0:
            primary_url = f"https://www.biorxiv.org/content/{doi}v{version}" if doi and server == "biorxiv" else ""
            if server == "medrxiv" and doi:
                primary_url = f"https://www.medrxiv.org/content/{doi}v{version}"

            pdf_url = f"{primary_url}.full.pdf" if primary_url else ""

            scored.append((score, _build_result(
                source="bioRxiv" if server == "biorxiv" else "medRxiv",
                title=title,
                authors=authors,
                journal=f"{server} preprint",
                year=year,
                doi=doi,
                abstract=abstract,
                url=primary_url,
                pdf_url=pdf_url
            )))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:max_results]]

def _auto_route_sources(query: str):
    q = query.lower()

    # 生物/医学默认优先 Europe PMC
    sources = ["europe_pmc", "crossref"]

    if any(k in q for k in ["arxiv", "llm", "deep learning", "machine learning", "transformer", "diffusion"]):
        sources.insert(0, "arxiv")

    if any(k in q for k in ["preprint", "biorxiv", "medrxiv"]):
        sources.insert(0, "biorxiv")
        sources.insert(1, "medrxiv")

    return list(dict.fromkeys(sources))

@register_tool(
    name="search_literature",
    description="检索常见公共文献数据库。支持 auto / europe_pmc / crossref / arxiv / biorxiv / medrxiv。返回题目、作者、摘要片段、DOI、PMID、PMCID、链接和可能的 PDF 链接。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索关键词，例如 'aptamer cancer biomarker review'"
            },
            "source": {
                "type": "string",
                "description": "数据库来源：auto, europe_pmc, crossref, arxiv, biorxiv, medrxiv",
                "default": "auto"
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数，建议 3-10",
                "default": 5
            }
        },
        "required": ["query"]
    }
)
def search_literature(query: str, source: str = "auto", max_results: int = 5):
    """
    统一文献检索入口
    """
    try:
        max_results = _clamp_max_results(max_results, 1, 10)
        source = (source or "auto").strip().lower()

        all_results = []

        if source == "auto":
            sources = _auto_route_sources(query)
        else:
            sources = [source]

        for s in sources:
            try:
                if s == "europe_pmc":
                    all_results.extend(_search_europe_pmc(query, max_results=max_results))
                elif s == "crossref":
                    all_results.extend(_search_crossref(query, max_results=max_results))
                elif s == "arxiv":
                    all_results.extend(_search_arxiv(query, max_results=max_results))
                elif s == "biorxiv":
                    all_results.extend(_search_biorxiv(query, max_results=max_results, server="biorxiv"))
                elif s == "medrxiv":
                    all_results.extend(_search_biorxiv(query, max_results=max_results, server="medrxiv"))
                else:
                    return json.dumps({
                        "status": "error",
                        "message": f"不支持的 source: {source}"
                    }, ensure_ascii=False)
            except Exception as sub_e:
                all_results.append({
                    "source": s,
                    "error": str(sub_e)
                })

        # 去重：优先按 DOI，其次按 title
        dedup = []
        seen = set()
        for item in all_results:
            if "error" in item:
                dedup.append(item)
                continue

            key = (item.get("doi") or "").strip().lower()
            if not key:
                key = (item.get("title") or "").strip().lower()

            if key and key not in seen:
                seen.add(key)
                dedup.append(item)

        # 截断总返回数
        good_results = [x for x in dedup if "error" not in x][:max_results]
        errors = [x for x in dedup if "error" in x]

        return json.dumps({
            "status": "success",
            "query": query,
            "source": source,
            "count": len(good_results),
            "results": good_results,
            "errors": errors
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"文献检索失败: {str(e)}"
        }, ensure_ascii=False)

@register_tool(
    name="fetch_paper_details",
    description="根据 DOI、PMID、PMCID 获取单篇文献详细信息。优先从 Europe PMC 获取生物医学文献详情，也支持通过 Crossref 查询 DOI。",
    parameters={
        "type": "object",
        "properties": {
            "identifier": {
                "type": "string",
                "description": "PMID、PMCID 或 DOI，例如 '12345678'、'PMC1234567'、'10.1038/xxxx'"
            }
        },
        "required": ["identifier"]
    }
)
def fetch_paper_details(identifier: str):
    """
    DOI / PMID / PMCID 详情查询
    """
    try:
        identifier = str(identifier).strip()

        if identifier.upper().startswith("PMC"):
            query = f"PMCID:{identifier.upper()}"
        elif re.match(r"^\d+$", identifier):
            query = f"EXT_ID:{identifier} AND SRC:MED"
        else:
            query = f'DOI:"{identifier}"'

        # 先 Europe PMC
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": query,
            "format": "json",
            "pageSize": 1,
            "resultType": "core"
        }

        resp = _safe_get(url, params=params)
        data = resp.json()
        items = data.get("resultList", {}).get("result", [])

        if items:
            item = items[0]
            doi = item.get("doi", "")
            pmid = item.get("pmid", "")
            pmcid = item.get("pmcid", "")
            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/" if pmcid else ""

            primary_url = ""
            if pmid:
                primary_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif doi:
                primary_url = f"https://doi.org/{doi}"
            elif pmcid:
                primary_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"

            return json.dumps({
                "status": "success",
                "paper": {
                    "source": "Europe PMC",
                    "title": _normalize_text(item.get("title", ""), 500),
                    "authors": _normalize_text(item.get("authorString", ""), 500),
                    "journal": _normalize_text(item.get("journalTitle", ""), 300),
                    "year": str(item.get("pubYear", "")),
                    "doi": doi,
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "abstract": _normalize_text(item.get("abstractText", ""), 5000),
                    "url": primary_url,
                    "pdf_url": pdf_url,
                    "links": {
                        "primary": primary_url,
                        "doi": f"https://doi.org/{doi}" if doi else "",
                        "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                        "pmc": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else "",
                        "pdf": pdf_url
                    }
                }
            }, ensure_ascii=False)

        # Europe PMC 没找到时，尝试 Crossref DOI
        if not re.match(r"^\d+$", identifier) and not identifier.upper().startswith("PMC"):
            url = f"https://api.crossref.org/works/{quote(identifier)}"
            resp = _safe_get(url)
            item = resp.json().get("message", {})

            title_list = item.get("title", []) or [""]
            title = title_list[0] if title_list else ""

            authors_raw = item.get("author", [])
            authors = ", ".join(
                [
                    " ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
                    for a in authors_raw[:10]
                ]
            )

            journal_list = item.get("container-title", []) or [""]
            journal = journal_list[0] if journal_list else ""

            year = ""
            issued = item.get("issued", {}).get("date-parts", [])
            if issued and issued[0]:
                year = str(issued[0][0])

            abstract = item.get("abstract", "")
            if abstract:
                abstract = re.sub(r"<[^>]+>", " ", abstract)

            pdf_url = ""
            for link in item.get("link", []) or []:
                if "pdf" in str(link.get("content-type", "")).lower():
                    pdf_url = link.get("URL", "")
                    break

            doi = item.get("DOI", "")
            primary_url = item.get("URL", "") or (f"https://doi.org/{doi}" if doi else "")

            return json.dumps({
                "status": "success",
                "paper": {
                    "source": "Crossref",
                    "title": _normalize_text(title, 500),
                    "authors": _normalize_text(authors, 500),
                    "journal": _normalize_text(journal, 300),
                    "year": year,
                    "doi": doi,
                    "pmid": "",
                    "pmcid": "",
                    "abstract": _normalize_text(abstract, 5000),
                    "url": primary_url,
                    "pdf_url": pdf_url,
                    "links": {
                        "primary": primary_url,
                        "doi": f"https://doi.org/{doi}" if doi else "",
                        "pdf": pdf_url
                    }
                }
            }, ensure_ascii=False)

        return json.dumps({
            "status": "error",
            "message": f"未找到文献: {identifier}"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"获取文献详情失败: {str(e)}"
        }, ensure_ascii=False)

@register_tool(
    name="download_open_access_pdf",
    description="下载开放获取的论文 PDF。输入可以是 PDF 链接、PMCID，或 DOI（若能解析到 PDF）。PDF 将保存到 generated/literature/ 目录。",
    parameters={
        "type": "object",
        "properties": {
            "identifier_or_url": {
                "type": "string",
                "description": "PDF URL、PMCID 或 DOI"
            },
            "filename_hint": {
                "type": "string",
                "description": "可选的保存文件名提示，不需要带 .pdf",
                "default": ""
            }
        },
        "required": ["identifier_or_url"]
    }
)
def download_open_access_pdf(identifier_or_url: str, filename_hint: str = ""):
    """
    下载开放获取 PDF
    """
    try:
        identifier_or_url = str(identifier_or_url).strip()
        pdf_url = ""

        # 1. 直接传 PDF URL
        if identifier_or_url.lower().startswith("http") and identifier_or_url.lower().endswith(".pdf"):
            pdf_url = identifier_or_url

        # 2. PMCID
        elif identifier_or_url.upper().startswith("PMC"):
            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{identifier_or_url.upper()}/pdf/"

        # 3. DOI -> 先查详情
        else:
            detail_raw = fetch_paper_details(identifier_or_url)
            detail_data = json.loads(detail_raw)
            if detail_data.get("status") == "success":
                pdf_url = detail_data.get("paper", {}).get("pdf_url", "")

        if not pdf_url:
            return json.dumps({
                "status": "error",
                "message": "未找到可下载的开放获取 PDF 链接"
            }, ensure_ascii=False)

        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename_hint.strip()) if filename_hint else ""
        if not safe_name:
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", identifier_or_url)[:80]

        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"

        save_path = LITERATURE_DIR / safe_name

        resp = requests.get(pdf_url, timeout=30, headers=REQUEST_HEADERS)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
            # 有些站点会重定向到 HTML 错误页
            if not resp.content.startswith(b"%PDF"):
                return json.dumps({
                    "status": "error",
                    "message": f"目标不是有效 PDF: {pdf_url}"
                }, ensure_ascii=False)

        with open(save_path, "wb") as f:
            f.write(resp.content)

        relative_path = f"generated/literature/{save_path.name}"
        url = f"/files/{relative_path}"

        return json.dumps({
            "status": "success",
            "filename": save_path.name,
            "relative_path": relative_path,
            "url": url,
            "pdf_url": pdf_url
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"下载 PDF 失败: {str(e)}"
        }, ensure_ascii=False)