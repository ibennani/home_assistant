/**
 * Extended Cast device with Default Media Receiver support.
 */

const { v4: uuidv4 } = require('uuid');
const BaseDevice = require('@tristanpenman/castv2/lib/device');
const { DEFAULT_MEDIA_RECEIVER_APP_ID, MediaSession } = require('./media-session');

class BridgeDevice extends BaseDevice {
  constructor(options, zoneConfig) {
    super(options);
    this.zoneConfig = zoneConfig;
    this.availableApps = [
      DEFAULT_MEDIA_RECEIVER_APP_ID,
      ...this.availableApps,
    ];
  }

  startApplication(appId) {
    if (Object.values(this.sessions).some((session) => session.appId === appId)) {
      console.log('application already started', { appId });
      return;
    }

    if (appId === DEFAULT_MEDIA_RECEIVER_APP_ID) {
      const sessionId = uuidv4();
      const transportId = `pid-${this.nextPid}`;
      this.nextPid += 1;

      const session = new MediaSession(
        appId,
        this,
        'Default Media Receiver',
        sessionId,
        transportId,
        this.zoneConfig,
      );

      this.sessions[sessionId] = session;
      this.registerTransport(session);
      this.emit('start', sessionId);
      return;
    }

    return super.startApplication(appId);
  }
}

module.exports = BridgeDevice;
