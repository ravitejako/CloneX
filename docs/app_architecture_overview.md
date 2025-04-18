# Website Extractor Architecture Overview

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

## Data Flow

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

### Key Components

1. **Flask Web Server**: The user interface and API endpoint
2. **HTTP Client**: Makes network requests to target websites
3. **Selenium Renderer**: Renders JavaScript-heavy sites (optional)
4. **Content Parser**: Analyzes HTML to extract assets
5. **Asset Downloader**: Retrieves all website assets
6. **Zip Creator**: Packages everything into a downloadable archive

For more detailed information, see the full [app_architecture.md](../app_architecture.md) file. 