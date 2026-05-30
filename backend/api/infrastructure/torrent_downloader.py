import os
import re
import subprocess
import logging
from typing import List, Optional
from pydantic import BaseModel
from django.conf import settings
from ..models import Setting

logger = logging.getLogger(__name__)

class TorrentJob(BaseModel):
    id: str
    done: str
    have: str
    eta: str
    up: str
    down: str
    ratio: str
    status: str
    name: str
    download_dir: str

class DownloadResult(BaseModel):
    success: bool
    message: str
    error: Optional[str] = None
    cmd: str
    download_dir: str

class TorrentDownloader:
    @classmethod
    def get_download_dir(cls) -> str:
        download_dir = None
        
        # 1. Try to get configured source_loc from database (configured scan path)
        try:
            db_source = Setting.objects.get(key='source_loc').value
            if db_source and os.path.exists(db_source):
                download_dir = db_source
        except Exception:
            pass
            
        # 2. Try to get hardcoded setting from Django settings as fallback
        if not download_dir:
            download_dir = getattr(settings, 'TORRENT_DOWNLOAD_DIR', None)
            
        # 3. Fallback to settings.MEDIA_ROOT
        if not download_dir:
            download_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
            
        # Ensure directory exists
        os.makedirs(download_dir, exist_ok=True)
        return os.path.abspath(download_dir)

    @classmethod
    def download(cls, magnet_link: str, custom_dir: Optional[str] = None) -> DownloadResult:
        """Triggers a background torrent download using transmission-remote."""
        write_location = custom_dir or cls.get_download_dir()
        
        cmd = ['transmission-remote', '-a', magnet_link, '-w', write_location]
        logger.info(f"Initiating background torrent download: {' '.join(cmd)}")
        
        try:
            # Execute command with a timeout
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            
            if result.returncode == 0:
                return DownloadResult(
                    success=True,
                    message='Torrent download successfully initiated with Transmission.',
                    cmd=' '.join(cmd),
                    download_dir=write_location
                )
            else:
                stderr_output = result.stderr.strip() or result.stdout.strip()
                return DownloadResult(
                    success=False,
                    message='Transmission daemon returned a non-zero exit code.',
                    error=f'Exit code {result.returncode}: {stderr_output}',
                    cmd=' '.join(cmd),
                    download_dir=write_location
                )
        except FileNotFoundError:
            err_msg = ("transmission-remote command not found. Please install transmission-cli via "
                       "Homebrew (brew install transmission-cli) and ensure the transmission-daemon is running.")
            logger.warning(err_msg)
            return DownloadResult(
                success=False,
                message='Transmission remote command is missing on the host.',
                error=err_msg,
                cmd=' '.join(cmd),
                download_dir=write_location
            )
        except Exception as e:
            logger.exception("Error executing transmission-remote call")
            return DownloadResult(
                success=False,
                message='An unexpected error occurred while starting the download.',
                error=str(e),
                cmd=' '.join(cmd),
                download_dir=write_location
            )

    @classmethod
    def list_downloads(cls) -> List[TorrentJob]:
        """Queries the Transmission daemon and parses the list of active downloads."""
        cmd = ['transmission-remote', '-l']
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise Exception(f"Transmission returned error: {error_msg}")
                
            return cls.parse_transmission_list(result.stdout)
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error querying active downloads: {e}")
            raise

    @classmethod
    def parse_transmission_list(cls, stdout_text: str) -> List[TorrentJob]:
        """Parses vertically aligned columns of transmission-remote -l stdout."""
        lines = stdout_text.strip().split('\n')
        if not lines:
            return []
        
        # Find header line to get column indices
        header_idx = -1
        for idx, line in enumerate(lines):
            if 'ID' in line and 'Done' in line and 'Status' in line:
                header_idx = idx
                break
                
        if header_idx == -1:
            return []
            
        header = lines[header_idx]
        
        # Find start indices of columns
        idx_id = header.find('ID')
        idx_done = header.find('Done')
        idx_have = header.find('Have')
        idx_eta = header.find('ETA')
        idx_up = header.find('Up')
        idx_down = header.find('Down')
        idx_ratio = header.find('Ratio')
        idx_status = header.find('Status')
        idx_name = header.find('Name')
        
        download_dir = cls.get_download_dir()
        torrents = []
        
        for line in lines[header_idx + 1:]:
            if not line.strip() or line.strip().startswith('Sum:'):
                continue
                
            def get_slice(start, end=None):
                if end:
                    return line[start:end].strip()
                return line[start:].strip()
                
            try:
                torrent_id = get_slice(idx_id, idx_done)
                done = get_slice(idx_done, idx_have)
                have = get_slice(idx_have, idx_eta)
                eta = get_slice(idx_eta, idx_up)
                up = get_slice(idx_up, idx_down)
                down = get_slice(idx_down, idx_ratio)
                ratio = get_slice(idx_ratio, idx_status)
                status = get_slice(idx_status, idx_name)
                name = get_slice(idx_name)
                
                torrents.append(TorrentJob(
                    id=torrent_id,
                    done=done,
                    have=have,
                    eta=eta,
                    up=up,
                    down=down,
                    ratio=ratio,
                    status=status,
                    name=name,
                    download_dir=download_dir
                ))
            except Exception:
                pass
                
        return torrents

    @classmethod
    def remove(cls, torrent_id: str, delete_files: bool = False) -> DownloadResult:
        """Removes a torrent by ID. Optionally deletes the downloaded files too."""
        action_flag = '-rad' if delete_files else '-r'
        cmd = ['transmission-remote', '-t', torrent_id, action_flag]
        logger.info(f"Removing torrent {torrent_id} (delete_files={delete_files}): {' '.join(cmd)}")
        
        write_location = cls.get_download_dir()
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if result.returncode == 0:
                action_text = "removed and files deleted" if delete_files else "removed (files kept)"
                return DownloadResult(
                    success=True,
                    message=f"Torrent {torrent_id} successfully {action_text}.",
                    cmd=' '.join(cmd),
                    download_dir=write_location
                )
            else:
                stderr_output = result.stderr.strip() or result.stdout.strip()
                return DownloadResult(
                    success=False,
                    message='Transmission daemon returned a non-zero exit code.',
                    error=f'Exit code {result.returncode}: {stderr_output}',
                    cmd=' '.join(cmd),
                    download_dir=write_location
                )
        except FileNotFoundError:
            err_msg = "transmission-remote command not found."
            logger.warning(err_msg)
            return DownloadResult(
                success=False,
                message='Transmission remote command is missing on the host.',
                error=err_msg,
                cmd=' '.join(cmd),
                download_dir=write_location
            )
        except Exception as e:
            logger.exception("Error executing transmission-remote remove call")
            return DownloadResult(
                success=False,
                message='An unexpected error occurred while removing the torrent.',
                error=str(e),
                cmd=' '.join(cmd),
                download_dir=write_location
            )
