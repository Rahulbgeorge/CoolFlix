import os
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
    """Scans the configured source directory recursively for new video files and queues them."""
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
                    original_path = os.path.join(root, file)
                    
                    # Check if already in DB
                    if Video.objects.filter(original_path=original_path).exists():
                        continue
                        
                    # Extract title and generate unique slug
                    title_without_ext = os.path.splitext(file)[0]
                    base_slug = slugify(title_without_ext)
                    if not base_slug:
                        base_slug = "video"
                    slug = base_slug
                    counter = 1
                    while Video.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{counter}"
                        counter += 1
                        
                    # Create DB record
                    video = Video.objects.create(
                        title=title_without_ext,
                        original_path=original_path,
                        slug=slug,
                        status='pending',
                        progress=0.0
                    )
                    
                    # Put on processing queue
                    transcode_queue.put(video.id)
                    new_videos_count += 1
                    
        return JsonResponse({'success': True, 'scanned': True, 'new_videos_added': new_videos_count})
    except Exception as e:
        logger.exception("Error scanning directory")
        return JsonResponse({'error': str(e)}, status=500)

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
