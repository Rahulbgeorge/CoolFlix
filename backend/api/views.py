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
from .models import Setting, Video, VideoClip
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

def get_output_loc():
    source_loc = get_setting('source_loc')
    output_loc = get_setting('output_loc')
    if not output_loc:
        if source_loc:
            output_loc = os.path.join(source_loc, 'streamable')
        else:
            output_loc = os.path.join(settings.MEDIA_ROOT, 'streamable')
    return output_loc

@csrf_exempt
def config_api(request):
    """GET/POST endpoint for source directory location configuration."""
    if request.method == 'GET':
        source_loc = get_setting('source_loc')
        output_loc = get_setting('output_loc')
        default_target = get_setting('default_transcode_target', 'original')
        if not output_loc and source_loc:
            output_loc = os.path.join(source_loc, 'streamable')
        return JsonResponse({
            'source_loc': source_loc,
            'output_loc': output_loc,
            'default_transcode_target': default_target
        })
        
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            source_loc = data.get('source_loc', '').strip()
            output_loc = data.get('output_loc', '').strip()
            default_target = data.get('default_transcode_target', 'original').strip()
            
            if not source_loc:
                return JsonResponse({'error': 'Source location cannot be empty'}, status=400)
                
            if not os.path.exists(source_loc):
                return JsonResponse({'error': f'Path does not exist: {source_loc}'}, status=400)
                
            if not os.path.isdir(source_loc):
                return JsonResponse({'error': f'Path is not a directory: {source_loc}'}, status=400)
                
            if not output_loc:
                output_loc = os.path.join(source_loc, 'streamable')
                
            if default_target not in ['original', '1080p', '720p', '480p']:
                default_target = 'original'
                
            # Create output directory if it doesn't exist
            try:
                os.makedirs(output_loc, exist_ok=True)
            except Exception as e:
                return JsonResponse({'error': f'Failed to create output directory: {str(e)}'}, status=400)
                
            set_setting('source_loc', source_loc)
            set_setting('output_loc', output_loc)
            set_setting('default_transcode_target', default_target)
            return JsonResponse({
                'success': True,
                'source_loc': source_loc,
                'output_loc': output_loc,
                'default_transcode_target': default_target
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
                hls_status='pending',
                hls_required=True,
                sprite_status='pending',
                preview_clip_status='pending',
                preview_status='pending',
                transcode_target=get_setting('default_transcode_target', 'original'),
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
            
            # Ensure the output directory exists for thumbnails and sprites
            video_output_dir = os.path.join(output_loc, slug)
            os.makedirs(video_output_dir, exist_ok=True)
            
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
        # Check if assets are available based on stage completion
        thumbnail_url = f"{host}/media/streamable/{v.slug}/thumbnail.jpg" if v.preview_clip_status == 'completed' else None
        master_playlist_url = f"{host}/media/streamable/{v.slug}/streams/master.m3u8" if v.hls_status == 'completed' else None
        # Check if physical preview is completed, else look for database preview clip
        preview_url = None
        if v.preview_status == 'completed':
            preview_url = f"{host}/media/streamable/{v.slug}/preview.mp4"
        else:
            preview_clip = v.clips.filter(category='Preview').first()
            if preview_clip:
                preview_url = f"{master_playlist_url}#t={preview_clip.start_time},{preview_clip.end_time}" if master_playlist_url else None
        
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
            'transcode_target': v.transcode_target,
            'hls_status': v.hls_status,
            'sprite_status': v.sprite_status,
            'preview_clip_status': v.preview_clip_status,
            'preview_status': v.preview_status,
            'hls_required': v.hls_required,
            'has_custom_thumbnail': v.has_custom_thumbnail,
        })
        
    return JsonResponse({'videos': result})

@csrf_exempt
def video_detail_api(request, video_id):
    """GET to retrieve detailed video metadata. POST/PATCH to update settings (hls_required, transcode_target)."""
    try:
        v = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)
        
    if request.method in ('POST', 'PATCH'):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON request body'}, status=400)
            
        hls_req = data.get('hls_required')
        if hls_req is not None:
            hls_req = bool(hls_req)
            if hls_req and not v.hls_required:
                v.hls_required = True
                if v.hls_status in ('skipped', 'pending', 'failed'):
                    v.hls_status = 'pending'
                    if v.progress == 100.0 or v.status == 'completed':
                        v.progress = 66.7
                        v.status = 'processing'
            elif not hls_req and v.hls_required:
                v.hls_required = False
                if v.hls_status in ('pending', 'processing'):
                    v.hls_status = 'skipped'
                    v.progress = 100.0
                    v.status = 'completed'
                    
        target = data.get('transcode_target')
        if target is not None:
            if target in ['original', '1080p', '720p', '480p']:
                v.transcode_target = target
                if v.hls_required and v.hls_status in ('completed', 'skipped', 'failed'):
                    v.hls_status = 'pending'
                    v.progress = 66.7
                    v.status = 'processing'
                    
        v.save()
        
    host = request.build_absolute_uri('/')[:-1]
    
    # Read stream metadata if available
    streams = []
    sprite_info = None
    output_loc = get_output_loc()
    if v.hls_status == 'completed':
        streams_meta_path = os.path.join(output_loc, v.slug, 'streams', 'metadata.json')
        if os.path.exists(streams_meta_path):
            try:
                with open(streams_meta_path, 'r') as f:
                    streams = json.load(f).get('streams', [])
            except Exception:
                pass
                
    if v.sprite_status == 'completed':
        sprite_meta_path = os.path.join(output_loc, v.slug, 'sprite_info.json')
        if os.path.exists(sprite_meta_path):
            try:
                with open(sprite_meta_path, 'r') as f:
                    sprite_info = json.load(f)
            except Exception:
                pass
                
    thumbnail_url = f"{host}/media/streamable/{v.slug}/thumbnail.jpg" if v.preview_clip_status == 'completed' else None
    master_playlist_url = f"{host}/media/streamable/{v.slug}/streams/master.m3u8" if v.hls_status == 'completed' else None
    sprite_url_template = f"{host}/media/streamable/{v.slug}/sprite_%03d.jpg" if v.sprite_status == 'completed' else None
    
    # Check if physical preview is completed, else look for database preview clip
    preview_url = None
    if v.preview_status == 'completed':
        preview_url = f"{host}/media/streamable/{v.slug}/preview.mp4"
    else:
        preview_clip = v.clips.filter(category='Preview').first()
        if preview_clip:
            preview_url = f"{master_playlist_url}#t={preview_clip.start_time},{preview_clip.end_time}" if master_playlist_url else None
    
    # Probe video dynamically for audio tracks list
    # TODO Phase 2: Once per-track audio files are generated (e.g. video_eng.mp4, video_tamil.mp4),
    # return their Nginx URLs here instead of just metadata. Frontend will switch src directly.
    audio_tracks = []
    if os.path.exists(v.original_path):
        try:
            from .infrastructure.transcoder import FFmpegTranscoder
            info = FFmpegTranscoder.probe_video(v.original_path)
            audio_tracks = info.get('audio_tracks', [])
        except Exception as e:
            logger.error(f"Failed to probe audio tracks for video {v.id}: {e}")

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
        'audio_tracks': audio_tracks,
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
        'transcode_target': v.transcode_target,
        'hls_status': v.hls_status,
        'sprite_status': v.sprite_status,
        'preview_clip_status': v.preview_clip_status,
        'preview_status': v.preview_status,
        'hls_required': v.hls_required,
        'has_custom_thumbnail': v.has_custom_thumbnail,
    })

@csrf_exempt
def video_retry_api(request, video_id):
    """Enqueues a failed or completed video for transcoding retry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)
        
    if video.status != 'failed' and video.status != 'completed':
        return JsonResponse({'error': 'Only failed or completed videos can be retried'}, status=400)
        
    # Read target quality from request body or query parameter
    target = 'original'
    try:
        if request.body:
            data = json.loads(request.body)
            target = data.get('target', 'original')
    except Exception:
        target = request.GET.get('target', video.transcode_target)
        
    if target not in ['original', '1080p', '720p', '480p']:
        target = 'original'
        
    video.transcode_target = target
    video.status = 'pending'
    video.hls_status = 'pending'
    video.sprite_status = 'pending'
    video.preview_clip_status = 'pending'
    video.preview_status = 'not_required'
    video.progress = 0.0
    video.error_message = None
    video.save()
    
    return JsonResponse({'success': True, 'queued': True})

def serve_streamable_file(request, relative_path):
    """Serves transcoded/copied assets (m3u8, ts, preview.mp4, thumbnails, original.mp4) dynamically from output_loc with seek support."""
    from django.views.static import serve
    source_loc = get_setting('source_loc')
    output_loc = get_setting('output_loc')
    if not output_loc:
        if source_loc:
            output_loc = os.path.join(source_loc, 'streamable')
        else:
            output_loc = os.path.join(settings.MEDIA_ROOT, 'streamable')
            
    abs_output = os.path.abspath(output_loc)
    
    try:
        response = serve(request, relative_path, document_root=abs_output)
        response["Access-Control-Allow-Origin"] = "*"
        return response
    except Exception as e:
        logger.exception(f"Error serving streamable file {relative_path}")
        return HttpResponse("Not Found", status=404)

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

        if url.startswith('magnet:'):
            # Paste direct magnet links support: parse and return immediately
            parsed_link = MagnetParser.parse_magnet_link(url, "Direct Magnet Link")
            return JsonResponse({
                'success': True,
                'page_title': 'Direct Magnet Link',
                'magnets': [parsed_link.model_dump()]
            })

        if not (url.startswith('http://') or url.startswith('https://')):
            return JsonResponse({'error': 'Invalid URL scheme. Must start with http://, https://, or paste magnet: directly'}, status=400)
            
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

# ──────────────────────────────────────────────────────────────────────────────
# Video streaming is handled directly by Nginx via range queries (206 Partial Content)
# dynamically initiated through Django returning X-Accel-Redirect headers.
# ──────────────────────────────────────────────────────────────────────────────


@csrf_exempt
def video_clips_api(request, video_id):
    """GET to retrieve all clips for a video and all unique categories. POST to save a new clip."""
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)

    if request.method == 'GET':
        clips = VideoClip.objects.filter(video=video).order_by('start_time')
        # Retrieve all unique categories in the entire database
        categories = list(VideoClip.objects.values_list('category', flat=True).distinct())
        categories = [c for c in categories if c]  # filter out empty ones
        
        clips_data = [{
            'id': c.id,
            'name': c.name,
            'start_time': c.start_time,
            'end_time': c.end_time,
            'category': c.category,
            'created_at': c.created_at.isoformat()
        } for c in clips]

        return JsonResponse({
            'clips': clips_data,
            'categories': categories
        })

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            category = data.get('category', '').strip()
            start_time = float(data.get('start_time', 0))
            end_time = float(data.get('end_time', 0))

            if not name:
                return JsonResponse({'error': 'Clip name cannot be empty'}, status=400)
            if not category:
                return JsonResponse({'error': 'Clip category cannot be empty'}, status=400)
            if start_time < 0:
                return JsonResponse({'error': 'Start time must be greater than or equal to 0'}, status=400)
            if end_time <= start_time:
                return JsonResponse({'error': 'End time must be strictly greater than start time'}, status=400)

            if category == 'Preview':
                clip, created = VideoClip.objects.update_or_create(
                    video=video,
                    category="Preview",
                    defaults={
                        'name': name,
                        'start_time': start_time,
                        'end_time': end_time
                    }
                )
                
                # Regenerate thumbnail from new start_time if NOT custom
                if not video.has_custom_thumbnail:
                    try:
                        target_dir = os.path.join(get_output_loc(), video.slug)
                        from .infrastructure.transcoder import FFmpegTranscoder
                        FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, start_time)
                    except Exception as e:
                        logger.error(f"Failed to regenerate thumbnail after preview clip update: {e}")
            else:
                clip = VideoClip.objects.create(
                    video=video,
                    name=name,
                    category=category,
                    start_time=start_time,
                    end_time=end_time
                )

            return JsonResponse({
                'success': True,
                'clip': {
                    'id': clip.id,
                    'name': clip.name,
                    'start_time': clip.start_time,
                    'end_time': clip.end_time,
                    'category': clip.category,
                    'created_at': clip.created_at.isoformat()
                }
            })
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid request data'}, status=400)
            
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def delete_clip_api(request, clip_id):
    """DELETE to remove a video clip by ID."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        clip = VideoClip.objects.get(id=clip_id)
        video = clip.video
        category = clip.category
        clip.delete()
        
        # If the deleted clip was the Preview clip and has_custom_thumbnail is False,
        # recreate a default preview clip & thumbnail.
        if category == 'Preview' and not video.has_custom_thumbnail:
            try:
                target_dir = os.path.join(get_output_loc(), video.slug)
                start_time = video.duration * 0.3 if video.duration > 10 else 1.0
                from .infrastructure.transcoder import FFmpegTranscoder
                FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, start_time)
                # Recreate database preview clip at start_time
                VideoClip.objects.create(
                    video=video,
                    category="Preview",
                    name="Preview Clip",
                    start_time=round(start_time, 1),
                    end_time=round(start_time + 5.0, 1)
                )
            except Exception as e:
                logger.error(f"Failed to regenerate default preview after deletion: {e}")
                
        return JsonResponse({'success': True})
    except VideoClip.DoesNotExist:
        return JsonResponse({'error': 'Clip not found'}, status=404)


@csrf_exempt
def video_thumbnail_api(request, video_id):
    """POST to upload a custom thumbnail. DELETE to revert to the generated one."""
    import time
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)
        
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file uploaded'}, status=400)
            
        file_obj = request.FILES['file']
        ext = os.path.splitext(file_obj.name)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png']:
            return JsonResponse({'error': 'Unsupported file format. Only JPG, JPEG, and PNG are allowed.'}, status=400)
            
        target_dir = os.path.join(get_output_loc(), video.slug)
        os.makedirs(target_dir, exist_ok=True)
        
        thumbnail_path = os.path.join(target_dir, 'thumbnail.jpg')
        preview_path = os.path.join(target_dir, 'preview.jpg')
        
        try:
            try:
                from PIL import Image
                img = Image.open(file_obj)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(thumbnail_path, 'JPEG', quality=90)
                img.save(preview_path, 'JPEG', quality=90)
            except Exception:
                with open(thumbnail_path, 'wb+') as destination:
                    for chunk in file_obj.chunks():
                        destination.write(chunk)
                shutil.copyfile(thumbnail_path, preview_path)
                
            video.has_custom_thumbnail = True
            video.save()
            
            host = request.build_absolute_uri('/')[:-1]
            return JsonResponse({
                'success': True, 
                'thumbnail_url': f"{host}/media/streamable/{video.slug}/thumbnail.jpg?t={int(time.time())}"
            })
        except Exception as e:
            return JsonResponse({'error': f"Failed to save thumbnail: {str(e)}"}, status=500)
            
    elif request.method == 'DELETE':
        target_dir = os.path.join(get_output_loc(), video.slug)
        thumbnail_path = os.path.join(target_dir, 'thumbnail.jpg')
        preview_path = os.path.join(target_dir, 'preview.jpg')
        
        if os.path.exists(preview_path):
            try:
                os.remove(preview_path)
            except Exception:
                pass
                
        preview_clip = video.clips.filter(category='Preview').first()
        start_time = preview_clip.start_time if preview_clip else (video.duration * 0.3 if video.duration > 10 else 1.0)
        
        try:
            from .infrastructure.transcoder import FFmpegTranscoder
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, start_time)
            video.has_custom_thumbnail = False
            video.save()
            
            host = request.build_absolute_uri('/')[:-1]
            return JsonResponse({
                'success': True,
                'thumbnail_url': f"{host}/media/streamable/{video.slug}/thumbnail.jpg?t={int(time.time())}"
            })
        except Exception as e:
            return JsonResponse({'error': f"Failed to regenerate thumbnail: {str(e)}"}, status=500)
            
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def upload_video_api(request):
    """POST to upload a video directly into the server's source_loc and trigger a scan/enqueue."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    source_loc = get_setting('source_loc')
    if not source_loc or not os.path.exists(source_loc):
        return JsonResponse({'error': 'Valid source location is not configured on the server.'}, status=400)
        
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No video file provided'}, status=400)
        
    file_obj = request.FILES['file']
    filename = file_obj.name
    
    # Check valid video extension
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v')
    ext = os.path.splitext(filename)[1].lower()
    if ext not in video_extensions:
        return JsonResponse({'error': f'Unsupported file format. Only video files are allowed: {", ".join(video_extensions)}'}, status=400)
        
    # Generate unique filename in source_loc if file already exists
    base_name = os.path.splitext(filename)[0]
    target_path = os.path.join(source_loc, filename)
    counter = 1
    while os.path.exists(target_path):
        target_path = os.path.join(source_loc, f"{base_name}_{counter}{ext}")
        counter += 1
        
    # Save the uploaded file chunk by chunk to prevent memory bloat
    try:
        with open(target_path, 'wb+') as dest:
            for chunk in file_obj.chunks():
                dest.write(chunk)
    except Exception as e:
        logger.exception("Failed to write uploaded video file")
        return JsonResponse({'error': f"Failed to save video: {str(e)}"}, status=500)
        
    # Now, trigger a quick scan/parse for this specific file to register it
    try:
        clean_res = FileNameCleaner.clean(target_path, source_loc)
        
        # Rename the file and directory physically on disk if requested by parser
        final_path = target_path
        if clean_res.new_filepath != target_path:
            dest_dir = os.path.dirname(clean_res.new_filepath)
            os.makedirs(dest_dir, exist_ok=True)
            try:
                os.rename(target_path, clean_res.new_filepath)
                final_path = clean_res.new_filepath
            except Exception as rename_err:
                logger.error(f"Failed to rename file {target_path} to {clean_res.new_filepath}: {rename_err}")
                final_path = target_path
                
        # Generate slug
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
            hls_status='not_required',
            sprite_status='pending',
            preview_clip_status='pending',
            preview_status='not_required',
            transcode_target=get_setting('default_transcode_target', 'original'),
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
        
        return JsonResponse({
            'success': True,
            'message': f"Video uploaded and queued successfully: {video.title}",
            'video_id': video.id
        })
    except Exception as scan_err:
        logger.exception("Error scanning uploaded video")
        return JsonResponse({
            'success': True,
            'message': "Video uploaded successfully. Run a directory scan to register it.",
            'error_details': str(scan_err)
        })


@csrf_exempt
def network_info_api(request):
    """Returns network IP details to let the client detect if they are on the same local network."""
    import socket
    import urllib.request
    
    # 1. Get client IP
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        
    # 2. Get server local IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        server_local_ip = s.getsockname()[0]
    except Exception:
        server_local_ip = '127.0.0.1'
    finally:
        s.close()
        
    # 3. Get server public IP
    server_public_ip = None
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=1.5) as response:
            server_public_ip = response.read().decode('utf-8').strip()
    except Exception:
        pass
        
    # 4. Check if same network
    same_network = False
    if client_ip in ('127.0.0.1', 'localhost', '::1') or client_ip.startswith('192.168.') or client_ip.startswith('10.') or client_ip.startswith('172.16.') or client_ip.startswith('172.31.'):
        same_network = True
    elif client_ip.lower().startswith('fe80:') or client_ip.lower().startswith('fc00:') or client_ip.lower().startswith('fd00:'):
        same_network = True
    elif server_public_ip and client_ip == server_public_ip:
        same_network = True
        
    return JsonResponse({
        'client_ip': client_ip,
        'server_local_ip': server_local_ip,
        'server_public_ip': server_public_ip,
        'same_network': same_network
    })





