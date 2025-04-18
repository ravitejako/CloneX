# Website Extractor - Application Architecture

## Overview

This document provides a high-level overview of the Website Extractor application architecture, explaining how the different components interact and the flow of data through the system.

```
┌───────────────────────────────────────────────────────────────────┐
│                    Website Extractor Application                   │
└───────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│                           Flask Web Server                         │
└───────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│                      Extraction Core Processes                     │
├───────────────┬──────────────────┬──────────────────┬─────────────┤
│  HTTP Client  │ Selenium Renderer │  Content Parser  │ Asset Saver │
│ (requests)    │ (WebDriver)       │ (BeautifulSoup)  │ (Zip)       │
└───────────────┴──────────────────┴──────────────────┴─────────────┘
```

## Data Flow Diagram

```
┌──────────┐    URL     ┌──────────┐  HTML Content  ┌──────────────┐
│  User    │───────────▶│ Extractor│───────────────▶│ HTML Parser  │
└──────────┘            └──────────┘                └──────────────┘
                             │                             │
                   Rendering │                             │ Asset URLs
                     option  │                             │
                             ▼                             ▼
                      ┌──────────┐                  ┌──────────────┐
                      │ Selenium │                  │ Asset        │
                      │ WebDriver│                  │ Downloader   │
                      └──────────┘                  └──────────────┘
                             │                             │
                     Rendered│                      Assets │
                       HTML  │                             │
                             ▼                             ▼
                      ┌──────────────────────────────────────────┐
                      │            Zip File Creator              │
                      └──────────────────────────────────────────┘
                                          │
                                          ▼
                      ┌──────────────────────────────────────────┐
                      │      File Download Response to User      │
                      └──────────────────────────────────────────┘
```

## Component Descriptions

### 1. Flask Web Server
- **Purpose**: Provides the web interface and handles HTTP requests
- **Key Files**: `app.py` (main file), `templates/index.html` (UI)
- **Functions**: Serves the interface, processes form submissions, returns downloaded files

### 2. HTTP Client (Requests)
- **Purpose**: Fetches website content using standard HTTP requests
- **Key Functions**: `download_asset()`, HTTP request code in `/extract` route
- **Features**: Cookie handling, header rotation, retry logic, error handling

### 3. Selenium Renderer (Optional)
- **Purpose**: Renders JavaScript-heavy websites using a headless Chrome browser
- **Key Functions**: `extract_with_selenium()`
- **Features**: Waits for dynamic content, scrolls the page, handles lazy loading, identifies framework-specific resources

### 4. Content Parser
- **Purpose**: Analyzes HTML content to extract assets and structure
- **Key Functions**: `extract_assets()`, `extract_metadata()`, `extract_component_structure()`
- **Features**: Identifies CSS, JS, images, fonts, extracts metadata, identifies UI components

### 5. Asset Downloader
- **Purpose**: Downloads all discovered assets
- **Key Functions**: `download_asset()` 
- **Features**: Handles different asset types, resolves relative URLs, manages retries

### 6. Zip File Creator
- **Purpose**: Packages all assets into a downloadable zip file
- **Key Functions**: `create_zip_file()`
- **Features**: Organizes assets by type, handles file naming, adds metadata and documentation

## Process Flow

1. **User Submits URL**:
   - User enters a URL in the web interface
   - Optionally selects "Use Advanced Rendering (Selenium)"
   - Submits the form to the `/extract` endpoint

2. **Content Acquisition**:
   - If Selenium is selected: Uses Chrome WebDriver to render the page
   - Otherwise: Uses Requests library for HTTP retrieval
   - Handles redirects, errors, retries with different headers

3. **HTML Processing**:
   - Parses HTML using BeautifulSoup
   - Fixes relative URLs
   - Extracts metadata (title, description, etc.)
   - Identifies UI components

4. **Asset Discovery**:
   - Finds all linked resources (CSS, JS, images, fonts, etc.)
   - Resolves URLs
   - Categorizes assets by type
   - Handles duplicates

5. **Asset Download**:
   - Downloads all discovered assets
   - Handles binary vs. text content
   - Manages errors and retries

6. **Zip Creation**:
   - Creates organized folder structure
   - Adds README and metadata
   - Creates component index
   - Packages everything into a ZIP file

7. **User Download**:
   - Returns the ZIP file as a downloadable attachment
   - Manages temporary file cleanup

## Challenges & Error Patterns

### Common Failure Points

1. **Selenium WebDriver Initialization**:
   - Error seen in logs: `Error initializing Chrome WebDriver: [Errno 8] Exec format error`
   - Cause: WebDriver executable permission or architecture mismatch
   - Fallback: Alternative initialization method is attempted

2. **CDN and Image Processing URLs**:
   - Error seen: `Failed to download https://www.tesla.com/q_auto/Homepage-New-Legacy-Model-Y-Desktop.png, status: 404`
   - Cause: URLs contain transformation parameters (`q_auto`, `f_auto`) that are processed by CDNs and don't represent actual file paths

3. **Theme and Framework Resources**:
   - Error seen: `Failed to download https://www.tesla.com/themes/contrib/stable/images/core/throbber-active.gif, status: 404`
   - Cause: Theme resources may be generated dynamically or have access restrictions

4. **Anti-Bot Measures**:
   - Some sites implement anti-scraping measures (403 Forbidden responses)
   - Application implements header rotation and Selenium fallback to mitigate this

## Improvement Opportunities

1. **URL Processing**: Enhance the URL normalization to better handle CDN-specific parameters
2. **Asset Deduplication**: Improve handling of duplicate assets with different query parameters
3. **Error Handling**: Add more targeted error handling for specific CDN formats
4. **WebDriver Management**: Improve Selenium WebDriver initialization reliability

## Technical Dependencies

- **Flask**: Web framework
- **Requests**: HTTP client
- **BeautifulSoup**: HTML parsing
- **Selenium**: Browser automation
- **cssutils**: CSS parsing
- **zipfile**: ZIP file creation 