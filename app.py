from flask import Flask, render_template, request, send_file, jsonify, session, after_this_request
import requests
from bs4 import BeautifulSoup
import os
import re
import json
from urllib.parse import urljoin, urlparse, urlunparse, unquote, quote, parse_qs
import zipfile
from io import BytesIO
import mimetypes
import base64
import cssutils
import logging
import uuid
import random
import time
import urllib3
import tempfile
from datetime import datetime
import traceback
import html
import shutil
import threading

# Try to import Selenium
SELENIUM_AVAILABLE = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
    print("Selenium is available. Advanced rendering is enabled.")
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium not available. Advanced rendering will be disabled.")

# Suppress cssutils warnings
cssutils.log.setLevel(logging.CRITICAL)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_for_website_extractor')

def is_binary_content(content, asset_type):
    """Determine if content should be treated as binary or text based on asset type and content inspection"""
    # First check by asset type
    if asset_type in ['images', 'fonts', 'videos', 'audio']:
        return True
        
    # For potentially text-based assets, try to detect if it's binary
    if asset_type in ['css', 'js', 'html', 'svg', 'json', 'globals_css']:
        # Check if the content is bytes
        if not isinstance(content, bytes):
            return False
            
        # Try to detect if binary by checking for null bytes and high concentration of non-ASCII chars
        try:
            # Check for null bytes which indicate binary content
            if b'\x00' in content:
                return True
                
            # Sample the first 1024 bytes to determine if it's binary
            sample = content[:1024]
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
            return bool(sample.translate(None, text_chars))
        except:
            # If there's any error in detection, treat as binary to be safe
            return True
            
    # For anything else, just check if it's bytes
    return isinstance(content, bytes)

def download_asset(url, base_url, headers=None, session_obj=None):
    """
    Download an asset from a URL
    
    Args:
        url: URL to download from
        base_url: Base URL of the website (for referrer)
        headers: Optional custom headers
        session_obj: Optional requests.Session object for maintaining cookies
    
    Returns:
        Content of the asset or None if download failed
    """
    # List of user agents to rotate through to avoid detection
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    ]
    
    # Use a random user agent
    random_user_agent = random.choice(user_agents)
    
    if not headers:
        headers = {
            'User-Agent': random_user_agent,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': base_url,
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
    else:
        # Update the user agent in the provided headers
        headers['User-Agent'] = random_user_agent
    
    # Parse the URL to check if it's valid
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            print(f"Invalid URL: {url}")
            return None
    except Exception as e:
        print(f"Error parsing URL {url}: {str(e)}")
        return None
    
    # Add a delay to avoid rate limiting
    time.sleep(0.1)  # 100ms delay between requests
    
    # Maximum number of retries
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Use session if provided, otherwise make a direct request
            if session_obj:
                response = session_obj.get(
                    url, 
                    timeout=15, 
                    headers=headers, 
                    stream=True, 
                    allow_redirects=True,
                    verify=False  # Ignore SSL certificate errors
                )
            else:
                response = requests.get(
                    url, 
                    timeout=15, 
                    headers=headers, 
                    stream=True, 
                    allow_redirects=True,
                    verify=False  # Ignore SSL certificate errors
                )
            
            # Handle redirects
            if response.history:
                print(f"Request for {url} was redirected {len(response.history)} times to {response.url}")
                url = response.url  # Update URL to the final destination
            
            if response.status_code == 200:
                # Check the Content-Type header
                content_type = response.headers.get('Content-Type', '')
                print(f"Downloaded {url} ({len(response.content)} bytes, type: {content_type})")
                
                # Check for binary content types
                is_binary = any(binary_type in content_type.lower() for binary_type in [
                    'image/', 'video/', 'audio/', 'font/', 'application/octet-stream', 
                    'application/zip', 'application/x-rar', 'application/pdf', 'application/vnd.'
                ])
                
                # If binary or content-type suggests binary, return raw content
                if is_binary:
                    return response.content
                
                # For text content types
                is_text = any(text_type in content_type.lower() for text_type in [
                    'text/', 'application/json', 'application/javascript', 'application/xml', 'application/xhtml'
                ])
                
                if is_text:
                    # Try to determine encoding
                    encoding = None
                    
                    # From Content-Type header
                    if 'charset=' in content_type:
                        encoding = content_type.split('charset=')[1].split(';')[0].strip()
                    
                    # From response encoding or apparent encoding
                    if not encoding:
                        encoding = response.encoding or response.apparent_encoding or 'utf-8'
                    
                    # Decode with specified encoding
                    try:
                        return response.content.decode(encoding, errors='replace').encode('utf-8')
                    except (UnicodeDecodeError, LookupError):
                        # If decoding fails, try utf-8
                        try:
                            return response.content.decode('utf-8', errors='replace').encode('utf-8')
                        except:
                            # If all else fails, return raw content
                            return response.content
                
                # For unknown content types, return raw content
                return response.content
            elif response.status_code == 404:
                print(f"Resource not found (404): {url}")
                return None
            elif response.status_code == 403:
                print(f"Access forbidden (403): {url}")
                # Try with a different user agent on the next retry
                headers['User-Agent'] = random.choice(user_agents)
                retry_count += 1
                time.sleep(1)  # Wait longer before retrying
                continue
            elif response.status_code >= 500:
                print(f"Server error ({response.status_code}): {url}")
                retry_count += 1
                time.sleep(1)  # Wait longer before retrying
                continue
            else:
                print(f"HTTP error ({response.status_code}): {url}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"Timeout error downloading {url}")
            retry_count += 1
            time.sleep(1)
            continue
        except requests.exceptions.ConnectionError:
            print(f"Connection error downloading {url}")
            retry_count += 1
            time.sleep(1)
            continue
        except requests.exceptions.TooManyRedirects:
            print(f"Too many redirects for {url}")
            return None
        except Exception as e:
            print(f"Error downloading {url}: {str(e)}")
            return None
    
    if retry_count == max_retries:
        print(f"Max retries reached for {url}")
    
    return None

def get_asset_type(url):
    """Determine the type of asset from the URL"""
    # Handle empty or None URLs
    if not url:
        return 'other'
    
    url_lower = url.lower()
    
    # Framework-specific patterns
    if '_next/static' in url_lower:
        if '.css' in url_lower or 'styles' in url_lower:
            return 'css'
        return 'js'  # Default to JS for Next.js assets
        
    if 'chunk.' in url_lower or 'webpack' in url_lower:
        return 'js'  # Webpack chunks
        
    if 'angular' in url_lower and '.js' in url_lower:
        return 'js'  # Angular bundles
        
    # Handle CSS files
    if url_lower.endswith(('.css', '.scss', '.less', '.sass')):
        return 'css'
    if 'global.css' in url_lower or 'globals.css' in url_lower or 'tailwind' in url_lower:
        return 'css'
    if 'fonts.googleapis.com' in url_lower:
        return 'css'
    if 'styles' in url_lower and '.css' in url_lower:
        return 'css'
        
    # Handle JS files
    if url_lower.endswith(('.js', '.jsx', '.mjs', '.ts', '.tsx', '.cjs')):
        return 'js'
    if 'bundle.js' in url_lower or 'main.js' in url_lower or 'app.js' in url_lower:
        return 'js'
    if 'polyfill' in url_lower or 'runtime' in url_lower or 'vendor' in url_lower:
        return 'js'
    if 'image-config' in url_lower or 'image.config' in url_lower:
        return 'js'
        
    # Handle image files
    if url_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif', '.bmp', '.ico')):
        return 'img'
    if '/images/' in url_lower or '/img/' in url_lower or '/assets/images/' in url_lower:
        return 'img'
        
    # Handle font files
    if url_lower.endswith(('.woff', '.woff2', '.ttf', '.otf', '.eot')):
        return 'fonts'
    if '/fonts/' in url_lower or 'font-awesome' in url_lower:
        return 'fonts'
        
    # Handle media files
    if url_lower.endswith(('.mp4', '.webm', '.ogg', '.avi', '.mov', '.flv')):
        return 'videos'
    if url_lower.endswith(('.mp3', '.wav', '.ogg', '.aac')):
        return 'audio'
        
    # Handle favicon
    if url_lower.endswith(('.ico', '.icon')):
        return 'favicons'
    if 'favicon' in url_lower:
        return 'favicons'
        
    # Handle special API endpoints
    if 'graphql' in url_lower or 'api.' in url_lower:
        return 'js'
        
    # Try to guess based on URL structure
    if '/css/' in url_lower:
        return 'css'
    if '/js/' in url_lower or '/scripts/' in url_lower:
        return 'js'
    if '/static/' in url_lower and not any(ext in url_lower for ext in ['.css', '.js', '.png', '.jpg']):
        # For static assets with unclear type, check the URL itself
        if 'style' in url_lower:
            return 'css'
        return 'js'  # Default for static assets
        
    # For CDN resources, try to determine type from the host
    cdn_hosts = ['cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com']
    for host in cdn_hosts:
        if host in url_lower:
            if any(lib in url_lower for lib in ['react', 'angular', 'vue', 'jquery']):
                return 'js'
            if any(lib in url_lower for lib in ['bootstrap', 'tailwind', 'material', 'font']):
                return 'css'
    
    # Default to JS for unknown extensions
    return 'js'

def extract_metadata(soup, base_url):
    """Extract metadata from the HTML"""
    metadata = {
        'title': '',
        'description': '',
        'keywords': '',
        'og_tags': {},
        'twitter_cards': {},
        'canonical': '',
        'language': '',
        'favicon': '',
        'structured_data': []
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        metadata['title'] = title_tag.string.strip()
    
    # Extract meta tags
    meta_tags = soup.find_all('meta')
    for tag in meta_tags:
        # Description
        if tag.get('name') == 'description' and tag.get('content'):
            metadata['description'] = tag.get('content').strip()
        
        # Keywords
        elif tag.get('name') == 'keywords' and tag.get('content'):
            metadata['keywords'] = tag.get('content').strip()
        
        # OpenGraph tags
        elif tag.get('property') and tag.get('property').startswith('og:') and tag.get('content'):
            prop = tag.get('property')[3:]  # Remove 'og:' prefix
            metadata['og_tags'][prop] = tag.get('content').strip()
        
        # Twitter card tags
        elif tag.get('name') and tag.get('name').startswith('twitter:') and tag.get('content'):
            prop = tag.get('name')[8:]  # Remove 'twitter:' prefix
            metadata['twitter_cards'][prop] = tag.get('content').strip()
    
    # Extract canonical URL
    canonical_tag = soup.find('link', {'rel': 'canonical'})
    if canonical_tag and canonical_tag.get('href'):
        canonical_url = canonical_tag.get('href')
        if not canonical_url.startswith(('http://', 'https://')):
            canonical_url = urljoin(base_url, canonical_url)
        metadata['canonical'] = canonical_url
    
    # Extract language
    html_tag = soup.find('html')
    if html_tag and html_tag.get('lang'):
        metadata['language'] = html_tag.get('lang')
    
    # Extract favicon
    favicon_tag = soup.find('link', {'rel': 'icon'}) or soup.find('link', {'rel': 'shortcut icon'})
    if favicon_tag and favicon_tag.get('href'):
        favicon_url = favicon_tag.get('href')
        if not favicon_url.startswith(('http://', 'https://')):
            favicon_url = urljoin(base_url, favicon_url)
        metadata['favicon'] = favicon_url
    
    # Extract structured data (JSON-LD)
    script_tags = soup.find_all('script', {'type': 'application/ld+json'})
    for tag in script_tags:
        if tag.string:
            try:
                json_data = json.loads(tag.string)
                metadata['structured_data'].append(json_data)
            except json.JSONDecodeError:
                pass
    
    return metadata

def get_component_type(element):
    """Determine the type of UI component based on element attributes and classes"""
    if not element:
        return None
        
    # Get tag name, classes, and ID
    tag_name = element.name
    class_list = element.get('class', [])
    if class_list and not isinstance(class_list, list):
        class_list = [class_list]
    class_str = ' '.join(class_list).lower() if class_list else ''
    element_id = element.get('id', '').lower()
    
    # Get element role
    role = element.get('role', '').lower()
    
    # Navigation components
    if tag_name == 'nav' or role == 'navigation' or 'nav' in class_str or 'navigation' in class_str or 'menu' in class_str or element_id in ['nav', 'navigation', 'menu']:
        return 'navigation'
    
    # Header components
    if tag_name == 'header' or role == 'banner' or 'header' in class_str or 'banner' in class_str or element_id in ['header', 'banner']:
        return 'header'
    
    # Footer components
    if tag_name == 'footer' or role == 'contentinfo' or 'footer' in class_str or element_id == 'footer':
        return 'footer'
    
    # Hero/banner components
    if 'hero' in class_str or 'banner' in class_str or 'jumbotron' in class_str or 'showcase' in class_str or element_id in ['hero', 'banner', 'jumbotron', 'showcase']:
        return 'hero'
    
    # Card components
    if 'card' in class_str or 'tile' in class_str or 'item' in class_str or element_id in ['card', 'tile']:
        return 'card'
    
    # Form components
    if tag_name == 'form' or role == 'form' or 'form' in class_str or element_id == 'form':
        return 'form'
    
    # CTA (Call to Action) components
    if 'cta' in class_str or 'call-to-action' in class_str or 'action' in class_str or element_id in ['cta', 'call-to-action']:
        return 'cta'
    
    # Sidebar components
    if 'sidebar' in class_str or 'side-bar' in class_str or element_id in ['sidebar', 'side-bar']:
        return 'sidebar'
    
    # Modal/Dialog components
    if role == 'dialog' or 'modal' in class_str or 'dialog' in class_str or 'popup' in class_str or element_id in ['modal', 'dialog', 'popup']:
        return 'modal'
    
    # Section components
    if tag_name == 'section' or role == 'region' or 'section' in class_str:
        return 'section'
    
    # Mobile components
    if 'mobile' in class_str or 'smartphone' in class_str or 'mobile-only' in class_str:
        return 'mobile'
    
    # Store/Product components
    if 'product' in class_str or 'store' in class_str or 'shop' in class_str or 'pricing' in class_str:
        return 'store'
    
    # Cart components
    if 'cart' in class_str or 'basket' in class_str or 'shopping-cart' in class_str or element_id in ['cart', 'basket', 'shopping-cart']:
        return 'cart'
    
    # If no specific type is identified, check if the element is a major container
    if tag_name in ['div', 'section', 'article'] and ('container' in class_str or 'wrapper' in class_str or 'content' in class_str):
        return 'container'
    
    # Default to unknown if no specific type is identified
    return 'other'

def extract_component_structure(soup):
    """Extract UI components from the HTML structure"""
    if not soup:
        return {}
        
    components = {
        'navigation': [],
        'header': [],
        'footer': [],
        'hero': [],
        'card': [],
        'form': [],
        'cta': [],
        'sidebar': [],
        'modal': [],
        'section': [],
        'store': [],
        'mobile': [],
        'cart': []
    }
    
    # Helper function to convert element to HTML string
    def element_to_html(element):
        return str(element)
    
    # Extract navigation components
    nav_elements = soup.find_all(['nav']) + soup.find_all(role='navigation') + soup.find_all(class_=lambda c: c and ('nav' in c.lower() or 'menu' in c.lower()))
    for element in nav_elements[:5]:  # Limit to 5 to avoid excessive extraction
        components['navigation'].append({
            'html': element_to_html(element)
        })
    
    # Extract header components
    header_elements = soup.find_all(['header']) + soup.find_all(role='banner') + soup.find_all(class_=lambda c: c and 'header' in c.lower())
    for element in header_elements[:2]:  # Usually only 1-2 headers per page
        components['header'].append({
            'html': element_to_html(element)
        })
    
    # Extract footer components
    footer_elements = soup.find_all(['footer']) + soup.find_all(role='contentinfo') + soup.find_all(class_=lambda c: c and 'footer' in c.lower())
    for element in footer_elements[:2]:  # Usually only 1-2 footers per page
        components['footer'].append({
            'html': element_to_html(element)
        })
    
    # Extract hero/banner components
    hero_elements = soup.find_all(class_=lambda c: c and ('hero' in c.lower() or 'banner' in c.lower() or 'jumbotron' in c.lower()))
    for element in hero_elements[:3]:  # Limit to 3
        components['hero'].append({
            'html': element_to_html(element)
        })
    
    # Extract card components - often these are repeated elements
    card_elements = soup.find_all(class_=lambda c: c and ('card' in c.lower() or 'tile' in c.lower()))
    
    # If we find many cards, just keep one of each unique structure
    unique_cards = {}
    for element in card_elements[:15]:  # Examine up to 15 cards
        # Use a simplified structure hash to identify similar cards
        structure_hash = str(len(element.find_all()))  # Number of child elements
        if structure_hash not in unique_cards:
            unique_cards[structure_hash] = element
    
    # Add unique cards to components
    for idx, element in enumerate(unique_cards.values()):
        if idx >= 5:  # Limit to 5 unique cards
            break
        components['card'].append({
            'html': element_to_html(element)
        })
    
    # Extract form components
    form_elements = soup.find_all(['form']) + soup.find_all(class_=lambda c: c and 'form' in c.lower())
    for element in form_elements[:3]:  # Limit to 3
        components['form'].append({
            'html': element_to_html(element)
        })
    
    # Extract CTA components
    cta_elements = soup.find_all(class_=lambda c: c and ('cta' in c.lower() or 'call-to-action' in c.lower()))
    for element in cta_elements[:3]:  # Limit to 3
        components['cta'].append({
            'html': element_to_html(element)
        })
    
    # Extract sidebar components
    sidebar_elements = soup.find_all(class_=lambda c: c and ('sidebar' in c.lower() or 'side-bar' in c.lower()))
    for element in sidebar_elements[:2]:  # Limit to 2
        components['sidebar'].append({
            'html': element_to_html(element)
        })
    
    # Extract modal/dialog components
    modal_elements = soup.find_all(role='dialog') + soup.find_all(class_=lambda c: c and ('modal' in c.lower() or 'dialog' in c.lower() or 'popup' in c.lower()))
    for element in modal_elements[:3]:  # Limit to 3
        components['modal'].append({
            'html': element_to_html(element)
        })
    
    # Extract section components
    section_elements = soup.find_all(['section']) + soup.find_all(role='region')
    # Filter to get only substantial sections
    substantial_sections = [element for element in section_elements if len(element.find_all()) > 3]  # Must have at least 3 child elements
    for element in substantial_sections[:5]:  # Limit to 5
        components['section'].append({
            'html': element_to_html(element)
        })
    
    # Extract mobile-specific components
    mobile_elements = soup.find_all(class_=lambda c: c and ('mobile' in c.lower() or 'smartphone' in c.lower() or 'mobile-only' in c.lower()))
    for element in mobile_elements[:3]:  # Limit to 3
        components['mobile'].append({
            'html': element_to_html(element)
        })
    
    # Extract store/product components
    store_elements = soup.find_all(class_=lambda c: c and ('product' in c.lower() or 'store' in c.lower() or 'shop' in c.lower() or 'pricing' in c.lower()))
    for element in store_elements[:5]:  # Limit to 5
        components['store'].append({
            'html': element_to_html(element)
        })
    
    # Extract cart components
    cart_elements = soup.find_all(class_=lambda c: c and ('cart' in c.lower() or 'basket' in c.lower() or 'shopping-cart' in c.lower()))
    for element in cart_elements[:2]:  # Limit to 2
        components['cart'].append({
            'html': element_to_html(element)
        })
    
    # Remove empty component types
    return {k: v for k, v in components.items() if v}

def extract_inline_styles(soup):
    """Extract all inline styles from the HTML"""
    inline_styles = {}
    elements_with_style = soup.select('[style]')
    
    for i, element in enumerate(elements_with_style):
        style_content = element.get('style')
        if style_content:
            class_name = f'extracted-inline-style-{i}'
            inline_styles[class_name] = style_content
            # Add the class to the element
            element['class'] = element.get('class', []) + [class_name]
            # Remove the inline style
            del element['style']
    
    return inline_styles

def extract_inline_javascript(soup):
    """Extract inline JavaScript from HTML content"""
    inline_js = []
    # Find all script tags without src attribute (inline scripts)
    for script in soup.find_all('script'):
        if not script.get('src') and script.string:
            inline_js.append(script.string.strip())
    
    if inline_js:
        return '\n\n/* --- INLINE SCRIPTS --- */\n\n'.join(inline_js)
    return ""

def extract_assets(html_content, base_url, session_obj=None, headers=None):
    """
    Extract all assets (CSS, JS, images, fonts) from HTML content.
    
    Args:
        html_content: HTML content as string
        base_url: Base URL for resolving relative paths
        session_obj: Optional requests session object
        headers: Optional headers for requests
        
    Returns:
        dict: Dictionary containing extracted assets by type
    """
    if not html_content:
        return {}
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        assets = {
            'css': [],
            'js': [],
            'images': [],
            'fonts': [],
            'other': []
        }
        
        # Extract CSS files
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href:
                try:
                    url = urljoin(base_url, href)
                    content = download_asset(url, base_url, headers, session_obj)
                    if content:
                        assets['css'].append({
                            'url': url,
                            'content': content,
                            'original_path': href
                        })
                except Exception as e:
                    print(f"Warning: Failed to extract CSS from {href}: {str(e)}")
        
        # Extract inline CSS
        for style in soup.find_all('style'):
            if style.string:
                assets['css'].append({
                    'url': None,
                    'content': style.string,
                    'original_path': 'inline'
                })
        
        # Extract JavaScript files
        for script in soup.find_all('script', src=True):
            src = script.get('src')
            if src:
                try:
                    url = urljoin(base_url, src)
                    content = download_asset(url, base_url, headers, session_obj)
                    if content:
                        assets['js'].append({
                            'url': url,
                            'content': content,
                            'original_path': src
                        })
                except Exception as e:
                    print(f"Warning: Failed to extract JS from {src}: {str(e)}")
        
        # Extract inline JavaScript
        for script in soup.find_all('script'):
            if script.string and not script.get('src'):
                assets['js'].append({
                    'url': None,
                    'content': script.string,
                    'original_path': 'inline'
                })
        
        # Extract images
        for img in soup.find_all(['img', 'source']):
            src = img.get('src') or img.get('srcset')
            if src:
                try:
                    # Handle srcset
                    if 'srcset' in img.attrs:
                        srcset = img['srcset'].split(',')
                        for src_item in srcset:
                            url = src_item.strip().split(' ')[0]
                            url = urljoin(base_url, url)
                            content = download_asset(url, base_url, headers, session_obj)
                            if content:
                                assets['images'].append({
                                    'url': url,
                                    'content': content,
                                    'original_path': src_item.strip()
                                })
                    else:
                        url = urljoin(base_url, src)
                        content = download_asset(url, base_url, headers, session_obj)
                        if content:
                            assets['images'].append({
                                'url': url,
                                'content': content,
                                'original_path': src
                            })
                except Exception as e:
                    print(f"Warning: Failed to extract image from {src}: {str(e)}")
        
        # Extract fonts
        for font in soup.find_all(['link', 'style']):
            if font.name == 'link' and 'font' in font.get('rel', []):
                href = font.get('href')
                if href:
                    try:
                        url = urljoin(base_url, href)
                        content = download_asset(url, base_url, headers, session_obj)
                        if content:
                            assets['fonts'].append({
                                'url': url,
                                'content': content,
                                'original_path': href
                            })
                    except Exception as e:
                        print(f"Warning: Failed to extract font from {href}: {str(e)}")
            
            # Extract @font-face declarations
            if font.name == 'style' and font.string:
                try:
                    font_faces = re.findall(r'@font-face\s*{([^}]*)}', font.string)
                    for font_face in font_faces:
                        src_match = re.search(r'src:\s*url\(([^)]+)\)', font_face)
                        if src_match:
                            font_url = src_match.group(1).strip('"\'').strip()
                            url = urljoin(base_url, font_url)
                            content = download_asset(url, base_url, headers, session_obj)
                            if content:
                                assets['fonts'].append({
                                    'url': url,
                                    'content': content,
                                    'original_path': font_url
                                })
                except Exception as e:
                    print(f"Warning: Failed to extract @font-face: {str(e)}")
        
        # Extract other assets (videos, audio, etc.)
        for media in soup.find_all(['video', 'audio', 'source']):
            src = media.get('src')
            if src:
                try:
                    url = urljoin(base_url, src)
                    content = download_asset(url, base_url, headers, session_obj)
                    if content:
                        assets['other'].append({
                            'url': url,
                            'content': content,
                            'original_path': src,
                            'type': media.name
                        })
                except Exception as e:
                    print(f"Warning: Failed to extract media from {src}: {str(e)}")
        
        return assets
        
    except Exception as e:
        print(f"Error in extract_assets: {str(e)}")
        traceback.print_exc()
        return {}

def create_zip_file(html_content, assets, url, session_obj, headers, screenshots=None):
    """
    Create a ZIP file containing all extracted assets.
    
    Args:
        html_content: Main HTML content
        assets: Dictionary of extracted assets
        url: Original URL
        session_obj: Requests session object
        headers: Headers for requests
        screenshots: Optional screenshots
        
    Returns:
        str: Path to the created ZIP file
    """
    try:
        # Create a temporary directory for the files
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, 'website.zip')
        
        # Create a ZIP file with compression
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            # Add main HTML file
            zip_file.writestr('index.html', html_content)
            
            # Create directories for different asset types
            asset_dirs = {
                'css': 'assets/css',
                'js': 'assets/js',
                'images': 'assets/images',
                'fonts': 'assets/fonts',
                'other': 'assets/other'
            }
            
            # Track used filenames to avoid duplicates
            used_filenames = set()
            
            # Add assets to ZIP file
            for asset_type, asset_list in assets.items():
                if asset_type in asset_dirs:
                    dir_path = asset_dirs[asset_type]
                    
                    for asset in asset_list:
                        try:
                            if isinstance(asset, dict) and 'content' in asset:
                                content = asset['content']
                                if content:
                                    # Generate a unique filename
                                    original_path = asset.get('original_path', '')
                                    filename = os.path.basename(original_path)
                                    if not filename:
                                        filename = f"asset_{uuid.uuid4().hex[:8]}"
                                    
                                    # Add file extension if missing
                                    if '.' not in filename:
                                        ext = mimetypes.guess_extension(asset.get('type', ''))
                                        if ext:
                                            filename += ext
                                    
                                    # Handle duplicate filenames
                                    base_name, ext = os.path.splitext(filename)
                                    counter = 1
                                    while filename in used_filenames:
                                        filename = f"{base_name}_{counter}{ext}"
                                        counter += 1
                                    used_filenames.add(filename)
                                    
                                    # Create full path
                                    file_path = os.path.join(dir_path, filename)
                                    
                                    # Handle large files
                                    if isinstance(content, bytes) and len(content) > 10 * 1024 * 1024:  # 10MB
                                        # For large files, write to a temporary file first
                                        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                                            temp_file.write(content)
                                            zip_file.write(temp_file.name, file_path)
                                            os.unlink(temp_file.name)
                                    else:
                                        zip_file.writestr(file_path, content)
                        except Exception as e:
                            print(f"Warning: Failed to add {asset_type} asset to ZIP: {str(e)}")
            
            # Add screenshots if available
            if screenshots:
                for name, screenshot in screenshots.items():
                    try:
                        if isinstance(screenshot, bytes):
                            zip_file.writestr(f'screenshots/{name}.png', screenshot)
                    except Exception as e:
                        print(f"Warning: Failed to add screenshot {name}: {str(e)}")
            
            # Add metadata
            metadata = {
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'asset_counts': {k: len(v) for k, v in assets.items()}
            }
            zip_file.writestr('metadata.json', json.dumps(metadata, indent=2))
        
        return zip_path
        
    except Exception as e:
        print(f"Error creating ZIP file: {str(e)}")
        traceback.print_exc()
        return None

def extract_with_selenium(url, timeout=30):
    """
    Extract rendered HTML content using Selenium with Chrome/Chromium.
    This method will execute JavaScript and capture the fully rendered page structure.
    
    Args:
        url: URL to fetch
        timeout: Maximum time to wait for page to load (seconds)
        
    Returns:
        tuple: (html_content, discovered_urls, None)
    """
    if not SELENIUM_AVAILABLE:
        return None, None, {"error": "Selenium is not installed. Run: pip install selenium webdriver-manager"}
    
    try:
        print("Setting up advanced Chrome options...")
        # Set up Chrome options with anti-detection measures
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # Use new headless mode
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")  # Improve performance
        chrome_options.add_argument("--disable-site-isolation-trials")
        chrome_options.add_argument("--disable-web-security")  # Allow cross-origin requests
        chrome_options.add_argument("--allow-running-insecure-content")
        
        # Advanced anti-detection measures
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Add modern user agent and additional headers
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        
        # Initialize the Chrome driver with retry mechanism
        max_retries = 3
        retry_count = 0
        driver = None
        
        while retry_count < max_retries:
            try:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                break
            except Exception as e:
                retry_count += 1
                print(f"Attempt {retry_count} failed: {str(e)}")
                if retry_count == max_retries:
                    print("All retry attempts failed. Trying alternative initialization...")
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                    except Exception as alt_error:
                        return None, None, {"error": f"Failed to initialize Chrome WebDriver: {str(alt_error)}"}
                time.sleep(2)  # Wait before retrying
        
        # Set page load timeout and script timeout
        driver.set_page_load_timeout(timeout)
        driver.set_script_timeout(timeout)
        
        # Used to store discovered URLs
        discovered_urls = []
        
        try:
            print(f"Navigating to {url}...")
            driver.get(url)
            
            # Wait for page to be fully loaded with multiple conditions
            try:
                WebDriverWait(driver, timeout).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception as e:
                print(f"Warning: Timeout waiting for page load: {str(e)}")
            
            # Execute JavaScript to improve performance and disable animations
            try:
                driver.execute_script("""
                    // Disable animations and transitions
                    var style = document.createElement('style');
                    style.type = 'text/css';
                    style.innerHTML = '* { animation-duration: 0.001s !important; transition-duration: 0.001s !important; }';
                    document.getElementsByTagName('head')[0].appendChild(style);
                    
                    // Force layout recalculation
                    document.body.offsetHeight;
                    
                    // Wait for any pending network requests
                    return new Promise((resolve) => {
                        if (window.performance && window.performance.getEntriesByType) {
                            const resources = window.performance.getEntriesByType('resource');
                            const pending = resources.filter(r => !r.responseEnd);
                            if (pending.length === 0) {
                                resolve();
                            } else {
                                setTimeout(resolve, 1000);
                            }
                        } else {
                            resolve();
                        }
                    });
                """)
            except Exception as e:
                print(f"Warning: JavaScript execution failed: {str(e)}")
            
            # Wait for page to be fully rendered
            print("Waiting for dynamic content to load...")
            try:
                # Wait a bit for any dynamic content to load
                time.sleep(5)
                
                # Wait for network to be idle
                driver.execute_script("return window.performance.getEntriesByType('resource').length")
                time.sleep(2)  # Wait a bit more after resources are loaded
            except Exception as e:
                print(f"Warning while waiting for dynamic content: {str(e)}")
            
            # Implement advanced scrolling to trigger lazy loading
            print("Performing advanced scrolling to trigger lazy loading...")
            try:
                # Get the total height of the page
                total_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, document.body.offsetHeight, document.documentElement.offsetHeight, document.body.clientHeight, document.documentElement.clientHeight);")
                
                # Scroll down the page in steps
                viewport_height = driver.execute_script("return window.innerHeight")
                scroll_steps = max(1, min(20, total_height // viewport_height))  # Cap at 20 steps
                
                for i in range(scroll_steps + 1):
                    scroll_position = (i * total_height) // scroll_steps
                    driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                    
                    # Small pause to allow content to load
                    time.sleep(0.3)
                    
                    # Extract resources after each scroll
                    try:
                        urls = driver.execute_script("""
                            var resources = [];
                            // Get all link hrefs
                            document.querySelectorAll('link[rel="stylesheet"], link[as="style"]').forEach(function(el) {
                                if (el.href) resources.push(el.href);
                            });
                            // Get all script srcs
                            document.querySelectorAll('script[src]').forEach(function(el) {
                                if (el.src) resources.push(el.src);
                            });
                            // Get all image srcs
                            document.querySelectorAll('img[src]').forEach(function(el) {
                                if (el.src && !el.src.startsWith('data:')) resources.push(el.src);
                            });
                            return resources;
                        """)
                        discovered_urls.extend(urls)
                    except Exception as res_error:
                        print(f"Error extracting resources during scroll: {str(res_error)}")
                
                # Scroll back to top
                driver.execute_script("window.scrollTo(0, 0);")
                
                # Wait for everything to settle after scrolling
                time.sleep(1)
            except Exception as scroll_error:
                print(f"Error during page scrolling: {str(scroll_error)}")
            
            # Try to click on common elements that might reveal more content
            try:
                # Common UI elements that might reveal more content when clicked
                for selector in [
                    'button.load-more', '.show-more', '.expand', '.accordion-toggle', 
                    '[aria-expanded="false"]', '.menu-toggle', '.navbar-toggler',
                    '.mobile-menu-button', '.hamburger', '[data-toggle="collapse"]'
                ]:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements[:3]:  # Limit to first 3 matches of each type
                            if element.is_displayed():
                                driver.execute_script("arguments[0].click();", element)
                                time.sleep(0.5)  # Wait for content to appear
                    except Exception as click_error:
                        # Skip any errors and continue with next selector
                        continue
                print("Attempted to expand hidden content")
            except Exception as interact_error:
                print(f"Error expanding content: {str(interact_error)}")
            
            # Get the final HTML content after all JavaScript executed
            html_content = driver.page_source
            print(f"HTML content captured ({len(html_content)} bytes)")
            
            # Extract URLs for modern frameworks
            try:
                # React/Next.js specific resources
                next_js_urls = driver.execute_script("""
                    var resources = [];
                    // Find Next.js specific scripts
                    document.querySelectorAll('script[src*="_next"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    // Find chunk files
                    document.querySelectorAll('script[src*="chunk"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    // Find webpack files
                    document.querySelectorAll('script[src*="webpack"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    // Find hydration scripts
                    document.querySelectorAll('script[src*="hydration"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    return resources;
                """)
                discovered_urls.extend(next_js_urls)
                
                # Angular specific resources
                angular_urls = driver.execute_script("""
                    var resources = [];
                    // Find Angular specific scripts
                    document.querySelectorAll('script[src*="runtime"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    document.querySelectorAll('script[src*="polyfills"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    document.querySelectorAll('script[src*="main"]').forEach(function(el) {
                        resources.push(el.src);
                    });
                    return resources;
                """)
                discovered_urls.extend(angular_urls)
                
                # Get CSS variables for Tailwind detection
                tailwind_check = driver.execute_script("""
                    var style = window.getComputedStyle(document.body);
                    var hasTailwind = false;
                    // Check for common Tailwind classes
                    if (document.querySelector('.flex') && 
                        document.querySelector('.grid') && 
                        document.querySelector('.text-')) {
                        hasTailwind = true;
                    }
                    return hasTailwind;
                """)
                
                if tailwind_check:
                    print("Tailwind CSS detected, including appropriate CSS files")
            except Exception as framework_error:
                print(f"Error detecting framework resources: {str(framework_error)}")
            
            # Remove duplicates from discovered URLs
            discovered_urls = list(set(discovered_urls))
            print(f"Discovered {len(discovered_urls)} resource URLs")
            
            return html_content, discovered_urls, None
            
        except TimeoutException:
            print(f"Timeout while loading {url}")
            return None, None, {"error": "Timeout while loading page"}
        except WebDriverException as e:
            print(f"Selenium error: {str(e)}")
            return None, None, {"error": f"Selenium error: {str(e)}"}
        finally:
            # Close the browser
            print("Closing WebDriver...")
            driver.quit()
    
    except Exception as e:
        print(f"Error setting up Selenium: {str(e)}")
        return None, None, {"error": f"Error setting up Selenium: {str(e)}"}

def fix_relative_urls(html_content, base_url):
    """Fix relative URLs in the HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Fix relative URLs for links
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('/'):
            link['href'] = urljoin(base_url, href)
    
    # Fix relative URLs for images
    for img in soup.find_all('img', src=True):
        src = img['src']
        if not src.startswith(('http://', 'https://', 'data:')):
            img['src'] = urljoin(base_url, src)
    
    # Fix relative URLs for scripts
    for script in soup.find_all('script', src=True):
        src = script['src']
        if not src.startswith(('http://', 'https://', 'data:')):
            script['src'] = urljoin(base_url, src)
    
    # Fix relative URLs for stylesheets
    for link in soup.find_all('link', href=True):
        href = link['href']
        if not href.startswith(('http://', 'https://', 'data:')):
            link['href'] = urljoin(base_url, href)
    
    return str(soup)

@app.route('/')
def index():
    """Render the home page"""
    return render_template('index.html')

@app.route('/clear')
def clear_session():
    """Clear the session data"""
    session.clear()
    return jsonify({'message': 'Session cleared'})

@app.route('/extract', methods=['POST'])
def extract():
    url = request.form.get('url')
    use_selenium = request.form.get('use_selenium') == 'true'
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        # Add http:// if not present
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        print(f"\n{'='*80}\nStarting extraction for: {url}\n{'='*80}")
        
        # Create a session to maintain cookies
        session_obj = requests.Session()
        
        # Disable SSL verification warnings
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Use Selenium for rendering if requested and available
        if use_selenium and SELENIUM_AVAILABLE:
            print("Using Selenium for advanced rendering...")
            html_content, additional_urls, error_info = extract_with_selenium(url)
            
            if not html_content:
                print("Selenium extraction failed, falling back to regular request")
                use_selenium = False
        
        # Safety check - make sure we have HTML content
        if not html_content or len(html_content) < 100:
            return jsonify({'error': 'Failed to extract valid HTML content from the website'}), 400
        
        try:
            print("\nExtracting assets...")
            # Extract assets from the HTML content
            assets = extract_assets(html_content, url, session_obj, None)
            
            if not assets:
                return jsonify({'error': 'Failed to extract assets from the website'}), 500
            
            # Try to fix relative URLs in the HTML
            try:
                print("\nFixing relative URLs...")
                fixed_html = fix_relative_urls(html_content, url)
                print("Relative URLs fixed")
            except Exception as e:
                print(f"Error fixing URLs: {str(e)}")
                fixed_html = html_content
            
            try:
                # Create zip file in memory
                print("\nCreating zip file in memory...")
                zip_buffer = BytesIO()
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
                    # Add main HTML file
                    zip_file.writestr('index.html', fixed_html)
                    
                    # Create directories for different asset types
                    asset_dirs = {
                        'css': 'assets/css',
                        'js': 'assets/js',
                        'images': 'assets/images',
                        'fonts': 'assets/fonts',
                        'other': 'assets/other'
                    }
                    
                    # Track used filenames to avoid duplicates
                    used_filenames = set()
                    
                    # Add assets to ZIP file
                    for asset_type, asset_list in assets.items():
                        if asset_type in asset_dirs:
                            dir_path = asset_dirs[asset_type]
                            
                            for asset in asset_list:
                                if isinstance(asset, dict) and 'content' in asset:
                                    content = asset['content']
                                    if content:
                                        try:
                                            # Generate filename
                                            original_path = asset.get('original_path', '')
                                            filename = os.path.basename(original_path)
                                            if not filename:
                                                filename = f"asset_{uuid.uuid4().hex[:8]}"
                                            
                                            # Add extension if missing
                                            if '.' not in filename:
                                                ext = mimetypes.guess_extension(asset.get('type', ''))
                                                if ext:
                                                    filename += ext
                                            
                                            # Handle duplicates
                                            base_name, ext = os.path.splitext(filename)
                                            counter = 1
                                            while filename in used_filenames:
                                                filename = f"{base_name}_{counter}{ext}"
                                                counter += 1
                                            used_filenames.add(filename)
                                            
                                            # Create full path and add to zip
                                            file_path = os.path.join(dir_path, filename)
                                            zip_file.writestr(file_path, content)
                                        except Exception as e:
                                            print(f"Warning: Failed to add {asset_type} asset to ZIP: {str(e)}")
                    
                    # Add metadata
                    metadata = {
                        'url': url,
                        'timestamp': datetime.now().isoformat(),
                        'asset_counts': {k: len(v) for k, v in assets.items()}
                    }
                    zip_file.writestr('metadata.json', json.dumps(metadata, indent=2))
                
                # Prepare zip file for download
                zip_buffer.seek(0)
                
                # Extract domain from URL for the filename
                domain = urlparse(url).netloc
                safe_domain = re.sub(r'[^\w\-_]', '_', domain)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{safe_domain}_{timestamp}.zip"
                
                # Send the file with proper headers
                response = send_file(
                    zip_buffer,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=filename
                )
                
                # Add headers to prevent caching
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                
                return response
                
            except Exception as e:
                print(f"Error creating zip file: {str(e)}")
                traceback.print_exc()
                return jsonify({'error': f'Failed to create zip file: {str(e)}'}), 500
                
        except Exception as e:
            print(f"Error in asset extraction: {str(e)}")
            traceback.print_exc()
            return jsonify({'error': f'Error extracting assets: {str(e)}'}), 500
            
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*80)
    print("Website Extractor is running!")
    print("Access it in your browser at: http://127.0.0.1:5002")
    print("="*80 + "\n")
    app.run(debug=True, threaded=True, port=5002) 

def main():
    """Entry point for the package, to allow running as an installed package from command line"""
    print("\n" + "="*80)
    print("Website Extractor is running!")
    print("Access it in your browser at: http://127.0.0.1:5002")
    print("="*80 + "\n")
    app.run(debug=True, threaded=True, port=5002) 