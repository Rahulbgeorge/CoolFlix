import os
import shutil
from django.conf import settings
import json
import logging
import mimetypes
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.utils.text import slugify
from .models import Setting, Video
from .transcoder import transcode_queue
from .infrastructure.cleaner import FileNameCleaner
from .infrastructure.magnet_parser import MagnetParser
from .infrastructure.torrent_downloader import TorrentDownloader

logger = logging.getLogger(__name__)

def get_setting(key, default=""):
    try:
        return Setting.objects.get(key=key).value
    except Setting.DoesNotExist:
        return default

def set_setting(key, value):
    setting, created = Setting.objects.update_or_create(key=key, defaults={'value': value})
    return setting

@csrf_exempt
def config_api(request):
    """GET/POST endpoint for source directory location configuration."""
    if request.method == 'GET':
        source_loc = get_setting('source_loc')
        output_loc = get_setting('output_loc')
        if not output_loc and source_loc:
            output_loc = os.path.join(source_loc, 'streamable')
        return JsonResponse({
            'source_loc': source_loc,
            'output_loc': output_loc
        })
        
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            source_loc = data.get('source_loc', '').strip()
            output_loc = data.get('output_loc', '').strip()
            
            if not source_loc:
                return JsonResponse({'error': 'Source location cannot be empty'}, status=400)
                
            if not os.path.exists(source_loc):
                return JsonResponse({'error': f'Path does not exist: {source_loc}'}, status=400)
                
            if not os.path.isdir(source_loc):
                return JsonResponse({'error': f'Path is not a directory: {source_loc}'}, status=400)
                
            if not output_loc:
                output_loc = os.path.join(source_loc, 'streamable')
                
            # Create output directory if it doesn't exist
            try:
                os.makedirs(output_loc, exist_ok=True)
            except Exception as e:
                return JsonResponse({'error': f'Failed to create output directory: {str(e)}'}, status=400)
                
            set_setting('source_loc', source_loc)
            set_setting('output_loc', output_loc)
            return JsonResponse({
                'success': True,
                'source_loc': source_loc,
                'output_loc': output_loc
            })
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def scan_api(request):
    """Scans the configured source directory recursively for new video files, renames them, and queues them."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    source_loc = get_setting('source_loc')
    if not source_loc or not os.path.exists(source_loc):
        return JsonResponse({'error': 'Valid source location is not configured'}, status=400)
        
    output_loc = get_setting('output_loc')
    if not output_loc:
        output_loc = os.path.join(source_loc, 'streamable')
        
    abs_source = os.path.abspath(source_loc)
    abs_output = os.path.abspath(output_loc)
    
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v')
    new_videos_count = 0
    
    # 1. Walk and collect all video files first to avoid modifying folders while walking
    video_files = []
    try:
        for root, dirs, files in os.walk(source_loc):
            abs_root = os.path.abspath(root)
            
            # Skip output folder and any subfolders inside it to prevent recursive scan
            if abs_root == abs_output or abs_root.startswith(abs_output + os.sep):
                dirs[:] = []
                continue
                
            # Exclude output dir from dirs list
            for d in list(dirs):
                d_abs = os.path.abspath(os.path.join(root, d))
                if d_abs == abs_output or d == 'streamable':
                    dirs.remove(d)
                    
            for file in files:
                if file.lower().endswith(video_extensions):
                    video_files.append(os.path.join(root, file))
    except Exception as e:
        logger.exception("Error walking source directory")
        return JsonResponse({'error': f"Failed to scan directory: {str(e)}"}, status=500)
        
    # 2. Process and rename each file, and store in database
    for filepath in video_files:
        try:
            # Clean name and get new filepath target
            clean_res = FileNameCleaner.clean(filepath, source_loc)
            
            # Skip if target file path is already in DB
            if Video.objects.filter(original_path=clean_res.new_filepath).exists():
                continue
                
            # Skip if current file path is already in DB
            if Video.objects.filter(original_path=filepath).exists():
                continue

            # Ensure file still exists at the original location
            if not os.path.exists(filepath):
                continue
                
            # Rename the file and directory physically on disk
            final_path = filepath
            if clean_res.new_filepath != filepath:
                dest_dir = os.path.dirname(clean_res.new_filepath)
                os.makedirs(dest_dir, exist_ok=True)
                
                try:
                    os.rename(filepath, clean_res.new_filepath)
                    final_path = clean_res.new_filepath
                    
                    # If the file was in a subfolder and it's now empty, delete it
                    old_parent = os.path.dirname(filepath)
                    if os.path.abspath(old_parent) != os.path.abspath(source_loc):
                        try:
                            remaining = [f for f in os.listdir(old_parent) if not f.startswith('.')]
                            if not remaining:
                                shutil.rmtree(old_parent)
                        except Exception:
                            pass
                except Exception as rename_err:
                    logger.error(f"Failed to rename file {filepath} to {clean_res.new_filepath}: {rename_err}")
                    # Fallback to original path if rename fails (e.g. permission/lock issue)
                    final_path = filepath
                    
            # Extract title and generate unique slug
            base_slug = slugify(clean_res.cleaned_name)
            if not base_slug:
                base_slug = "video"
            slug = base_slug
            counter = 1
            while Video.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                
            # Create DB record with full metadata
            video = Video.objects.create(
                title=clean_res.cleaned_name,
                original_path=final_path,
                slug=slug,
                status='pending',
                progress=0.0,
                cleaned_title=clean_res.cleaned_name,
                release_year=clean_res.year,
                languages=clean_res.languages,
                resolution=clean_res.resolution,
                quality=clean_res.quality,
                codec=clean_res.codec,
                season=clean_res.season,
                episode=clean_res.episode,
                size=clean_res.size,
                subtitles=clean_res.subtitles,
                is_series=clean_res.is_series
            )
            
            # Put on processing queue
            transcode_queue.put(video.id)
            new_videos_count += 1
            
        except Exception as item_err:
            logger.error(f"Error processing video item {filepath}: {item_err}")
            
    return JsonResponse({'success': True, 'scanned': True, 'new_videos_added': new_videos_count})

def videos_list_api(request):
    """Returns list of all videos with metadata and endpoints."""
    videos = Video.objects.all().order_by('-created_at')
    result = []
    
    # We need request host to construct absolute URLs for streamable content
    host = request.build_absolute_uri('/')[:-1]
    
    for v in videos:
        # Check if assets are available
        thumbnail_url = f"{host}/media/streamable/{v.slug}/thumbnail.jpg" if v.status == 'completed' else None
        preview_url = f"{host}/media/streamable/{v.slug}/preview.mp4" if v.status == 'completed' else None
        master_playlist_url = f"{host}/media/streamable/{v.slug}/streams/master.m3u8" if v.status == 'completed' else None
        
        result.append({
            'id': v.id,
            'title': v.title,
            'slug': v.slug,
            'status': v.status,
            'progress': v.progress,
            'duration': v.duration,
            'width': v.width,
            'height': v.height,
            'thumbnail_url': thumbnail_url,
            'preview_url': preview_url,
            'master_playlist_url': master_playlist_url,
            'error_message': v.error_message,
            'created_at': v.created_at.isoformat(),
            'updated_at': v.updated_at.isoformat(),
            
            # New parsed metadata fields
            'original_path': v.original_path,
            'cleaned_title': v.cleaned_title,
            'year': v.release_year,
            'languages': v.languages,
            'resolution': v.resolution,
            'quality': v.quality,
            'codec': v.codec,
            'season': v.season,
            'episode': v.episode,
            'size': v.size,
            'subtitles': v.subtitles,
            'is_series': v.is_series,
        })
        
    return JsonResponse({'videos': result})

def video_detail_api(request, video_id):
    """Returns detailed video object, including available quality streams."""
    try:
        v = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)
        
    host = request.build_absolute_uri('/')[:-1]
    
    # Read stream metadata if available
    streams = []
    sprite_info = None
    if v.status == 'completed':
        streams_meta_path = os.path.join(settings.MEDIA_ROOT, 'streamable', v.slug, 'streams', 'metadata.json')
        if os.path.exists(streams_meta_path):
            try:
                with open(streams_meta_path, 'r') as f:
                    streams = json.load(f).get('streams', [])
            except Exception:
                pass
                
        sprite_meta_path = os.path.join(settings.MEDIA_ROOT, 'streamable', v.slug, 'sprite_info.json')
        if os.path.exists(sprite_meta_path):
            try:
                with open(sprite_meta_path, 'r') as f:
                    sprite_info = json.load(f)
            except Exception:
                pass
                
    thumbnail_url = f"{host}/media/streamable/{v.slug}/thumbnail.jpg" if v.status == 'completed' else None
    preview_url = f"{host}/media/streamable/{v.slug}/preview.mp4" if v.status == 'completed' else None
    master_playlist_url = f"{host}/media/streamable/{v.slug}/streams/master.m3u8" if v.status == 'completed' else None
    sprite_url_template = f"{host}/media/streamable/{v.slug}/sprite_%03d.jpg" if v.status == 'completed' else None
    
    return JsonResponse({
        'id': v.id,
        'title': v.title,
        'slug': v.slug,
        'status': v.status,
        'progress': v.progress,
        'duration': v.duration,
        'width': v.width,
        'height': v.height,
        'thumbnail_url': thumbnail_url,
        'preview_url': preview_url,
        'master_playlist_url': master_playlist_url,
        'sprite_url_template': sprite_url_template,
        'sprite_info': sprite_info,
        'streams': streams,
        'error_message': v.error_message,
        'created_at': v.created_at.isoformat(),
        
        # New parsed metadata fields
        'original_path': v.original_path,
        'cleaned_title': v.cleaned_title,
        'year': v.release_year,
        'languages': v.languages,
        'resolution': v.resolution,
        'quality': v.quality,
        'codec': v.codec,
        'season': v.season,
        'episode': v.episode,
        'size': v.size,
        'subtitles': v.subtitles,
        'is_series': v.is_series,
    })

@csrf_exempt
def video_retry_api(request, video_id):
    """Enqueues a failed video for transcoding retry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)
        
    if video.status != 'failed' and video.status != 'completed':
        return JsonResponse({'error': 'Only failed or completed videos can be retried'}, status=400)
        
    video.status = 'pending'
    video.progress = 0.0
    video.error_message = None
    video.save()
    
    transcode_queue.put(video.id)
    return JsonResponse({'success': True, 'queued': True})

def serve_streamable_file(request, relative_path):
    """Serves transcoded assets (m3u8, ts, preview.mp4, thumbnails) dynamically from output_loc."""
    source_loc = get_setting('source_loc')
    output_loc = get_setting('output_loc')
    if not output_loc:
        if source_loc:
            output_loc = os.path.join(source_loc, 'streamable')
        else:
            output_loc = os.path.join(settings.MEDIA_ROOT, 'streamable')
            
    abs_output = os.path.abspath(output_loc)
    file_path = os.path.abspath(os.path.join(abs_output, relative_path))
    
    # Path traversal validation
    if not file_path.startswith(abs_output):
        return HttpResponse("Forbidden", status=403)
        
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return HttpResponse("Not Found", status=404)
        
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        if file_path.endswith('.m3u8'):
            content_type = 'application/x-mpegURL'
        elif file_path.endswith('.ts'):
            content_type = 'video/MP2T'
        else:
            content_type = 'application/octet-stream'
            
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response["Access-Control-Allow-Origin"] = "*"
    return response

@csrf_exempt
def parse_url_api(request):
    """POST endpoint to scrape magnet links and titles from a webpage URL."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        
        if not url:
            return JsonResponse({'error': 'URL cannot be empty'}, status=400)
            
        if not (url.startswith('http://') or url.startswith('https://')):
            return JsonResponse({'error': 'Invalid URL scheme. Must start with http:// or https://'}, status=400)
            
        # Parse the page
        parser_output = MagnetParser.parse_page(url)
        
        return JsonResponse({
            'success': True,
            'page_title': parser_output.page_title,
            'magnets': [m.model_dump() for m in parser_output.magnets]
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    except Exception as e:
        logger.exception("Error parsing webpage URL")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def download_magnet_api(request):
    """POST endpoint to trigger transmission-remote background download for a magnet link."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        magnet_link = data.get('magnet_link', '').strip()
        
        if not magnet_link:
            return JsonResponse({'error': 'Magnet link cannot be empty'}, status=400)
            
        if not magnet_link.startswith('magnet:'):
            return JsonResponse({'error': 'Invalid magnet link format'}, status=400)
            
        # Fetch the configured source directory as write location override if exists
        source_loc = get_setting('source_loc')
        custom_dir = os.path.abspath(source_loc) if (source_loc and os.path.exists(source_loc)) else None
        
        result = TorrentDownloader.download(magnet_link, custom_dir=custom_dir)
        
        if result.success:
            return JsonResponse({
                'success': True,
                'message': result.message,
                'cmd': result.cmd,
                'download_dir': result.download_dir
            })
        else:
            status_code = 400
            # If the command wasn't found, return 501
            if "not found" in (result.error or "").lower() or "missing" in (result.message or "").lower():
                status_code = 501
            return JsonResponse({
                'success': False,
                'error': result.error or result.message,
                'cmd': result.cmd
            }, status=status_code)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    except Exception as e:
        logger.exception("Error executing torrent download")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def download_status_api(request):
    """GET endpoint to fetch active downloads status from Transmission daemon."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        downloads = TorrentDownloader.list_downloads()
        return JsonResponse({
            'success': True,
            'downloads': [d.model_dump() for d in downloads]
        })
    except FileNotFoundError:
        return JsonResponse({
            'success': False,
            'error': 'transmission-remote command not found. Cannot query active download progress.'
        }, status=501)
    except Exception as e:
        logger.exception("Error checking active torrent status")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def delete_torrent_api(request):
    """POST endpoint to remove or delete a torrent from Transmission daemon."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        torrent_id = data.get('torrent_id', '').strip()
        delete_files = bool(data.get('delete_files', False))
        
        if not torrent_id:
            return JsonResponse({'error': 'Torrent ID cannot be empty'}, status=400)
            
        result = TorrentDownloader.remove(torrent_id, delete_files=delete_files)
        
        if result.success:
            return JsonResponse({
                'success': True,
                'message': result.message,
                'cmd': result.cmd
            })
        else:
            status_code = 400
            if "not found" in (result.error or "").lower() or "missing" in (result.message or "").lower():
                status_code = 501
            return JsonResponse({
                'success': False,
                'error': result.error or result.message,
                'cmd': result.cmd
            }, status=status_code)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    except Exception as e:
        logger.exception("Error removing torrent")
        return JsonResponse({'error': str(e)}, status=500)

def serve_frontend(request, path=''):
    """Serves the entrypoint index.html for the built frontend from MEDIA_ROOT/frontend/index.html."""
    frontend_dir = os.path.join(settings.MEDIA_ROOT, 'frontend')
    index_path = os.path.join(frontend_dir, 'index.html')
    
    if not os.path.exists(index_path):
        return HttpResponse(
            "Frontend not compiled. Please run the install/build script to compile the frontend to /media/frontend.",
            status=404
        )
        
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return HttpResponse(content, content_type='text/html')
