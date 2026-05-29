import os
import re
from typing import List, Optional
from pydantic import BaseModel, Field

class CleanInput(BaseModel):
    filepath: str

class CleanOutput(BaseModel):
    original_path: str
    original_filename: str
    cleaned_name: str
    year: Optional[int] = None
    languages: List[str] = []
    resolution: Optional[str] = None
    quality: Optional[str] = None
    codec: Optional[str] = None
    season: Optional[str] = None
    episode: Optional[str] = None
    size: Optional[str] = None
    subtitles: bool = False
    is_series: bool = False
    new_filepath: str

class FileNameCleaner:
    # Common languages mapping
    LANG_MAP = {
        'english': 'English', 'eng': 'English',
        'hindi': 'Hindi', 'hin': 'Hindi',
        'tamil': 'Tamil', 'tam': 'Tamil',
        'telugu': 'Telugu', 'tel': 'Telugu',
        'latino': 'Latino', 'spanish': 'Spanish', 'spa': 'Spanish',
        'french': 'French', 'fre': 'French',
        'italian': 'Italian', 'ita': 'Italian',
        'korean': 'Korean', 'kor': 'Korean',
        'japanese': 'Japanese', 'jap': 'Japanese',
        'chinese': 'Chinese', 'chi': 'Chinese',
        'german': 'German', 'ger': 'German',
        'russian': 'Russian', 'rus': 'Russian',
        'malayalam': 'Malayalam', 'mal': 'Malayalam',
        'kannada': 'Kannada', 'kan': 'Kannada',
    }

    # Website prefixes to strip from the beginning of the title
    WEBSITE_PREFIXES = [
        r'^vidssave\.com\s*-\s*',
        r'^vidssave\.com\b',
        r'^yts\.mx\b',
        r'^psa\.wf\b',
        r'^galaxyrg\b',
        r'^1337x\b',
        r'^www\.5[mM]ovie[rR]ulz\.[a-zA-Z0-9]+\s*-\s*',
        r'^5[mM]ovie[rR]ulz\.[a-zA-Z0-9]+\s*-\s*',
    ]

    @classmethod
    def clean(cls, filepath: str, source_loc: Optional[str] = None) -> CleanOutput:
        original_filename = os.path.basename(filepath)
        base_name, ext = os.path.splitext(original_filename)

        # 1. Parse Year
        year = None
        # Look for 4 digit year between 1900 and 2099
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', base_name)
        if year_match:
            year = int(year_match.group(1))

        # 2. Parse Season / Episode
        season = None
        episode = None
        is_series = False

        season_match = re.search(r'\b[sS](\d+)\b', base_name)
        if not season_match:
            season_match = re.search(r'\bSeason\s*(\d+)\b', base_name, re.IGNORECASE)
        if season_match:
            season = f"S{int(season_match.group(1)):02d}"
            is_series = True

        episode_match = re.search(r'\b[eE](\d+)\b', base_name)
        if not episode_match:
            episode_match = re.search(r'\bEpisode\s*(\d+)\b', base_name, re.IGNORECASE)
        if not episode_match:
            episode_match = re.search(r'\bEP\s*\(?(\d+-\d+|\d+)\)?\b', base_name, re.IGNORECASE)
        if episode_match:
            episode = f"E{episode_match.group(1)}"
            is_series = True

        # Check for TV Show markers like "COMPLETE" or "S01"
        if "complete" in base_name.lower() or is_series:
            is_series = True

        # 3. Parse Resolution
        resolution = None
        res_match = re.search(r'\b(2160[piP]|1080[piP]|720[piP]|480[piP]|360[piP]|4[kK]|2[kK]|UHD|FHD)\b', base_name)
        if res_match:
            resolution = res_match.group(1).lower()
            if resolution in ['uhd', '4k']:
                resolution = '2160p'
            elif resolution == 'fhd':
                resolution = '1080p'
        else:
            # Standalone HD
            hd_match = re.search(r'\b[hH][dD]\b', base_name)
            if hd_match:
                resolution = '720p' # Standard fallback for HD

        # 4. Parse Codec
        codec = None
        codec_match = re.search(r'\b(x264|x265|h264|h265|hevc|H\.264|H\.265)\b', base_name, re.IGNORECASE)
        if codec_match:
            codec = codec_match.group(1).lower().replace('.', '')

        # 5. Parse Quality
        quality = None
        quality_match = re.search(r'\b(WEB-DL|WEBDL|HDRip|DVDRip|BDRip|BRRip|BluRay|HDTV|DVDScr|Scr|HDTC|TC)\b', base_name, re.IGNORECASE)
        if quality_match:
            quality = quality_match.group(1)
        elif 'hq' in base_name.lower():
            quality = 'HQ'

        # 6. Parse Size
        size = None
        size_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(GB|MB|Gig|GBs|MBs)\b', base_name, re.IGNORECASE)
        if size_match:
            size = f"{size_match.group(1)}{size_match.group(2).upper()}"

        # 7. Parse Subtitles
        subtitles = False
        if re.search(r'\b(ESub|ESubs|Subtitles|Subs|ENG\.SUBS)\b', base_name, re.IGNORECASE):
            subtitles = True

        # 8. Parse Languages
        languages = []
        # Check brackets contents first
        bracket_contents = re.findall(r'\[([^\]]+)\]|\(([^)]+)\)', base_name)
        # Flatten the list of tuples returned by findall
        flat_brackets = [item for sublist in bracket_contents for item in sublist if item]
        
        # Scan bracketed text for languages
        for bracket in flat_brackets:
            bracket_lower = bracket.lower()
            for lang_key, lang_val in cls.LANG_MAP.items():
                if re.search(rf'\b{lang_key}\b', bracket_lower) and lang_val not in languages:
                    languages.append(lang_val)

        # Scan the full base name for languages
        base_name_lower = base_name.lower()
        for lang_key, lang_val in cls.LANG_MAP.items():
            if re.search(rf'\b{lang_key}\b', base_name_lower) and lang_val not in languages:
                languages.append(lang_val)

        # 9. Extract Cleaned Title (Name)
        # Find where the metadata markers start to truncate the title
        markers = [
            r'\b(19\d\d|20\d\d)\b',
            r'\b[sS]\d+\b',
            r'\b[eE]\d+\b',
            r'\bSeason\s*\d+\b',
            r'\bEpisode\s*\d+\b',
            r'\bEP\s*(\d+|\(\d+-\d+\))\b',
            r'\b(2160[piP]|1080[piP]|720[piP]|480[piP]|360[piP]|4[kK]|2[kK]|UHD|FHD)\b',
            r'\b[hH][dD]\b',
            r'\b(WEB-DL|WEBDL|HDRip|DVDRip|BDRip|BRRip|BluRay|HDTV|DVDScr|Scr|HDTC|TC)\b',
            r'\b(x264|x265|h264|h265|hevc|HEVC|H\.264|H\.265)\b',
            r'\b\d+(\.\d+)?\s*(GB|MB|Gig)\b',
            r'\b(ESub|ESubs|Subtitles|Subs|[dD]ual [aA]udio|[mM]ulti [aA]udio)\b',
        ]

        # Also truncate before any bracket/parenthesis if they contain languages or dual audio
        # e.g., "Vikram  (2022)" -> truncate at "(2022)"
        # e.g., "Padayappa HD Subtitles" -> truncate at "HD"
        min_idx = len(base_name)
        for pattern in markers:
            m = re.search(pattern, base_name, re.IGNORECASE)
            if m:
                min_idx = min(min_idx, m.start())

        # If a brackets or parenthesis opens before min_idx and doesn't close, or is adjacent
        # e.g., "Vikram  (2022)" -> "Vikram  "
        raw_title = base_name[:min_idx]

        # Clean website prefixes from title
        for prefix in cls.WEBSITE_PREFIXES:
            raw_title = re.sub(prefix, '', raw_title, flags=re.IGNORECASE)

        # Replace separators with spaces
        cleaned_name = re.sub(r'[\._\-]+', ' ', raw_title)
        
        # Strip brackets/parentheses left at the end
        cleaned_name = re.sub(r'[\(\[\{\-\s]+$', '', cleaned_name)
        cleaned_name = re.sub(r'^[\)\]\}\-\s]+', '', cleaned_name)
        
        # Collapse multiple spaces
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()

        # Title Case
        if cleaned_name:
            # Simple title capitalization but keep numbers/caps
            cleaned_name = " ".join([word.capitalize() if word.islower() else word for word in cleaned_name.split()])
        else:
            cleaned_name = base_name

        # 10. Compute the new filename and folder structure
        # Rename parent folder if the file is in a subfolder.
        # If no source_loc is provided, assume parent directory of filepath is the root source
        parent_dir = os.path.dirname(filepath)
        filename_only = os.path.basename(filepath)

        # Prepare new folder name: Cleaned Name (+ Year if available) to make it unique
        folder_suffix = f" ({year})" if year else ""
        new_folder_name = f"{cleaned_name}{folder_suffix}"

        # If source_loc is configured, check if we are in a subdirectory of source_loc
        new_filepath = filepath
        if source_loc:
            abs_source = os.path.abspath(source_loc)
            abs_parent = os.path.abspath(parent_dir)
            
            # If parent is the root source_loc, we need to create a new subdirectory and move the file
            if abs_parent == abs_source:
                new_folder_path = os.path.join(source_loc, new_folder_name)
                new_filename = f"{cleaned_name}{folder_suffix}{ext}"
                new_filepath = os.path.join(new_folder_path, new_filename)
            elif abs_parent.startswith(abs_source + os.sep):
                # We are in a subdirectory. We rename this subdirectory to new_folder_name
                # Let's find the top-level folder name inside source_loc
                relative_path = os.path.relpath(parent_dir, source_loc)
                top_folder = relative_path.split(os.sep)[0]
                
                new_folder_path = os.path.join(source_loc, new_folder_name)
                new_filename = f"{cleaned_name}{folder_suffix}{ext}"
                new_filepath = os.path.join(new_folder_path, new_filename)
        else:
            # Fallback when no source_loc is given: just rename in-place
            new_filename = f"{cleaned_name}{folder_suffix}{ext}"
            new_filepath = os.path.join(parent_dir, new_filename)

        return CleanOutput(
            original_path=filepath,
            original_filename=original_filename,
            cleaned_name=cleaned_name,
            year=year,
            languages=languages,
            resolution=resolution,
            quality=quality,
            codec=codec,
            season=season,
            episode=episode,
            size=size,
            subtitles=subtitles,
            is_series=is_series,
            new_filepath=new_filepath
        )
