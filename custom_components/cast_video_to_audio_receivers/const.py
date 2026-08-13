"""Constants for Cast video to audio receivers."""

DOMAIN = "cast_video_to_audio_receivers"

CONF_ZONES = "zones"
CONF_ZONE_ID = "zone_id"
CONF_FRIENDLY_NAME = "friendly_name"
CONF_TARGET_ENTITY = "target_entity"
CONF_CERT_MANIFEST = "cert_manifest"
CONF_FFMPEG_PATH = "ffmpeg_path"
CONF_AUDIO_BITRATE = "audio_bitrate"
CONF_TLS_PORT = "tls_port"
CONF_MONITOR_VIDEO_ENTITY = "monitor_video_entity"
CONF_ENABLE_MONITOR = "enable_monitor"

DEFAULT_AUDIO_BITRATE = "128k"
DEFAULT_TLS_PORT = 8010
DEFAULT_FFMPEG_PATH = "ffmpeg"

IPC_PLAY_PATH = "/api/cast_video_to_audio_receivers/play"
IPC_STOP_PATH = "/api/cast_video_to_audio_receivers/stop"
IPC_HEALTH_PATH = "/api/cast_video_to_audio_receivers/health"

STREAM_URL_PREFIX = "/api/cast_video_to_audio_receivers/stream"

DEFAULT_MEDIA_RECEIVER_APP_ID = "CC1AD845"

SVT_FORMATS = [
    "hls",
    "hls-cmaf-avc",
    "hls-ts-full",
    "dash-avc",
    "dash",
]
