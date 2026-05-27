# Netflix clone


## Where the videos are presend
   - source loc: inputed by user
   - structure: all original videos will be present in the folder provided
      - streamable folder:
          - for each video one folder will be present under streamable
          - with a subfolder called as streams/ having all the streamable chunks
          - with a sprite sheet
          - with a thumbnail image
  
# tech stack:
  - django, reactjs, ffmpeg

# Logic:
  - Scan for original videos
  - check if a folder corresponding to that video is already present in streamable folder
  - if not present then create it, and create streams, thumbnail and sprite using ffmpeg command
  - use the chunks of that video for preview as well using ffmpeg command
  - ensure the data required for streaming is correctly present as well, you can modify the contents/ structure inside each folder to manage the streams correctly

## frontend:
  - After the backend scans, for all folders under streamable in the frontend create an icon like netflix style with scrubbable option to scrubbing through videos, and just stream the video, with forward, rewind, play pause, full screen options, and also options to select quality, by default stream in best quality, if needed use hls.js
 - there should be a settings menu via which the source loc is configurable