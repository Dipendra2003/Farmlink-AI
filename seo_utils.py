"""
Enterprise SEO Utilities and Schema.org Generator for FarmLink AI
Provides JSON-LD rich snippet builders, canonical URL formatting, pagination helpers, and Jinja context injection.
"""

import json
import re
import os
from datetime import datetime
from flask import request, url_for, current_app
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

def strip_html(text):
    """Strip HTML tags and markdown formatting for clean SEO descriptions"""
    if not text:
        return ""
    # Strip HTML tags
    clean = re.sub(r'<[^>]+>', '', str(text))
    # Strip basic markdown symbols
    clean = re.sub(r'[#*`~_\[\]()]', '', clean)
    # Collapse multiple whitespaces
    clean = ' '.join(clean.split())
    return clean

def truncate_meta_description(text, max_length=155):
    """Clean and truncate text to recommended SEO meta description length without breaking words"""
    clean_text = strip_html(text)
    if len(clean_text) <= max_length:
        return clean_text
    truncated = clean_text[:max_length].rsplit(' ', 1)[0]
    return f"{truncated}..."

def clean_canonical_url(req=None):
    """
    Generate canonical URL stripping tracking parameters (utm_*, gclid, fbclid, etc.)
    Preserves structural pagination and core filtering params when needed.
    """
    if req is None:
        req = request
    
    # Base external URL without query string
    try:
        url = req.base_url
        if req.query_string:
            parsed = urlparse(req.url)
            params = parse_qs(parsed.query)
            # Remove tracking and transient marketing parameters
            remove_keys = [k for k in params if k.lower().startswith('utm_') or k.lower() in ('gclid', 'fbclid', 'ref', 'source', 'token', '_')]
            for k in remove_keys:
                del params[k]
            if params:
                query_string = urlencode(params, doseq=True)
                url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query_string, parsed.fragment))
        return url
    except Exception:
        return req.url if req else ""

def generate_organization_schema():
    """Generate global Organization and WebSite SearchAction schema"""
    base_url = url_for('index', _external=True)
    logo_url = url_for('static', filename='images/logo.png', _external=True) if os.path.exists(os.path.join(current_app.static_folder or '', 'images', 'logo.png')) else url_for('static', filename='favicon.ico', _external=True)
    
    org_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "FarmLink AI",
        "url": base_url,
        "logo": logo_url,
        "description": "AI-powered agricultural marketplace and knowledge hub connecting farmers, buyers, and agronomy experts.",
        "sameAs": [
            "https://twitter.com/farmlinkai",
            "https://facebook.com/farmlinkai",
            "https://linkedin.com/company/farmlinkai"
        ]
    }
    
    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "FarmLink AI",
        "url": base_url,
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{url_for('marketplace', _external=True)}?search={{search_term_string}}",
            "query-input": "required name=search_term_string"
        }
    }
    return json.dumps([org_schema, website_schema], separators=(',', ':'))

def generate_breadcrumb_schema(items):
    """
    Generate BreadcrumbList Schema from a list of dicts or tuples:
    [{"name": "Home", "item": "http://..."}, {"name": "Marketplace", "item": "http://..."}]
    """
    element_list = []
    for idx, item in enumerate(items, start=1):
        name = item.get('name') if isinstance(item, dict) else item[0]
        url = item.get('item') if isinstance(item, dict) else (item[1] if len(item) > 1 else None)
        entry = {
            "@type": "ListItem",
            "position": idx,
            "name": name
        }
        if url and idx < len(items):  # Last item usually does not require canonical item URL in breadcrumbs or can have it
            entry["item"] = url
        element_list.append(entry)
        
    schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": element_list
    }
    return json.dumps(schema, separators=(',', ':'))

def generate_product_schema(crop, seller_name, canonical_url, image_url, avg_rating=None, review_count=0):
    """Generate structured Google Product and Offer Schema for agricultural crops"""
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": crop.name,
        "description": truncate_meta_description(getattr(crop, 'description', '') or crop.name, 300),
        "image": [image_url] if image_url else [],
        "sku": f"FL-CROP-{crop.id}",
        "offers": {
            "@type": "Offer",
            "url": canonical_url,
            "priceCurrency": "INR",
            "price": str(getattr(crop, 'price', 0) or 0),
            "priceValidUntil": (datetime.utcnow().replace(year=datetime.utcnow().year + 1)).strftime('%Y-%m-%d'),
            "itemCondition": "https://schema.org/NewCondition",
            "availability": "https://schema.org/InStock" if getattr(crop, 'status', 'available') == 'available' and getattr(crop, 'quantity', 1) > 0 else "https://schema.org/OutOfStock",
            "seller": {
                "@type": "Organization" if getattr(crop, 'is_corporate', False) else "Person",
                "name": seller_name or "Verified Farmer"
            }
        }
    }
    
    if avg_rating and float(avg_rating) > 0 and review_count > 0:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(round(float(avg_rating), 1)),
            "reviewCount": str(int(review_count))
        }
        
    return json.dumps(schema, separators=(',', ':'))

def generate_article_schema(article, author_name, canonical_url, image_url):
    """Generate structured Article / TechArticle Schema for Learning Hub knowledge posts"""
    created_str = article.created_at.isoformat() if getattr(article, 'created_at', None) else datetime.utcnow().isoformat()
    updated_str = article.updated_at.isoformat() if getattr(article, 'updated_at', None) else created_str
    
    schema = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": getattr(article, 'title', 'Agronomy Learning Article')[:110],
        "description": truncate_meta_description(getattr(article, 'summary', None) or getattr(article, 'content', ''), 200),
        "image": [image_url] if image_url else [],
        "datePublished": created_str,
        "dateModified": updated_str,
        "author": {
            "@type": "Person",
            "name": author_name or "FarmLink AI Agronomy Expert"
        },
        "publisher": {
            "@type": "Organization",
            "name": "FarmLink AI",
            "logo": {
                "@type": "ImageObject",
                "url": url_for('static', filename='favicon.ico', _external=True)
            }
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        }
    }
    return json.dumps(schema, separators=(',', ':'))

def generate_qapage_schema(post, author_name, canonical_url):
    """Generate structured QAPage or DiscussionForumPosting Schema for Expert Forum discussions"""
    created_str = post.created_at.isoformat() if getattr(post, 'created_at', None) else datetime.utcnow().isoformat()
    replies = getattr(post, 'replies', []) or []
    
    is_question = getattr(post, 'is_question', True)
    schema_type = "QAPage" if is_question else "DiscussionForumPosting"
    
    main_entity = {
        "@type": "Question" if is_question else "DiscussionForumPosting",
        "name": getattr(post, 'title', 'Agricultural Forum Discussion')[:150],
        "text": strip_html(getattr(post, 'content', '')),
        "dateCreated": created_str,
        "author": {
            "@type": "Person",
            "name": author_name or "FarmLink Community Member"
        },
        "answerCount": len(replies),
        "upvoteCount": getattr(post, 'upvotes', 0) or 0
    }
    
    # Include accepted or top solution answers if present
    accepted_replies = [r for r in replies if getattr(r, 'is_solution', False)]
    other_replies = [r for r in replies if not getattr(r, 'is_solution', False)]
    
    if accepted_replies:
        sol = accepted_replies[0]
        main_entity["acceptedAnswer"] = {
            "@type": "Answer",
            "text": strip_html(getattr(sol, 'content', '')),
            "dateCreated": sol.created_at.isoformat() if getattr(sol, 'created_at', None) else created_str,
            "upvoteCount": getattr(sol, 'upvotes', 0) or 0,
            "author": {
                "@type": "Person",
                "name": getattr(sol.author, 'username', 'Agri Expert') if getattr(sol, 'author', None) else "Agri Expert"
            }
        }
    elif other_replies:
        top_reply = sorted(other_replies, key=lambda r: getattr(r, 'upvotes', 0) or 0, reverse=True)[0]
        main_entity["suggestedAnswer"] = {
            "@type": "Answer",
            "text": strip_html(getattr(top_reply, 'content', '')),
            "dateCreated": top_reply.created_at.isoformat() if getattr(top_reply, 'created_at', None) else created_str,
            "upvoteCount": getattr(top_reply, 'upvotes', 0) or 0,
            "author": {
                "@type": "Person",
                "name": getattr(top_reply.author, 'username', 'Agri Expert') if getattr(top_reply.author, 'author', None) else "Agri Expert"
            }
        }
        
    if is_question:
        schema = {
            "@context": "https://schema.org",
            "@type": "QAPage",
            "mainEntity": main_entity
        }
    else:
        schema = {
            "@context": "https://schema.org",
            "mainEntityOfPage": canonical_url,
            **main_entity
        }
    return json.dumps(schema, separators=(',', ':'))

def generate_faq_schema(faq_items):
    """
    Generate structured FAQPage Schema from a list of dicts/tuples:
    [{"question": "How to order?", "answer": "Click Buy Direct..."}]
    """
    main_entities = []
    for item in faq_items:
        q = item.get('question') if isinstance(item, dict) else item[0]
        a = item.get('answer') if isinstance(item, dict) else item[1]
        main_entities.append({
            "@type": "Question",
            "name": str(q),
            "acceptedAnswer": {
                "@type": "Answer",
                "text": strip_html(str(a))
            }
        })
        
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": main_entities
    }
    return json.dumps(schema, separators=(',', ':'))

def get_seo_pagination_links(page, total_pages, endpoint=None, **kwargs):
    """Generate SEO canonical, prev, and next link attributes for paginated lists"""
    if endpoint is None:
        try:
            endpoint = request.endpoint
        except Exception:
            return {}
            
    if not endpoint:
        return {}
        
    links = {}
    args = request.args.to_dict() if request else {}
    args.update(kwargs)
    
    # Ensure canonical has page number if > 1, otherwise clean root
    try:
        if page and page > 1:
            args['page'] = page
            links['canonical_url'] = url_for(endpoint, _external=True, **args)
        else:
            if 'page' in args:
                del args['page']
            links['canonical_url'] = url_for(endpoint, _external=True, **args)
            
        if page and page > 1:
            prev_args = args.copy()
            if page - 1 == 1 and 'page' in prev_args:
                del prev_args['page']
            else:
                prev_args['page'] = page - 1
            links['prev_url'] = url_for(endpoint, _external=True, **prev_args)
            
        if page and total_pages and page < total_pages:
            next_args = args.copy()
            next_args['page'] = page + 1
            links['next_url'] = url_for(endpoint, _external=True, **next_args)
    except Exception:
        pass
        
    return links

def init_seo_processor(app):
    """Register SEO helpers and environmental constants into global template context"""
    @app.context_processor
    def inject_seo_helpers():
        return {
            'clean_canonical_url': clean_canonical_url,
            'truncate_meta_description': truncate_meta_description,
            'strip_html': strip_html,
            'generate_organization_schema': generate_organization_schema,
            'generate_breadcrumb_schema': generate_breadcrumb_schema,
            'generate_product_schema': generate_product_schema,
            'generate_article_schema': generate_article_schema,
            'generate_qapage_schema': generate_qapage_schema,
            'generate_faq_schema': generate_faq_schema,
            'get_seo_pagination_links': get_seo_pagination_links,
            'GOOGLE_SITE_VERIFICATION': os.environ.get('GOOGLE_SITE_VERIFICATION', 'j_SFQieTDFMkB-XrDvcgebzyGmcFeg3Yue7LgZ00diM'),
            'GA_MEASURE_ID': os.environ.get('GA_MEASURE_ID', '')
        }
