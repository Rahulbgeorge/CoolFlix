import urllib.parse
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from pydantic import BaseModel
from .cleaner import FileNameCleaner

class ParseURLInput(BaseModel):
    url: str

class ParsedMagnetLink(BaseModel):
    magnet_link: str
    title: str
    original_name: Optional[str] = None
    size: Optional[str] = None
    resolution: Optional[str] = None
    quality: Optional[str] = None
    codec: Optional[str] = None
    languages: List[str] = []

class ParseURLOutput(BaseModel):
    page_title: str
    magnets: List[ParsedMagnetLink]

class MagnetParser:
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }

    @classmethod
    def parse_magnet_link(cls, magnet_link: str, fallback_title: str) -> ParsedMagnetLink:
        """Parses a single magnet link and extracts title and details."""
        original_name = None
        size = None
        resolution = None
        quality = None
        codec = None
        languages = []
        
        # Decode display name from magnet URL (dn query parameter)
        try:
            parsed_query = urllib.parse.parse_qs(urllib.parse.urlparse(magnet_link).query)
            dn_list = parsed_query.get('dn', [])
            if dn_list:
                original_name = dn_list[0]
        except Exception:
            pass

        if original_name:
            # We have a display name. We can run our FileNameCleaner on it to parse details!
            clean_info = FileNameCleaner.clean(original_name)
            
            # Construct a clean title using the parsed parts
            title_parts = [clean_info.cleaned_name]
            if clean_info.year:
                title_parts.append(f"({clean_info.year})")
            if clean_info.season:
                title_parts.append(clean_info.season)
            if clean_info.episode:
                title_parts.append(clean_info.episode)
                
            badges = []
            if clean_info.resolution:
                badges.append(clean_info.resolution.upper())
                resolution = clean_info.resolution
            if clean_info.quality:
                badges.append(clean_info.quality)
                quality = clean_info.quality
            if clean_info.size:
                badges.append(clean_info.size)
                size = clean_info.size
            if clean_info.subtitles:
                badges.append("SUB")
                
            # Languages
            if clean_info.languages:
                languages = clean_info.languages

            badge_str = " ".join([f"[{b}]" for b in badges])
            lang_str = f" ({' / '.join(languages)})" if languages else ""
            
            title = " ".join(title_parts)
            if badge_str:
                title += f" {badge_str}"
            if lang_str:
                title += lang_str
                
            codec = clean_info.codec
        else:
            # Fallback when magnet does not have a dn parameter
            title = fallback_title
            # Attempt to parse resolution/size/languages from fallback title if possible
            clean_info = FileNameCleaner.clean(fallback_title)
            size = clean_info.size
            resolution = clean_info.resolution
            quality = clean_info.quality
            codec = clean_info.codec
            languages = clean_info.languages

        return ParsedMagnetLink(
            magnet_link=magnet_link,
            title=title,
            original_name=original_name or fallback_title,
            size=size,
            resolution=resolution,
            quality=quality,
            codec=codec,
            languages=languages
        )

    @classmethod
    def parse_page(cls, url: str, html_content: Optional[str] = None) -> ParseURLOutput:
        """Fetches and parses a webpage, extracting all magnet links and descriptive titles."""
        if not html_content:
            try:
                response = requests.get(url, headers=cls.HEADERS, timeout=15)
                response.raise_for_status()
                html_content = response.text
            except Exception as e:
                raise Exception(f"Failed to fetch the webpage: {str(e)}")

        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract Page Title (fallback if we can't find specific headers)
        page_title = "Torrent Page"
        title_tag = soup.find('title')
        if title_tag:
            page_title = title_tag.get_text().strip()
            # Clean MovieRulz or other typical footers
            page_title = re.sub(r'\s*\|\s*MovieRulz\s*$', '', page_title, flags=re.IGNORECASE)
            page_title = re.sub(r'\s*Watch Online Free\s*$', '', page_title, flags=re.IGNORECASE)

        # Better yet, look for main h2 entry-title or h1
        h2_title = soup.find('h2', class_='entry-title')
        if h2_title:
            page_title = h2_title.get_text().strip()
        elif soup.find('h1'):
            page_title = soup.find('h1').get_text().strip()

        # Clean title
        page_title = re.sub(r'\s+Watch Online.*$', '', page_title, flags=re.IGNORECASE)

        # Find all magnet links
        magnets = []
        anchors = soup.find_all('a', href=True)
        
        for idx, anchor in enumerate(anchors):
            href = anchor['href'].strip()
            if href.startswith('magnet:'):
                # Attempt to get a descriptive label from the anchor text
                anchor_text = anchor.get_text(separator=' ').strip()
                # Clean up multiple whitespaces
                anchor_text = re.sub(r'\s+', ' ', anchor_text)
                
                # Remove common MovieRulz anchor text prefixes like "GET THIS TORRENT"
                clean_anchor = re.sub(r'^GET THIS TORRENT\s*', '', anchor_text, flags=re.IGNORECASE)
                clean_anchor = clean_anchor.strip()
                
                # Fallback title if dn is missing
                fallback = f"{page_title} - Link {idx + 1}"
                if clean_anchor:
                    fallback = f"{page_title} ({clean_anchor})"
                    
                parsed_link = cls.parse_magnet_link(href, fallback)
                magnets.append(parsed_link)

        # Deduplicate magnet links (sometimes pages have duplicate download buttons)
        seen_links = set()
        deduped_magnets = []
        for mag in magnets:
            if mag.magnet_link not in seen_links:
                seen_links.add(mag.magnet_link)
                deduped_magnets.append(mag)

        return ParseURLOutput(
            page_title=page_title,
            magnets=deduped_magnets
        )
