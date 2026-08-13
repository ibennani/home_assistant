/**
 * Media session for Default Media Receiver (CC1AD845).
 * Forwards LOAD/STOP to Home Assistant IPC.
 */

const { mediaNamespace } = require('@tristanpenman/castv2/lib/namespaces');
const { postToHa } = require('./ipc-client');
const { enrichCustomData } = require('./handlers/svt_play');

const DEFAULT_MEDIA_RECEIVER_APP_ID = 'CC1AD845';

class MediaSession {
  constructor(appId, device, displayName, sessionId, transportId, zoneConfig) {
    this.appId = appId;
    this.device = device;
    this.displayName = displayName;
    this.sessionId = sessionId;
    this.transportId = transportId;
    this.zoneConfig = zoneConfig;
    this.mediaSessionId = 1;
    this.playerState = 'IDLE';
    this.currentMedia = null;
    this.namespaces = [{ name: mediaNamespace }];
  }

  handleMessage(message) {
    if (message.namespace !== mediaNamespace) {
      return;
    }

    let request;
    try {
      request = JSON.parse(message.payloadUtf8);
    } catch (err) {
      console.error('invalid media payload', err);
      return;
    }

    const { type, requestId } = request;
    switch (type) {
      case 'LOAD':
        return this.handleLoad(request, message);
      case 'STOP':
        return this.handleStop(request, message);
      case 'PAUSE':
        this.playerState = 'PAUSED';
        return this.sendMediaStatus(requestId, message);
      case 'PLAY':
        this.playerState = 'PLAYING';
        return this.sendMediaStatus(requestId, message);
      case 'GET_STATUS':
        return this.sendMediaStatus(requestId, message);
      default:
        console.log('unhandled media type', type);
    }
  }

  async handleLoad(request, message) {
    const media = request.media || {};
    this.currentMedia = media;
    this.playerState = 'PLAYING';
    this.mediaSessionId += 1;

    const contentId = media.contentId || media.contentUrl;
    const contentType = media.contentType;
    const customData = enrichCustomData(contentId, media.customData || {});
    const title = media.metadata?.title || media.metadata?.subtitle;

    console.log('LOAD media', { contentId, contentType, customData });

    try {
      await postToHa(this.zoneConfig.haUrl, '/api/cast_video_to_audio_receivers/play', {
        zone_id: this.zoneConfig.zoneId,
        content_id: contentId,
        content_type: contentType,
        custom_data: customData,
        title,
      });
    } catch (err) {
      console.error('failed to notify HA', err);
      return this.sendLoadFailed(request.requestId, message, err.message);
    }

    return this.sendMediaStatus(request.requestId, message);
  }

  async handleStop(request, message) {
    this.playerState = 'IDLE';
    this.currentMedia = null;

    try {
      await postToHa(this.zoneConfig.haUrl, '/api/cast_video_to_audio_receivers/stop', {
        zone_id: this.zoneConfig.zoneId,
      });
    } catch (err) {
      console.error('failed to notify HA stop', err);
    }

    return this.sendMediaStatus(request.requestId, message);
  }

  sendLoadFailed(requestId, message, reason) {
    const payloadUtf8 = JSON.stringify({
      requestId,
      type: 'LOAD_FAILED',
      reason: 'CANCELLED',
      detailedErrorCode: 905,
      customData: { message: reason },
    });
    this.device.sendUtf8(mediaNamespace, payloadUtf8, this.transportId, message.sourceId);
  }

  sendMediaStatus(requestId, message) {
    const mediaStatus = {
      playerState: this.playerState,
      playbackRate: 1,
      currentTime: 0,
      media: this.currentMedia,
      supportedMediaCommands: 15,
    };

    const payloadUtf8 = JSON.stringify({
      requestId,
      type: 'MEDIA_STATUS',
      status: [mediaStatus],
    });

    this.device.broadcastUtf8(mediaNamespace, payloadUtf8, this.transportId);
  }
}

module.exports = {
  DEFAULT_MEDIA_RECEIVER_APP_ID,
  MediaSession,
};
