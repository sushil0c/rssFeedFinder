# RSS Feed & Category Finder — Accessible RSS/Atom Feed Discovery & News Reader Add-on for NVDA

[![NVDA Compatibility](https://img.shields.io/badge/NVDA-2021.1%20--%202026.2-blue)](https://www.nvaccess.org/)
[![Version](https://img.shields.io/badge/version-2.1.0-green)](../../releases)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-orange.svg)](LICENSE)

**RSS Feed & Category Finder (`rssFeedFinder`)** is a free, open-source **NVDA screen reader add-on** that automatically discovers hidden **RSS, Atom, and XML feeds** on any website, organizes sub-category feeds by topic, and lets you read news articles directly inside NVDA without browser clutter.

Most modern websites, blogs, and news portals still publish RSS and Atom feeds, but they rarely display a visible "RSS" button anymore. Feed links are buried inside HTML source code, WordPress endpoints, or scattered across dozens of category pages. For blind and visually impaired screen reader users, navigating ad-heavy news websites just to check the latest headlines or find a working feed URL can be slow and frustrating.

**RSS Feed & Category Finder** fixes this. Enter any website address, and it tracks down both the main RSS feed and topic-specific category feeds (such as *Sports, Technology, Health, Business, Politics,* or *Entertainment*) in seconds—allowing you to copy feed URLs for your favorite RSS client or read clean article summaries right inside NVDA.

---

## Why You Need This NVDA Add-on (Problems It Solves)

- **No More Hunting Through Page Source:** You don't need to inspect HTML code or guess `/feed`, `/rss.xml`, or `/atom.xml` paths manually. Just type a domain like `bbc.com/news`, `onlinekhabar.com`, `setopati.com`, or `techcrunch.com` and press `Enter`.
- **Uncovers Hidden Category & Topic Feeds:** Many news portals provide separate RSS feeds for individual sections. This add-on automatically crawls navigation and category links to find topic-specific feeds and groups them neatly by category.
- **Distraction-Free Accessible News Reader:** Want to read headlines without popups, banners, or autoplay ads? Select any discovered or saved feed to read article titles, publication dates, and clean text summaries directly inside an accessible NVDA dialog.
- **Works With International & Non-English Websites:** Built with Unicode-safe URL handling (supporting Nepali, Hindi, Arabic, CJK, and other non-Latin scripts), gzip/deflate decompression, and resilient SSL handling.
- **Bulk Feed Discovery for Curators & Developers:** Have a JSON file with hundreds of websites? Use the built-in multi-threaded Batch Checker to scan them all at once and export a categorized JSON report of working RSS/Atom feeds.

---

## Key Features

- **Smart RSS, Atom & RDF Feed Detection:** Automatically checks HTML `<link>` tags, common CMS feed endpoints (WordPress, Blogger, Ghost, Medium, Substack, custom XML), and site sub-pages.
- **Automatic Topic Categorization:** Classifies feeds into intuitive categories: *General News, Technology, Sports, Business & Economy, Health, Lifestyle, Entertainment, Education, Politics, Opinion,* and *World*.
- **Category Filter & One-Click Clipboard Copy:** Filter discovered feeds by topic and copy either a single feed URL (`Alt+C`) or all feed URLs in a category (`Alt+A`).
- **Built-in Accessible Article Reader:** Browse recent posts from any feed, read the full summary in a screen-reader-friendly text box, or open the original article in your web browser (`Alt+O`).
- **Saved Favorite Feeds Manager:** Bookmark your favorite RSS feeds (`Alt+S`) so your personal news list is ready every time you open NVDA.
- **Batch JSON Feed Scanner:** Import any JSON list of websites and export a structured report of verified feeds grouped by category.

---

## Keyboard Shortcuts & Commands

### Global NVDA Shortcut
- **`NVDA + Control + Shift + F`**: Open the **RSS Feed & Category Finder** dialog from anywhere in Windows.
- Also accessible via **NVDA Menu -> Tools -> RSS Feed & Category Finder...**

### Dialog Shortcuts
| Shortcut | Action |
| :--- | :--- |
| **`Enter`** *(in URL field)* | Discover primary and sub-category RSS/Atom feeds for the website |
| **`Alt + C`** | Copy the selected feed URL to the clipboard |
| **`Alt + A`** | Copy all feed URLs in the currently selected category |
| **`Alt + S`** | Save the selected feed to your Favorites list |
| **`Alt + D`** | Delete the selected feed from your Favorites list |
| **`Alt + R`** / **`Enter`** | Load and read recent articles from the selected feed |
| **`Alt + O`** | Open the selected article in your default web browser |
| **`Alt + U`** | Copy the selected article's web URL |
| **`Alt + B`** | Batch-check a JSON file of websites and export categorized feeds |
| **`Alt + H`** | Open the built-in add-on help documentation |
| **`Escape`** | Close the dialog |

---

## How to Install in NVDA

### Option 1: From the NVDA Add-on Store
1. Open **NVDA Menu -> Tools -> Add-on Store**.
2. Search for **RSS Feed & Category Finder** (`rssFeedFinder`).
3. Select **Install** and restart NVDA when prompted.

### Option 2: Manual Installation (`.nvda-addon` Package)
1. Download **[rssFeedFinder.nvda-addon](rssFeedFinder.nvda-addon)** from this repository or the [Releases](../../releases) page.
2. Press `Enter` on the downloaded `rssFeedFinder.nvda-addon` file.
3. Choose **Yes** to confirm installation in NVDA and restart NVDA.

---

## Frequently Asked Questions (FAQ)

**Q: Can I use this add-on both to find feed URLs for another RSS app and to read news inside NVDA?**  
Yes. You can copy any discovered RSS/Atom URL with `Alt+C` to paste into Thunderbird, NetNewsWire, Feedly, or any other RSS reader, or press `Alt+R` to read the feed's articles directly inside NVDA.

**Q: Does it support WordPress, Blogger, and custom news portals?**  
Yes. It detects standard `<link rel="alternate">` tags as well as WordPress (`/feed/`, `/?feed=rss2`), Blogger (`/feeds/posts/default`), Atom (`/atom.xml`), and custom category XML endpoints.

---

## Add-on Specifications

- **Add-on ID / Name:** `rssFeedFinder`
- **Summary:** RSS Feed & Category Finder
- **Current Version:** 2.1.0
- **Minimum NVDA Version:** 2021.1.0
- **Last Tested NVDA Version:** 2026.2.0
- **Author:** Sushil Chaudhary ([https://sushil0.com.np](https://sushil0.com.np))
- **License:** GNU General Public License v2.0 (see [LICENSE](LICENSE))
