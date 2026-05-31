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
        
        # Decode display name from magnet URL (dn query parameter)
        try:
            if '?' in magnet_link:
                query_str = magnet_link.split('?', 1)[1]
                parsed_query = urllib.parse.parse_qs(query_str)
                dn_list = parsed_query.get('dn', [])
                if dn_list:
                    original_name = dn_list[0]
        except Exception:
            pass

        # We can clean both original_name and fallback_title to merge/supplement information!
        clean_dn = FileNameCleaner.clean(original_name) if original_name else None
        clean_fb = FileNameCleaner.clean(fallback_title) if fallback_title else None
        
        # Helper to get the best field by prioritizing the DN param first, then falling back to webpage title
        def get_field(field_name, default=None):
            val_dn = getattr(clean_dn, field_name, None) if clean_dn else None
            val_fb = getattr(clean_fb, field_name, None) if clean_fb else None
            return val_dn if val_dn is not None else (val_fb if val_fb is not None else default)

        # Merge languages lists
        langs_dn = getattr(clean_dn, 'languages', []) if clean_dn else []
        langs_fb = getattr(clean_fb, 'languages', []) if clean_fb else []
        languages = list(dict.fromkeys(langs_dn + langs_fb))

        # Re-derive standard values
        size = get_field('size')
        resolution = get_field('resolution')
        quality = get_field('quality')
        codec = get_field('codec')
        
        # Build movie title. We want the most descriptive base name
        cleaned_name = get_field('cleaned_name', fallback_title)
        year = get_field('year')
        season = get_field('season')
        episode = get_field('episode')
        subtitles = clean_dn.subtitles if clean_dn else (clean_fb.subtitles if clean_fb else False)

        title_parts = [cleaned_name]
        if year:
            title_parts.append(f"({year})")
        if season:
            title_parts.append(season)
        if episode:
            title_parts.append(episode)
            
        badges = []
        if resolution:
            badges.append(resolution.upper())
        if quality:
            badges.append(quality)
        if size:
            badges.append(size)
        if subtitles:
            badges.append("SUB")
            
        badge_str = " ".join([f"[{b}]" for b in badges])
        lang_str = f" ({' / '.join(languages)})" if languages else ""
        
        title = " ".join(title_parts)
        if badge_str:
            title += f" {badge_str}"
        if lang_str:
            title += lang_str

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
                # 1. Attempt to get a descriptive label from the anchor text
                anchor_text = anchor.get_text(separator=' ').strip()
                # Clean up multiple whitespaces
                anchor_text = re.sub(r'\s+', ' ', anchor_text)
                
                # Remove common MovieRulz anchor text prefixes like "GET THIS TORRENT"
                clean_anchor = re.sub(
                    r'^(GET THIS TORRENT|Magnet|Download|Torrent|Magnet Link)\s*',
                    '',
                    anchor_text,
                    flags=re.IGNORECASE
                ).strip()
                
                descriptive_title = ""
                if clean_anchor and len(clean_anchor) > 3 and not any(x in clean_anchor.lower() for x in ['download', 'magnet', 'torrent']):
                    descriptive_title = clean_anchor
                else:
                    # 2. Smart Traversal: Go up the DOM tree to find corresponding movie title link (e.g. for TorrentGalaxy)
                    current = anchor
                    for _ in range(4): # Traverse up to 4 levels
                        current = current.parent
                        if not current:
                            break
                            
                        found = False
                        # Find non-magnet sibling text links in the same row/container
                        for sibling in current.find_all('a', href=True):
                            s_href = sibling['href'].strip()
                            if not s_href.startswith('magnet:') and not s_href.startswith('javascript:'):
                                s_text = sibling.get_text(separator=' ').strip()
                                s_text = re.sub(r'\s+', ' ', s_text)
                                # Ignore short or generic utility links (e.g. download, magnet, login)
                                if len(s_text) > 10 and not any(x in s_text.lower() for x in ['download', 'magnet', 'torrent', 'rss', 'login', 'register']):
                                    descriptive_title = s_text
                                    found = True
                                    break
                        if found:
                            break
                            
                        # Also check standard headings or text divs within this row
                        for tag in ['div', 'span', 'h3', 'h4', 'b', 'strong']:
                            for child in current.find_all(tag):
                                c_text = child.get_text(separator=' ').strip()
                                c_text = re.sub(r'\s+', ' ', c_text)
                                if len(c_text) > 10 and not any(x in c_text.lower() for x in ['download', 'magnet', 'torrent', 'rss']):
                                    descriptive_title = c_text
                                    found = True
                                    break
                            if found:
                                break
                
                # Fallback title if no descriptive text could be extracted
                fallback = f"{page_title} - Link {idx + 1}"
                if descriptive_title:
                    fallback = descriptive_title
                elif clean_anchor:
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
