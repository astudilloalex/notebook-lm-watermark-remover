# User guide

Install and open NotebookLM Studio as described in [INSTALLATION.md](INSTALLATION.md). The interface opens in your browser, while Python and FFmpeg run locally on your computer.

## Add and select videos

Use the add-videos button or drag several files onto the upload area. Horizontal videos and Shorts can share one batch. MP4, MOV, MKV and WebM files are accepted when their actual codecs and geometry are supported by the processor.

Each row displays its name, duration, size, detected format and processing state. New videos are selected for processing. Upload progress refers to a temporary working copy on the same computer; the original is unchanged. Allow enough free space for working copies and outputs.

Use Select all for the entire batch or check individual rows. Click a row to inspect and configure that video.

## Preview before processing

The inspector provides before/after image comparison, original playback, end-preview/cut selection and finished-result playback. A comparison image is generated automatically for the first valid video. Choose another time and refresh the preview to inspect a different frame.

The comparison marks the target region on the original and shows the interpolated result beside it. This does not generate the complete output. Settings changes mark existing previews as stale.

### Preview the final seconds and choose a cut

Open the end/cut tab to preview the original video's last 5, 10, 20, 30 or 60 seconds with audio when present. Shorter videos are shown in full. The preview retains the original logo and closing screen.

Green indicates what is kept; red indicates what will be removed. Scrub, play or step one frame at a time. The clock refers to the full video, even though playback shows only its final segment.

The set-end button **includes the currently selected frame** and removes all following frames. The jump-to-cut button returns to the last frame that will be kept. Expand the preview window when the cut is earlier than the visible segment.

For constant-frame-rate inputs with reliable frame totals, the selection is saved in source frames. If totals are missing or nominal/average FPS differ, the selection is approximate and saved in seconds. Variable-frame-rate detection is heuristic. Output quality modes may change output FPS; frame trimming is calculated against the source.

Each video retains its own settings. Only the selected end segment is prepared, at a preview resolution of up to 1280 × 720, and reused when only the trim changes. The final result retains its configured full resolution. Stop cancels preparation.

## Configure one video or a batch

Automatic format selection uses aspect ratio and FPS:

| Profile | Default end trim |
| --- | --- |
| Explainer horizontal, approximately 24 FPS | 72 frames |
| Cinematic horizontal, approximately 30 FPS | 90 frames |
| Vertical Short | 90 frames |
| Legacy Short, selected manually | 60 frames |
| Custom region | No automatic trim |

High quality preserves detected FPS. Balanced outputs 30 FPS; Fast outputs 15 FPS. Resolution is preserved.

End trimming supports automatic settings, a nonnegative integer frame count or a nonnegative duration in seconds. Disable trimming or enter zero to keep the complete ending. Frame counts refer to the input: 30 frames at 24 FPS is 1.25 seconds. Trims that remove the entire video are rejected. The preview summary estimates the remaining duration; no closing-screen recognition is performed.

To give several videos the same trim, select them, configure one video and apply settings to the selection. Select all first to affect the entire batch. All selected files are validated before settings change; if one is incompatible or too short, no selected settings are changed.

Advanced position settings include upper-logo contrast detection for horizontal profiles, a left-side Explainer logo and an optional `X:Y:WIDTH:HEIGHT` rectangle in original pixels. An absolute rectangle suitable for one resolution may be invalid for another. In mixed automatic batches, upper-logo detection applies only to horizontal inputs.

## Process and download

Process selected videos to work through the queue sequentially. Completed videos are skipped until their settings change. A failed video is marked with its error; the rest of the batch continues.

Stop cancels the active operation and leaves remaining videos pending. Completed results remain available until session deletion. During processing, configuration changes and row removal are disabled; other videos can still be inspected.

Use a row's download arrow for its MP4 or the ZIP button for all currently completed results. The browser saves a copy to its configured download location, usually Downloads. Downloading does not move the internal result.

Wait for downloads to finish. The program cannot confirm that the browser finished writing a file simply because a download link was clicked. Reprocessing replaces that video's internal result after successful conversion. Removing a row deletes its working copies and internal outputs; save anything you need first.

## Delete the session and close

Use the application's close button. Its confirmation dialog explains the loss of undownloaded results and offers a ZIP download before exiting. Confirm session deletion to stop active work/transfers, remove temporary inputs, outputs and previews, and request server shutdown. If cleanup fails, the interface displays an error and permits retrying.

Original files and downloaded copies outside the session are preserved. Closing only the browser/tab leaves the server running. A forced exit or power loss may leave a session for cleanup at the next start. Process locks protect other active instances; unrelated folders and Downloads are not purged.

The video list and its settings are not restored after restart. Older versions' persistent result folders are not removed automatically.

## Limits

Processing runs exclusively on the local computer. The server binds only to `127.0.0.1` and requires the private session token created at launch. No external page, scripts or cloud service is needed.

Logo interpolation can leave a patch and cannot recover hidden artwork or text. Automatic profiles are proportion/FPS rules and may need manual adjustment when NotebookLM changes export formats. Inspect the comparison before processing a large batch.
